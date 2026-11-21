# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ask for a name as soon as you add an object.

Right after Shift+A (or any "Add" menu), an F2-style rename popup opens, so
the new object gets a real name instead of "Cube.001". The "Adjust Last
Operation" panel keeps working: change the cylinder's vertices afterwards and
the object keeps the name you typed.
"""

import bpy
from bpy.app.handlers import persistent

# The last object we asked a name for.
state = {
    "op": 0,          # the "Add" operation, so a redo isn't taken for a new add
    "uid": 0,         # the object (session_uid survives undo)
    "default": "",    # the name Blender gave it, e.g. "Cylinder"
    "name": "",       # the name the user typed
    "objects": 0,     # object count at the previous update
}


def object_count():
    try:
        return len(bpy.data.objects)
    except AttributeError:  # bpy.data isn't available while Blender starts
        return 0


def rename(wm, context):
    # Blender's own F2 field edits the object directly, which counts as a new
    # undo step and closes "Adjust Last Operation". This field lives on the
    # window manager (never part of undo), and the object is renamed from here.
    obj = context.view_layer.objects.active
    if obj is not None and obj.session_uid == state["uid"] and wm.name_first not in ("", obj.name):
        obj.name = wm.name_first
        state["name"] = obj.name


class NAMEFIRST_PT_name(bpy.types.Panel):
    bl_space_type = 'TOPBAR'  # dummy, shown as a popup only
    bl_region_type = 'HEADER'
    bl_label = "Object Name"
    bl_ui_units_x = 14

    def draw(self, context):
        layout = self.layout
        layout.label(text="Object Name")
        row = layout.row()
        row.activate_init = True  # start typing right away
        row.label(icon='OBJECT_DATA')
        row.prop(context.window_manager, "name_first", text="")


def window_override():
    window = bpy.context.window or bpy.context.window_manager.windows[0]
    override = {"window": window}
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            override["area"] = area
            override["region"] = next(r for r in area.regions if r.type == 'WINDOW')
            break
    return override


def open_rename_popup():
    bpy.context.window_manager.name_first = state["name"]
    with bpy.context.temp_override(**window_override()):
        bpy.ops.wm.call_panel(name=NAMEFIRST_PT_name.__name__, keep_open=False)


def base_name(name):
    # "Cylinder.001" -> "Cylinder"
    stem, dot, number = name.rpartition(".")
    return stem if dot and number.isdigit() else name


def restore_name():
    # "Adjust Last Operation" re-creates the object under a default name.
    obj = bpy.context.view_layer.objects.active
    if obj is not None and base_name(obj.name) == base_name(state["default"]):
        obj.name = state["name"]
        state["uid"] = obj.session_uid


def run_soon(func):
    # Handlers can't rename or open popups themselves; a timer runs right after.
    if not bpy.app.timers.is_registered(func):
        bpy.app.timers.register(func)


@persistent
def on_update(scene, depsgraph):
    previous, state["objects"] = state["objects"], object_count()

    op = bpy.context.window_manager.operators[-1:]
    obj = bpy.context.view_layer.objects.active
    if not op or obj is None or obj.mode != 'OBJECT':
        return
    op = op[0]

    if obj.session_uid == state["uid"]:
        state["name"] = obj.name  # renamed some other way, e.g. in the Outliner
    elif op.as_pointer() == state["op"]:
        # Same operation but a different object: it was redone.
        if state["name"] != state["default"]:
            run_soon(restore_name)
    elif op.bl_idname.endswith("_add") and state["objects"] > previous and obj.select_get():
        # A new object, not a modifier or material slot added to an existing one.
        state.update(op=op.as_pointer(), uid=obj.session_uid, default=obj.name, name=obj.name)
        run_soon(open_rename_popup)


@persistent
def on_load(_):
    state.update(op=0, uid=0, default="", name="", objects=object_count())


def register():
    bpy.utils.register_class(NAMEFIRST_PT_name)
    bpy.types.WindowManager.name_first = bpy.props.StringProperty(
        name="Name", options={'SKIP_SAVE'}, update=rename)
    if bpy.app.background:
        return
    on_load(None)
    bpy.app.handlers.depsgraph_update_post.append(on_update)
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    for handlers, func in (
        (bpy.app.handlers.depsgraph_update_post, on_update),
        (bpy.app.handlers.load_post, on_load),
    ):
        if func in handlers:
            handlers.remove(func)
    del bpy.types.WindowManager.name_first
    bpy.utils.unregister_class(NAMEFIRST_PT_name)
