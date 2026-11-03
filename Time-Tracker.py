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

# --- PropertyGroup für Timer-Daten (wird in der .blend-Datei gespeichert) ---
class ProjectTimerProperties(bpy.types.PropertyGroup):
    total_seconds: bpy.props.IntProperty(
        name="Gesamtzeit (Sekunden)",
        default=0
    )

_timer_state = {
    "last_activity": time.time(),  # Wird nicht gespeichert, aber immer aktuell
    "is_active": False,
    "start_time": 0.0,
    "modal_handler": None,
    "min_activity_interval": 1.0
}

# --- Timer-Daten abrufen ---
def get_timer_data():
    scene = bpy.context.scene
    return scene.project_timer

# --- Timer-Logik (wird alle 1 Sekunde aufgerufen) ---
def check_activity():
    timer = get_timer_data()
    current_time = time.time()

    if current_time - _timer_state["last_activity"] < _timer_state["min_activity_interval"]:
        if not _timer_state["is_active"]:
            _timer_state["start_time"] = current_time
            _timer_state["is_active"] = True
        timer.total_seconds += 1
    else:
        if _timer_state["is_active"]:
            _timer_state["is_active"] = False
            
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    return 1.0  # Timer alle 1 Sekunde ausführen

# --- depsgraph-Handler für Szenenänderungen ---
def depsgraph_update_handler(scene):
    if (time.time() - _timer_state["last_activity"]) > _timer_state["min_activity_interval"]:
        _update_activity()

# --- Aktivität aktualisieren ---
def _update_activity():
    _timer_state["last_activity"] = time.time()
    # Erzwinge UI-Update
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

# --- Zeit formatieren (HH:MM:SS) ---
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _start_modal_operator():
    if bpy.context.window is not None:
        bpy.ops.view3d.time_tracker_modal('INVOKE_DEFAULT')
    return None

# --- UI: Panel in der Seitenleiste ---
class TIME_TRACKER_PT_panel(bpy.types.Panel):
    bl_label = "Projekt Timer"
    bl_idname = "TIME_TRACKER_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Timer"

    def draw(self, context):
        layout = self.layout
        timer = get_timer_data()
        layout.label(text=f"Project Lifetime: {format_time(timer.total_seconds)}")

class TIME_TRACKER_OT_modal(bpy.types.Operator):
    bl_idname = "view3d.time_tracker_modal"
    bl_label = "Time Tracker Modal"

    def modal(self, context, event):
        # Nur bei PRESS-Events und wenn genug Zeit vergangen ist
        if event.value in {'PRESS', 'RELEASE'} and (time.time() - _timer_state["last_activity"]) > _timer_state["min_activity_interval"]:
            if event.type in {
                'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                'MOUSEPAN', 'MOUSEROTATE', 'MOUSEZOOM'
            }:
                _update_activity()

        return {'PASS_THROUGH'}  # Events an Blender weitergeben

    def invoke(self, context, event):
        _timer_state["modal_handler"] = context.window_manager.modal_handler_add(self)
        _update_activity()
        return {'RUNNING_MODAL'}

# --- Add-on Registrierung ---
classes = (
    ProjectTimerProperties,
    TIME_TRACKER_PT_panel,
    TIME_TRACKER_OT_modal,
)

def register():
    # Klassen registrieren
    for cls in classes:
        bpy.utils.register_class(cls)

    # PropertyGroup an Szene anhängen
    bpy.types.Scene.project_timer = bpy.props.PointerProperty(type=ProjectTimerProperties)

    # Handler registrieren
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)

    # Timer registrieren (läuft alle 1 Sekunde)
    bpy.app.timers.register(check_activity, persistent=True)
    
    bpy.app.timers.register(_start_modal_operator, first_interval=0.1, persistent=True)

def unregister():
    # Timer deregistrieren
    if check_activity in bpy.app.timers.timers():
        bpy.app.timers.unregister(check_activity)

    # Handler deregistrieren
    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    
    if _timer_state.get("modal_handler"):
        _timer_state["modal_handler"] = None


    # Klassen deregistrieren
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.project_timer

if __name__ == "__main__":
    register()