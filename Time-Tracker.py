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


# This property is stored in the .blend file. It therefore survives closing
# and reopening that file (provided the .blend is saved).
class ProjectTimerProperties(bpy.types.PropertyGroup):
    total_seconds: bpy.props.IntProperty(
        name="Total time (seconds)",
        default=0,
        min=0,
    )


_timer_state = {
    "last_activity": time.monotonic(),
    "is_active": False,
    "modal_started": False,
    "min_activity_interval": 1.0,
    "scene_pointer": None,
    "last_total_seconds": 0,
}


def get_timer_data():
    scene = getattr(bpy.context, "scene", None)
    if scene is None or not hasattr(scene, "project_timer"):
        return None
    return scene.project_timer


def _redraw_view3d():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return

    for window in wm.windows:
        if window.screen is None:
            continue
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def check_activity():
    scene = getattr(bpy.context, "scene", None)
    if scene is None or not hasattr(scene, "project_timer"):
        return 1.0

    timer = scene.project_timer
    scene_pointer = scene.as_pointer()

    if _timer_state["scene_pointer"] is None:
        # First run: keep the value loaded from this .blend; don't reset it.
        _timer_state["scene_pointer"] = scene_pointer
        _timer_state["last_total_seconds"] = timer.total_seconds
    elif _timer_state["scene_pointer"] != scene_pointer:
        # A scene switch within the same file continues the file's timer.
        timer.total_seconds = _timer_state["last_total_seconds"]
        _timer_state["scene_pointer"] = scene_pointer
        _timer_state["last_activity"] = time.monotonic()
        _timer_state["is_active"] = False

    now = time.monotonic()
    if now - _timer_state["last_activity"] < _timer_state["min_activity_interval"]:
        _timer_state["is_active"] = True
        timer.total_seconds += 1
    else:
        _timer_state["is_active"] = False

    _timer_state["last_total_seconds"] = timer.total_seconds
    _redraw_view3d()
    return 1.0


@persistent
def depsgraph_update_handler(scene):
    if time.monotonic() - _timer_state["last_activity"] > _timer_state["min_activity_interval"]:
        _update_activity()


@persistent
def _restart_on_load(_dummy):
    # The loaded scene property contains the saved time. Preserve it and reset
    # only transient runtime state for the newly loaded file.
    scene = getattr(bpy.context, "scene", None)
    if scene is not None and hasattr(scene, "project_timer"):
        _timer_state["scene_pointer"] = scene.as_pointer()
        _timer_state["last_total_seconds"] = scene.project_timer.total_seconds
    else:
        _timer_state["scene_pointer"] = None
        _timer_state["last_total_seconds"] = 0

    _timer_state["last_activity"] = time.monotonic()
    _timer_state["is_active"] = False
    _timer_state["modal_started"] = False

    if getattr(bpy.context, "window", None) is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')


def _update_activity():
    _timer_state["last_activity"] = time.monotonic()
    _redraw_view3d()


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _start_modal_operator():
    if not _timer_state["modal_started"] and getattr(bpy.context, "window", None) is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')
    return None


class TIME_TRACKER_PT_panel(bpy.types.Panel):
    bl_label = "Projekt Timer"
    bl_idname = "TIME_TRACKER_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Timer"

    def draw(self, context):
        timer = get_timer_data()
        if timer is not None:
            self.layout.label(text=f"Project Lifetime: {format_time(timer.total_seconds)}")


class TIME_TRACKER_OT_modal(bpy.types.Operator):
    bl_idname = "view3d.time_tracker_modal"
    bl_label = "Time Tracker Modal"

    def modal(self, context, event):
        if event.value in {'PRESS', 'RELEASE'} and event.type in {
            'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
            'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
            'MOUSEPAN', 'MOUSEROTATE', 'MOUSEZOOM',
        }:
            if time.monotonic() - _timer_state["last_activity"] > _timer_state["min_activity_interval"]:
                _update_activity()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if _timer_state["modal_started"]:
            return {'CANCELLED'}

        _timer_state["modal_started"] = True
        context.window_manager.modal_handler_add(self)
        _update_activity()
        return {'RUNNING_MODAL'}


classes = (
    ProjectTimerProperties,
    TIME_TRACKER_PT_panel,
    TIME_TRACKER_OT_modal,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.project_timer = bpy.props.PointerProperty(type=ProjectTimerProperties)

    # Don't access bpy.context.scene here: Blender can restrict context while
    # registering an add-on. The first timer callback initializes runtime state.
    if depsgraph_update_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    if _restart_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_restart_on_load)

    if not bpy.app.timers.is_registered(check_activity):
        bpy.app.timers.register(check_activity, persistent=True)
    if not bpy.app.timers.is_registered(_start_modal_operator):
        bpy.app.timers.register(_start_modal_operator, first_interval=0.1, persistent=True)


def unregister():
    for callback in (check_activity, _start_modal_operator):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)

    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    if _restart_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restart_on_load)

    _timer_state["scene_pointer"] = None
    _timer_state["last_total_seconds"] = 0
    _timer_state["is_active"] = False
    _timer_state["modal_started"] = False

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Scene, "project_timer"):
        del bpy.types.Scene.project_timer


if __name__ == "__main__":
    register()
