"""GestureCAD localhost UDP receiver for Blender."""

bl_info = {
    "name": "GestureCAD UDP Receiver",
    "author": "GestureCAD",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > GestureCAD",
    "description": "Apply local GestureCAD UDP messages to Blender objects",
    "category": "3D View",
}

import json
import math
import socket
from collections import deque

import bpy
import gpu
from bpy.props import BoolProperty, FloatProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader


HOST = "127.0.0.1"
PORT = 8765
POLL_INTERVAL = 0.02
MAX_DATAGRAMS_PER_POLL = 256
MAX_MESSAGES_PER_TICK = 50

_socket: socket.socket | None = None
_messages: deque[dict] = deque(maxlen=500)
_cursor_uv: tuple[float, float] | None = None
_draw_handler = None
_cursor_shader = None
pointer_world = None


def _validate_message(message):
    """Validate decoded JSON locally so the add-on installs as one file."""
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise ValueError("expected a JSON object with a string type")
    kind = message["type"]
    fields = {
        "translate": {"type", "dx", "dy"},
        "scale": {"type", "factor"},
        "rotate": {"type", "axis", "radians"},
        "select": {"type", "name"},
        "command": {"type", "op", "axis", "value"},
        "cursor": {"type", "u", "v"},
        "undo": {"type"},
    }
    if kind not in fields or set(message) != fields[kind]:
        raise ValueError("unsupported message type or invalid message fields")
    numeric = {
        "translate": ("dx", "dy"),
        "scale": ("factor",),
        "rotate": ("radians",),
        "command": ("value",),
        "cursor": ("u", "v"),
    }.get(kind, ())
    for key in numeric:
        value = message[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
    if kind == "scale" and message["factor"] <= 0:
        raise ValueError("factor must be greater than zero")
    if kind == "cursor" and any(
        not 0.0 <= message[key] <= 1.0 for key in ("u", "v")
    ):
        raise ValueError("cursor u and v must be between zero and one")
    if kind in {"rotate", "command"}:
        if not isinstance(message["axis"], str) or message["axis"] not in {"x", "y", "z"}:
            raise ValueError("axis must be x, y, or z")
    if kind == "command" and message["op"] != "move":
        raise ValueError("only the move command is supported")
    if kind == "select" and (not isinstance(message["name"], str) or not message["name"].strip()):
        raise ValueError("select name must be a non-empty string")
    return message


def _apply_message(message):
    """Apply one already-validated message using Blender's main-thread API."""
    kind = message["type"]
    if kind == "cursor":
        _update_pointer(message["u"], message["v"])
        return
    if kind == "undo":
        bpy.ops.ed.undo()
        return
    if kind == "select":
        obj = bpy.data.objects.get(message["name"])
        if obj is None:
            raise ValueError(f"object not found: {message['name']}")
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return

    obj = bpy.context.view_layer.objects.active
    if obj is None:
        raise ValueError("there is no active object")
    if kind == "translate":
        obj.location.x += message["dx"]
        obj.location.y += message["dy"]
    elif kind == "scale":
        obj.scale *= message["factor"]
    elif kind == "rotate":
        obj.rotation_euler["xyz".index(message["axis"])] += message["radians"]
    elif kind == "command":
        obj.location["xyz".index(message["axis"])] += message["value"]


def _active_view3d_region():
    """Find a 3D window region for ray conversion from the current window."""
    area = bpy.context.area
    if area is not None and area.type == "VIEW_3D":
        region = next((item for item in area.regions if item.type == "WINDOW"), None)
        if region is not None:
            return area, region
    window = bpy.context.window
    if window is None or window.screen is None:
        return None, None
    for area in window.screen.areas:
        if area.type == "VIEW_3D":
            region = next((item for item in area.regions if item.type == "WINDOW"), None)
            if region is not None:
                return area, region
    return None, None


def _tag_view3d_redraw():
    manager = bpy.context.window_manager
    if manager is None:
        return
    for window in manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _snap_world_point(scene, point):
    if not scene.gesturecad_grid_snap:
        return point
    step = scene.gesturecad_grid_size
    if step <= 0:
        return point
    return tuple(round(component / step) * step for component in point)


def _update_pointer(u, v):
    global _cursor_uv, pointer_world
    _cursor_uv = (u, v)
    pointer_world = None
    scene = bpy.context.scene
    if scene is not None and "pointer_world" in scene:
        del scene["pointer_world"]
    area, region = _active_view3d_region()
    if scene is None or area is None or region is None or region.width == 0 or region.height == 0:
        _tag_view3d_redraw()
        return

    space = area.spaces.active
    region_3d = space.region_3d
    region_coord = (u * region.width, v * region.height)
    ray_origin = view3d_utils.region_2d_to_origin_3d(
        region, region_3d, region_coord, clamp=1000.0
    )
    ray_direction = view3d_utils.region_2d_to_vector_3d(
        region, region_3d, region_coord
    )
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _face_index, _obj, _matrix = scene.ray_cast(
        depsgraph, ray_origin, ray_direction, distance=10000.0
    )
    if hit:
        point = tuple(location)
    elif abs(ray_direction.z) > 1e-8:
        distance = -ray_origin.z / ray_direction.z
        point = tuple(ray_origin + ray_direction * distance) if distance >= 0 else None
    else:
        point = None

    pointer_world = _snap_world_point(scene, point) if point is not None else None
    if pointer_world is not None:
        scene["pointer_world"] = pointer_world
    _tag_view3d_redraw()


def _draw_cursor():
    """Draw a solid square in normalized WINDOW-region coordinates."""
    global _cursor_shader
    if _cursor_uv is None:
        return
    context = bpy.context
    region = context.region
    if region is None or region.type != "WINDOW":
        return
    if _cursor_shader is None:
        _cursor_shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    center_x = _cursor_uv[0] * region.width
    center_y = _cursor_uv[1] * region.height
    half_size = 7.0
    left, right = center_x - half_size, center_x + half_size
    bottom, top = center_y - half_size, center_y + half_size
    vertices = (
        (left, bottom), (right, bottom), (left, top),
        (left, top), (right, bottom), (right, top),
    )
    batch = batch_for_shader(_cursor_shader, "TRIS", {"pos": vertices})
    _cursor_shader.bind()
    _cursor_shader.uniform_float("color", (1.0, 0.25, 0.05, 1.0))
    batch.draw(_cursor_shader)


def _ensure_draw_handler():
    global _draw_handler
    if _draw_handler is None:
        _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cursor, (), "WINDOW", "POST_PIXEL"
        )


def _remove_draw_handler():
    global _draw_handler, _cursor_shader, _cursor_uv, pointer_world
    if _draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, "WINDOW")
        _draw_handler = None
    _cursor_shader = None
    _cursor_uv = None
    pointer_world = None
    scene = bpy.context.scene
    if scene is not None and "pointer_world" in scene:
        del scene["pointer_world"]
    _tag_view3d_redraw()


def _apply_timer():
    """Apply queued actions on Blender's main thread."""
    if _socket is None:
        return None
    for _ in range(min(len(_messages), MAX_MESSAGES_PER_TICK)):
        message = _messages.popleft()
        try:
            _apply_message(message)
        except Exception as error:
            print(f"GestureCAD: could not apply {message}: {error}")
    return POLL_INTERVAL


def _receive_timer():
    """Non-blockingly receive and queue UDP datagrams, then keep polling."""
    if _socket is None:
        return None
    for _ in range(MAX_DATAGRAMS_PER_POLL):
        try:
            payload, _address = _socket.recvfrom(65535)
        except BlockingIOError:
            break
        except OSError as error:
            print(f"GestureCAD: UDP receive stopped: {error}")
            stop_receiver()
            return None
        try:
            message = _validate_message(json.loads(payload.decode("utf-8")))
            _messages.append(message)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            print(f"GestureCAD: ignored invalid UDP message: {error}")
    return POLL_INTERVAL


def start_receiver():
    global _socket
    if _socket is not None:
        return
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.setblocking(False)
    try:
        receiver.bind((HOST, PORT))
    except OSError:
        receiver.close()
        raise
    _socket = receiver
    _ensure_draw_handler()
    if not bpy.app.timers.is_registered(_receive_timer):
        bpy.app.timers.register(_receive_timer, first_interval=POLL_INTERVAL, persistent=True)
    if not bpy.app.timers.is_registered(_apply_timer):
        bpy.app.timers.register(_apply_timer, first_interval=POLL_INTERVAL, persistent=True)
    print(f"GestureCAD: listening on {HOST}:{PORT}")


def stop_receiver():
    global _socket
    if _socket is not None:
        _socket.close()
        _socket = None
    _messages.clear()
    _remove_draw_handler()
    for callback in (_receive_timer, _apply_timer):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)
    print("GestureCAD: receiver stopped")


class GESTURECAD_OT_start_receiver(bpy.types.Operator):
    bl_idname = "gesturecad.start_receiver"
    bl_label = "Start Receiver"

    def execute(self, context):
        try:
            start_receiver()
        except OSError as error:
            self.report({"ERROR"}, f"Could not bind {HOST}:{PORT}: {error}")
            return {"CANCELLED"}
        return {"FINISHED"}


class GESTURECAD_OT_stop_receiver(bpy.types.Operator):
    bl_idname = "gesturecad.stop_receiver"
    bl_label = "Stop Receiver"

    def execute(self, context):
        stop_receiver()
        return {"FINISHED"}


class GESTURECAD_PT_receiver(bpy.types.Panel):
    bl_label = "GestureCAD Receiver"
    bl_idname = "GESTURECAD_PT_receiver"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GestureCAD"

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"UDP {HOST}:{PORT}")
        if _socket is None:
            layout.operator(GESTURECAD_OT_start_receiver.bl_idname, icon="PLAY")
        else:
            layout.label(text="Listening", icon="CHECKMARK")
            layout.operator(GESTURECAD_OT_stop_receiver.bl_idname, icon="PAUSE")
        layout.separator()
        layout.prop(context.scene, "gesturecad_grid_snap", text="Grid Snap")
        if context.scene.gesturecad_grid_snap:
            layout.prop(context.scene, "gesturecad_grid_size", text="Grid Size")


_CLASSES = (
    GESTURECAD_OT_start_receiver,
    GESTURECAD_OT_stop_receiver,
    GESTURECAD_PT_receiver,
)


def register():
    bpy.types.Scene.gesturecad_grid_snap = BoolProperty(
        name="GestureCAD Grid Snap", default=True
    )
    bpy.types.Scene.gesturecad_grid_size = FloatProperty(
        name="GestureCAD Grid Size", default=0.01, min=0.0001, unit="LENGTH"
    )
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    try:
        start_receiver()
    except OSError as error:
        print(f"GestureCAD: could not bind {HOST}:{PORT}: {error}")


def unregister():
    stop_receiver()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gesturecad_grid_size
    del bpy.types.Scene.gesturecad_grid_snap


if __name__ == "__main__":
    register()
