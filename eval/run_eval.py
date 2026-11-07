"""Blender UI task runner for GestureCAD interaction evaluations.

Launch with, for example:
    blender --python eval/run_eval.py -- --participant P001 --condition gesture+voice
"""

bl_info = {
    "name": "GestureCAD Evaluation Runner",
    "author": "GestureCAD",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Evaluation",
    "category": "3D View",
}

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import bpy
from bpy.props import IntProperty, StringProperty


EVAL_DIR = Path(__file__).resolve().parent
TASKS = (
    {
        "title": "1. Orbit and place",
        "instruction": (
            "Orbit to azimuth 45 degrees and elevation 30 degrees. Place "
            "Eval_Cube on the red marked spot."
        ),
    },
    {
        "title": "2. Exact dimensions",
        "instruction": (
            "Resize Eval_Box to exactly 1.20 x 0.80 x 1.50 m. Use object "
            "dimensions, not the displayed scale values."
        ),
    },
    {
        "title": "3. Match reference",
        "instruction": (
            "Rotate, scale, and place Eval_Cube_B, Eval_Sphere, and Eval_Cone "
            "to match eval/reference.svg."
        ),
    },
)

_SESSION = None
_CLASSES = []


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _log_event(event: str, **details) -> None:
    if _SESSION is None:
        return
    entry = {"timestamp": _utc_now(), "event": event, **details}
    path = _SESSION["events_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def _place_text(body: str, name: str, location, size=0.25):
    bpy.ops.object.text_add(location=location)
    text_obj = bpy.context.object
    text_obj.name = name
    text_obj.data.body = body
    text_obj.data.size = size
    text_obj.data.extrude = 0.001
    return text_obj


def _create_eval_scene(participant_id: str):
    scene = bpy.data.scenes.new(f"Eval {participant_id}")
    window = bpy.context.window
    if window is not None:
        window.scene = scene

    ground_material = _material("Eval Ground", (0.16, 0.18, 0.21, 1.0))
    red_material = _material("Eval Target Red", (0.95, 0.12, 0.08, 1.0))
    blue_material = _material("Eval Blue", (0.15, 0.42, 0.95, 1.0))
    green_material = _material("Eval Green", (0.16, 0.72, 0.38, 1.0))
    gold_material = _material("Eval Gold", (0.95, 0.62, 0.12, 1.0))

    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 1, -0.03))
    ground = bpy.context.object
    ground.name = "Eval_Ground"
    ground.data.materials.append(ground_material)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.55, minor_radius=0.035, location=(2, 0, 0.01)
    )
    marker = bpy.context.object
    marker.name = "Eval_Target_Marker"
    marker.data.materials.append(red_material)
    _place_text("TASK 1 - PLACE ON RED RING", "Eval_Task1_Label", (0.7, -0.8, 0.02), 0.22)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-2, 0, 0.5))
    cube = bpy.context.object
    cube.name = "Eval_Cube"
    cube.data.materials.append(blue_material)

    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 0.25))
    box = bpy.context.object
    box.name = "Eval_Box"
    box.data.materials.append(green_material)
    _place_text(
        "TASK 2 DIMENSION CARD: 1.20 x 0.80 x 1.50 m",
        "Eval_Dimension_Card",
        (-1.4, 1.0, 0.02),
        0.22,
    )

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-3, 4, 0.5))
    cube_b = bpy.context.object
    cube_b.name = "Eval_Cube_B"
    cube_b.rotation_euler.z = math.radians(-20)
    cube_b.scale = (0.75, 1.2, 1.0)
    cube_b.data.materials.append(blue_material)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5, location=(1, 3, 0.5))
    sphere = bpy.context.object
    sphere.name = "Eval_Sphere"
    sphere.rotation_euler.z = math.radians(35)
    sphere.scale = (1.2, 1.2, 1.2)
    sphere.data.materials.append(green_material)

    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.5, depth=1.0, location=(3, 5, 0.5))
    cone = bpy.context.object
    cone.name = "Eval_Cone"
    cone.rotation_euler.z = math.radians(-35)
    cone.scale = (1.2, 0.8, 1.0)
    cone.data.materials.append(gold_material)
    _place_text("TASK 3 - SEE eval/reference.svg", "Eval_Task3_Label", (-2.0, 5.2, 0.02), 0.22)

    # Set a useful initial viewport when Blender was launched with a UI.
    for area in bpy.context.screen.areas if bpy.context.screen else ():
        if area.type == "VIEW_3D":
            region_3d = area.spaces.active.region_3d
            region_3d.view_location = (0.0, 1.5, 0.0)
            region_3d.view_distance = 13.0
    bpy.context.view_layer.objects.active = cube
    cube.select_set(True)
    return scene


def _append_csv_row() -> None:
    session = _SESSION
    row = {
        "participant_id": session["participant_id"],
        "condition": session["condition"],
        "condition_started_at": session["started_at"],
        "condition_ended_at": _utc_now(),
    }
    for index, task in enumerate(session["tasks"], start=1):
        prefix = f"task{index}"
        row[f"{prefix}_start"] = task["start_timestamp"]
        row[f"{prefix}_end"] = task["end_timestamp"]
        row[f"{prefix}_time_seconds"] = round(task["elapsed_seconds"], 3)
        row[f"{prefix}_error_count"] = task["error_count"]
    for key in (
        "mental_demand",
        "physical_demand",
        "temporal_demand",
        "performance",
        "effort",
        "frustration",
    ):
        row[f"nasa_{key}"] = getattr(bpy.context.scene, f"eval_nasa_{key}")

    csv_path = session["csv_path"]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    _log_event("condition_saved", csv_path=str(csv_path), nasa_tlx={key: row[f"nasa_{key}"] for key in (
        "mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration"
    )})
    print(f"GestureCAD evaluation saved: {csv_path}")
    _SESSION["saved"] = True


def _refresh_ui():
    if _SESSION is None:
        return None
    manager = bpy.context.window_manager
    if manager:
        for window in manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    return 0.25


class GESTURECAD_EVAL_OT_start_task(bpy.types.Operator):
    bl_idname = "gesturecad_eval.start_task"
    bl_label = "Start Task"
    task_index: IntProperty(min=0, max=2)

    def execute(self, context):
        session = _SESSION
        if session is None or session["active_task"] is not None:
            self.report({"ERROR"}, "A task is already active or no evaluation is configured")
            return {"CANCELLED"}
        if self.task_index != len(session["completed"]):
            self.report({"ERROR"}, "Tasks must be completed in order")
            return {"CANCELLED"}
        record = {
            "start_timestamp": _utc_now(),
            "start_monotonic": time.perf_counter(),
            "error_count": 0,
        }
        session["active_task"] = self.task_index
        session["active_record"] = record
        _log_event(
            "task_started",
            task_index=self.task_index + 1,
            task_title=TASKS[self.task_index]["title"],
        )
        return {"FINISHED"}


class GESTURECAD_EVAL_OT_mark_error(bpy.types.Operator):
    bl_idname = "gesturecad_eval.mark_error"
    bl_label = "Mark Error"

    def execute(self, context):
        session = _SESSION
        if session is None or session["active_task"] is None:
            self.report({"ERROR"}, "No task is active")
            return {"CANCELLED"}
        session["active_record"]["error_count"] += 1
        note = context.scene.eval_error_note.strip()
        _log_event(
            "task_error_marked",
            task_index=session["active_task"] + 1,
            error_count=session["active_record"]["error_count"],
            note=note,
        )
        context.scene.eval_error_note = ""
        return {"FINISHED"}


class GESTURECAD_EVAL_OT_finish_task(bpy.types.Operator):
    bl_idname = "gesturecad_eval.finish_task"
    bl_label = "End Task"

    def execute(self, context):
        session = _SESSION
        if session is None or session["active_task"] is None:
            self.report({"ERROR"}, "No task is active")
            return {"CANCELLED"}
        index = session["active_task"]
        record = session["active_record"]
        end_timestamp = _utc_now()
        elapsed = time.perf_counter() - record["start_monotonic"]
        result = {
            "start_timestamp": record["start_timestamp"],
            "end_timestamp": end_timestamp,
            "elapsed_seconds": elapsed,
            "error_count": record["error_count"],
        }
        session["tasks"].append(result)
        session["completed"].append(index)
        session["active_task"] = None
        session["active_record"] = None
        _log_event(
            "task_ended",
            task_index=index + 1,
            start_timestamp=result["start_timestamp"],
            end_timestamp=end_timestamp,
            elapsed_seconds=round(elapsed, 3),
            error_count=result["error_count"],
        )
        return {"FINISHED"}


class GESTURECAD_EVAL_OT_submit_condition(bpy.types.Operator):
    bl_idname = "gesturecad_eval.submit_condition"
    bl_label = "Save Condition and NASA-TLX"

    def execute(self, context):
        if _SESSION is None or len(_SESSION["completed"]) != len(TASKS):
            self.report({"ERROR"}, "Complete all three tasks first")
            return {"CANCELLED"}
        if _SESSION["saved"]:
            self.report({"WARNING"}, "This condition has already been saved")
            return {"CANCELLED"}
        _append_csv_row()
        self.report({"INFO"}, "Condition results saved to CSV")
        return {"FINISHED"}


class GESTURECAD_EVAL_PT_panel(bpy.types.Panel):
    bl_label = "GestureCAD Evaluation"
    bl_idname = "GESTURECAD_EVAL_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Evaluation"

    def draw(self, context):
        layout = self.layout
        session = _SESSION
        if session is None:
            layout.label(text="No evaluation session configured")
            return
        layout.label(text=f"Participant: {session['participant_id']}")
        layout.label(text=f"Condition: {session['condition']}")
        layout.separator()

        for index, task in enumerate(TASKS):
            result = session["tasks"][index] if index < len(session["tasks"]) else None
            status = "Done" if result else "Ready"
            if result:
                status += f" - {result['elapsed_seconds']:.1f}s, {result['error_count']} errors"
            layout.label(text=f"{task['title']}: {status}")

        active = session["active_task"]
        if active is not None:
            record = session["active_record"]
            elapsed = time.perf_counter() - record["start_monotonic"]
            layout.separator()
            layout.label(text=TASKS[active]["instruction"])
            layout.label(text=f"Running: {elapsed:.1f}s | Errors: {record['error_count']}")
            row = layout.row(align=True)
            row.operator(GESTURECAD_EVAL_OT_mark_error.bl_idname, icon="ERROR")
            row.operator(GESTURECAD_EVAL_OT_finish_task.bl_idname, icon="CHECKMARK")
            layout.prop(context.scene, "eval_error_note", text="Error note")
            return

        next_index = len(session["completed"])
        if next_index < len(TASKS):
            layout.separator()
            layout.label(text=TASKS[next_index]["instruction"])
            op = layout.operator(GESTURECAD_EVAL_OT_start_task.bl_idname, icon="PLAY")
            op.task_index = next_index
        elif not session["saved"]:
            layout.separator()
            layout.label(text="NASA-TLX - rate each dimension from 0 to 20")
            layout.prop(context.scene, "eval_nasa_mental_demand", text="Mental demand", slider=True)
            layout.prop(context.scene, "eval_nasa_physical_demand", text="Physical demand", slider=True)
            layout.prop(context.scene, "eval_nasa_temporal_demand", text="Temporal demand", slider=True)
            layout.prop(context.scene, "eval_nasa_performance", text="Performance (0=best, 20=worst)", slider=True)
            layout.prop(context.scene, "eval_nasa_effort", text="Effort", slider=True)
            layout.prop(context.scene, "eval_nasa_frustration", text="Frustration", slider=True)
            layout.operator(GESTURECAD_EVAL_OT_submit_condition.bl_idname, icon="FILE_TICK")
        else:
            layout.label(text=f"Saved to {session['csv_path'].name}", icon="CHECKMARK")


def _register_classes():
    global _CLASSES
    _CLASSES = [
        GESTURECAD_EVAL_OT_start_task,
        GESTURECAD_EVAL_OT_mark_error,
        GESTURECAD_EVAL_OT_finish_task,
        GESTURECAD_EVAL_OT_submit_condition,
        GESTURECAD_EVAL_PT_panel,
    ]
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def _register_scene_properties():
    bpy.types.Scene.eval_error_note = StringProperty(name="Error note", maxlen=120)
    for key, label in (
        ("mental_demand", "Mental demand"),
        ("physical_demand", "Physical demand"),
        ("temporal_demand", "Temporal demand"),
        ("performance", "Performance"),
        ("effort", "Effort"),
        ("frustration", "Frustration"),
    ):
        setattr(
            bpy.types.Scene,
            f"eval_nasa_{key}",
            IntProperty(name=label, default=0, min=0, max=20),
        )


def _cli_args():
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", required=True, help="participant identifier")
    parser.add_argument(
        "--condition",
        required=True,
        choices=("gesture+voice", "mouse+keyboard"),
    )
    parser.add_argument("--csv", default=str(EVAL_DIR / "results.csv"))
    parser.add_argument("--events", default=str(EVAL_DIR / "events.jsonl"))
    return parser.parse_args(arguments)


def register():
    global _SESSION
    args = _cli_args()
    _SESSION = {
        "participant_id": args.participant,
        "condition": args.condition,
        "started_at": _utc_now(),
        "csv_path": Path(args.csv).expanduser().resolve(),
        "events_path": Path(args.events).expanduser().resolve(),
        "active_task": None,
        "active_record": None,
        "completed": [],
        "tasks": [],
        "saved": False,
    }
    _register_scene_properties()
    _register_classes()
    _create_eval_scene(args.participant)
    _log_event(
        "condition_started",
        participant_id=args.participant,
        condition=args.condition,
        tasks=[task["title"] for task in TASKS],
    )
    bpy.app.timers.register(_refresh_ui, first_interval=0.25, persistent=True)
    print("GestureCAD evaluation ready. Use the Evaluation tab in the 3D View sidebar.")


def unregister():
    if bpy.app.timers.is_registered(_refresh_ui):
        bpy.app.timers.unregister(_refresh_ui)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    for key in (
        "eval_error_note",
        "eval_nasa_mental_demand",
        "eval_nasa_physical_demand",
        "eval_nasa_temporal_demand",
        "eval_nasa_performance",
        "eval_nasa_effort",
        "eval_nasa_frustration",
    ):
        if hasattr(bpy.types.Scene, key):
            delattr(bpy.types.Scene, key)


if __name__ == "__main__":
    register()
