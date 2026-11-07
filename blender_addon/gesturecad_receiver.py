"""GestureCAD localhost UDP receiver for Blender."""

bl_info = {
    "name": "GestureCAD UDP Receiver",
    "author": "GestureCAD",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > GestureCAD",
    "description": "Apply local GestureCAD UDP messages to Blender objects",
    "category": "3D View",
}

import json
import math
import socket
from collections import deque

import bpy


HOST = "127.0.0.1"
PORT = 8765
POLL_INTERVAL = 0.02
MAX_DATAGRAMS_PER_POLL = 256
MAX_MESSAGES_PER_TICK = 50

_socket: socket.socket | None = None
_messages: deque[dict] = deque(maxlen=500)


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
        "undo": {"type"},
    }
    if kind not in fields or set(message) != fields[kind]:
        raise ValueError("unsupported message type or invalid message fields")
    numeric = {
        "translate": ("dx", "dy"),
        "scale": ("factor",),
        "rotate": ("radians",),
        "command": ("value",),
    }.get(kind, ())
    for key in numeric:
        value = message[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
    if kind == "scale" and message["factor"] <= 0:
        raise ValueError("factor must be greater than zero")
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


_CLASSES = (
    GESTURECAD_OT_start_receiver,
    GESTURECAD_OT_stop_receiver,
    GESTURECAD_PT_receiver,
)


def register():
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


if __name__ == "__main__":
    register()
