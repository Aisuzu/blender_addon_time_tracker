bl_info = {
    "name": "Projekt Time Tracker",
    "author": "VT",
    "version": (1, 5),
    "blender": (5, 2, 3),
    "location": "View3D > Sidebar > Timer",
    "description": "Tracking your actual working time on the project. The timer stops when nothing is done on the scene.",
    "warning": "",
    "category": "3D View",
}

import bpy
import time
from bpy.app.handlers import persistent

# --- PropertyGroup for timer data (is saved inside the .blend) ---
class ProjectTimerProperties(bpy.types.PropertyGroup):
    total_seconds: bpy.props.IntProperty(
        name="Total time (seconds)",
        default=0
    )

_timer_state = {
    "last_activity": time.monotonic(),
    "is_active": False,
    "modal_handler": None,
    "modal_started": False,
    "min_activity_interval": 1.0,
    "scene_pointer": None,
}

# --- get timer data inside scene ---
def get_timer_data():
    scene = bpy.context.scene
    if scene is None:
        return None
    return scene.project_timer

def _redraw_view3d():
    wm = bpy.context.window_manager
    if wm is None:
        return

    for window in wm.windows:
        if window.screen is None:
            continue
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

# --- logic for the timer, called every second ---
def check_activity():
    scene = bpy.context.scene
    if scene is None:
        return 1.0

    timer = get_timer_data()
    if timer is None:
        return 1.0

    current_scene_pointer = scene.as_pointer()

    # Reset timer when a different scene/file is active
    if _timer_state["scene_pointer"] != current_scene_pointer:
        timer.total_seconds = 0
        _timer_state["scene_pointer"] = current_scene_pointer
        _timer_state["last_activity"] = time.monotonic()
        _timer_state["is_active"] = False

    current_time = time.monotonic()

    if current_time - _timer_state["last_activity"] < _timer_state["min_activity_interval"]:
        if not _timer_state["is_active"]:
            _timer_state["is_active"] = True
        timer.total_seconds += 1
    else:
        _timer_state["is_active"] = False

    _redraw_view3d()
    return 1.0

# --- depsgraph handler for changes ---
@persistent
def depsgraph_update_handler(scene):
    if time.monotonic() - _timer_state["last_activity"] > _timer_state["min_activity_interval"]:
        _timer_state["last_activity"] = time.monotonic()
        _redraw_view3d()

@persistent
def _restart_on_load(dummy):
    scene = bpy.context.scene
    if scene is not None:
        scene.project_timer.total_seconds = 0
        _timer_state["scene_pointer"] = scene.as_pointer()

    _timer_state["last_activity"] = time.monotonic()
    _timer_state["is_active"] = False
    _timer_state["modal_handler"] = None
    _timer_state["modal_started"] = False

    if bpy.context.window is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')

# --- update activity and UI ---
def _update_activity():
    _timer_state["last_activity"] = time.monotonic()
    _redraw_view3d()

# --- time format for UI (HH:MM:SS) ---
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def _start_modal_operator():
    if not _timer_state.get("modal_handler") and bpy.context.window is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')
    return None

# --- UI: Panel ---
class TIME_TRACKER_PT_panel(bpy.types.Panel):
    bl_label = "Projekt Timer"
    bl_idname = "TIME_TRACKER_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Timer"

    def draw(self, context):
        layout = self.layout
        timer = get_timer_data()
        if timer is not None:
            layout.label(text=f"Project Lifetime: {format_time(timer.total_seconds)}")

class TIME_TRACKER_OT_modal(bpy.types.Operator):
    bl_idname = "view3d.time_tracker_modal"
    bl_label = "Time Tracker Modal"

    def modal(self, context, event):
        if event.value in {'PRESS', 'RELEASE'}:
            if event.type in {
                'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'MOUSEPAN', 'MOUSEROTATE', 'MOUSEZOOM'
            }:
                if time.monotonic() - _timer_state["last_activity"] > _timer_state["min_activity_interval"]:
                    _update_activity()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if _timer_state["modal_started"]:
            return {'CANCELLED'}

        _timer_state["modal_started"] = True
        _timer_state["modal_handler"] = context.window_manager.modal_handler_add(self)
        _update_activity()
        return {'RUNNING_MODAL'}

# --- Add-on registration ---
classes = (
    ProjectTimerProperties,
    TIME_TRACKER_PT_panel,
    TIME_TRACKER_OT_modal,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.project_timer = bpy.props.PointerProperty(type=ProjectTimerProperties)

    scene = bpy.context.scene
    if scene is not None:
        _timer_state["scene_pointer"] = scene.as_pointer()

    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    bpy.app.handlers.load_post.append(_restart_on_load)

    has_check_activity = False
    if not bpy.app.timers.is_registered(check_activity):
        bpy.app.timers.register(check_activity, persistent=True)

    if not bpy.app.timers.is_registered(_start_modal_operator):
        bpy.app.timers.register(
            _start_modal_operator,
            first_interval=0.1,
            persistent=True,
        )

def unregister():
    for callback in (check_activity, _start_modal_operator):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)

    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    if _restart_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restart_on_load)

    _timer_state["modal_handler"] = None
    _timer_state["modal_started"] = False

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Scene, "project_timer"):
        del bpy.types.Scene.project_timer

if __name__ == "__main__":
    register()