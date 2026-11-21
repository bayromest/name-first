# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ask for a name as soon as you add an object.

Right after Shift+A (or any "Add" menu), an F2-style rename popup opens, so
the new object gets a real name instead of "Cube.001". The "Adjust Last
Operation" panel keeps working: change the cylinder's vertices afterwards and
the object keeps the name you typed.

Optionally (in the preferences) the popup also asks which collection the
object goes in, for when you forgot which one was active.
"""

import bpy
from bpy.app.handlers import persistent

# The last object we asked a name for.
state = {
    "op": 0,          # the "Add" operation, so a redo isn't taken for a new add
    "uid": 0,         # the object (session_uid survives undo)
    "default": "",    # the name Blender gave it, e.g. "Cylinder"
    "name": "",       # the name the user typed
    "collection": "", # the collection the user picked ("" = left alone)
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


SCENE_COLLECTION = "__scene__"
collection_items = []  # Blender needs Python to keep dynamic enum items alive


def collection_enum(wm, context):
    scene = context.scene
    collection_items.clear()
    collection_items.append((SCENE_COLLECTION, "Scene Collection", "", 'SCENE_DATA', 0))

    def walk(parent, depth):
        for child in parent.children:
            icon = 'OUTLINER_COLLECTION' if child.color_tag == 'NONE' else 'COLLECTION_' + child.color_tag
            label = "    " * depth + child.name
            collection_items.append((child.name, label, "", icon, len(collection_items)))
            walk(child, depth + 1)

    walk(scene.collection, 0)
    return collection_items


def collection_from_id(identifier):
    if identifier == SCENE_COLLECTION:
        return bpy.context.scene.collection
    return bpy.data.collections.get(identifier)


def move_to(obj, collection):
    if collection is None or list(obj.users_collection) == [collection]:
        return
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for other in obj.users_collection:
        if other != collection:
            other.objects.unlink(obj)


def move(wm, context):
    # Same trick as rename(): the choice lives on the window manager.
    obj = context.view_layer.objects.active
    if obj is not None and obj.session_uid == state["uid"]:
        move_to(obj, collection_from_id(wm.name_first_collection))
        state["collection"] = wm.name_first_collection


def ask_collection():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon is not None and addon.preferences.ask_collection


class NAMEFIRST_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    ask_collection: bpy.props.BoolProperty(
        name="Also ask for the collection",
        description="Pick the collection the new object goes in, right under its name",
        default=False,
    )

    def draw(self, context):
        self.layout.prop(self, "ask_collection")


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
        if ask_collection():
            row = layout.row()
            row.label(icon='OUTLINER_COLLECTION')
            row.prop(context.window_manager, "name_first_collection", text="")


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
    wm = bpy.context.window_manager
    wm.name_first = state["name"]
    keep_open = ask_collection()
    if keep_open:
        obj = bpy.context.view_layer.objects.active
        current = obj.users_collection[0] if obj and obj.users_collection else None
        scene_collection = bpy.context.scene.collection
        wm.name_first_collection = SCENE_COLLECTION if current in (None, scene_collection) else current.name
    with bpy.context.temp_override(**window_override()):
        # With a second field, Enter on the name mustn't close the popup.
        bpy.ops.wm.call_panel(name=NAMEFIRST_PT_name.__name__, keep_open=keep_open)


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
        if state["collection"]:
            move_to(obj, collection_from_id(state["collection"]))


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
        if state["name"] != state["default"] or state["collection"]:
            run_soon(restore_name)
    elif op.bl_idname.endswith("_add") and state["objects"] > previous and obj.select_get():
        # A new object, not a modifier or material slot added to an existing one.
        state.update(op=op.as_pointer(), uid=obj.session_uid, default=obj.name, name=obj.name, collection="")
        run_soon(open_rename_popup)


@persistent
def on_load(_):
    state.update(op=0, uid=0, default="", name="", collection="", objects=object_count())


classes = (
    NAMEFIRST_AddonPreferences,
    NAMEFIRST_PT_name,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.name_first = bpy.props.StringProperty(name="Name", update=rename)
    wm.name_first_collection = bpy.props.EnumProperty(
        name="Collection", items=collection_enum, update=move)
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
    del bpy.types.WindowManager.name_first_collection
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
