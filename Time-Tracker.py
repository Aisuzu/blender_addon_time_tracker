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
    "last_activity": time.time(),
    "is_active": False,
    "start_time": 0.0,
    "modal_handler": None,
    "min_activity_interval": 1.0,
    # Used to detect switching to a different scene in the current file.
    "scene_pointer": None,
}

# --- get timer data inside scene ---
def get_timer_data():
    scene = bpy.context.scene
    return scene.project_timer if scene is not None else None

# --- "logic" for the timer, is called every 1 second ---
def check_activity():
    scene = bpy.context.scene
    if scene is None:
        return 1.0

    timer = scene.project_timer
    scene_pointer = scene.as_pointer()

    # Start a fresh timer when the active scene changes.
    if _timer_state["scene_pointer"] != scene_pointer:
        timer.total_seconds = 0
        _timer_state["scene_pointer"] = scene_pointer
        _timer_state["last_activity"] = time.time()
        _timer_state["is_active"] = False

    current_time = time.time()

    if current_time - _timer_state["last_activity"] < _timer_state["min_activity_interval"]:
        if not _timer_state["is_active"]:
            _timer_state["start_time"] = current_time
            _timer_state["is_active"] = True
        timer.total_seconds += 1
    else:
        if _timer_state["is_active"]:
            _timer_state["is_active"] = False

    wm = bpy.context.window_manager
    if wm is not None:
        for window in wm.windows:
            if window.screen is not None:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

    return 1.0

# --- depsgraph-Handler for changes ---
@persistent
def depsgraph_update_handler(scene):
    if (time.time() - _timer_state["last_activity"]) > _timer_state["min_activity_interval"]:
        _update_activity()

@persistent
def _restart_on_load(dummy):
    # A loaded .blend may contain previously saved timer values. Always clear
    # the active scene's value so every newly opened file starts from zero.
    scene = bpy.context.scene
    if scene is not None:
        scene.project_timer.total_seconds = 0
        _timer_state["scene_pointer"] = scene.as_pointer()

    _timer_state["last_activity"] = time.time()
    _timer_state["is_active"] = False
    _timer_state["modal_handler"] = None

    if bpy.context.window is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')

# --- update the activity and UI ---
def _update_activity():
    _timer_state["last_activity"] = time.time()
    wm = bpy.context.window_manager
    if wm is not None:
        for window in wm.windows:
            if window.screen is not None:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

# --- time format for UI (HH:MM:SS) ---
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _start_modal_operator():
    if not _timer_state.get("modal_handler"):
        if bpy.context.window is not None:
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
        if event.value in {'PRESS', 'RELEASE'} and (time.time() - _timer_state["last_activity"]) > _timer_state["min_activity_interval"]:
            if event.type in {
                'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'MOUSEPAN', 'MOUSEROTATE', 'MOUSEZOOM'
            }:
                _update_activity()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        _timer_state["modal_handler"] = context.window_manager.modal_handler_add(self)
        _update_activity()
        return {'RUNNING_MODAL'}

# --- Add-on registration---
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
    _timer_state["scene_pointer"] = scene.as_pointer() if scene is not None else None

    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    bpy.app.handlers.load_post.append(_restart_on_load)

    bpy.app.timers.register(check_activity, persistent=True)
    bpy.app.timers.register(_start_modal_operator, first_interval=0.1, persistent=True)

def unregister():
    if check_activity in bpy.app.timers.timers():
        bpy.app.timers.unregister(check_activity)

    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    if _restart_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restart_on_load)

    if _timer_state.get("modal_handler"):
        _timer_state["modal_handler"] = None

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.project_timer

if __name__ == "__main__":
    register()
