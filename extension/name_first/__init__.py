# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ask for a name as soon as you add an object.

Right after Shift+A (or any "Add" menu), an F2-style rename popup opens, so
the new object gets a real name instead of "Cube.001". The "Adjust Last
Operation" panel keeps working: change the cylinder's vertices afterwards and
the object keeps the name you typed.

Optionally (in the preferences) the popup also asks which collection the
object goes in, and can create a new one on the spot.
"""

import bpy
from bpy.app.handlers import persistent

from . import collection_tools as ct

# The last object we asked a name for.
state = {
    "op": 0,          # the "Add" operation, so a redo isn't taken for a new add
    "uid": 0,         # the object (session_uid survives undo)
    "default": "",    # the name Blender gave it, e.g. "Cylinder"
    "name": "",       # the name the user typed
    "collection": "", # the collection the user picked ("" = left alone)
    "before": "",     # where the object was before a new collection was made
    "new": None,      # the collection made in the popup: name, color, parent, after
    "objects": 0,     # object count at the previous update
}
quiet = []  # non-empty while the popup's fields are filled in from code
enum_items = {}  # Blender needs Python to keep dynamic enum items alive


def object_count():
    try:
        return len(bpy.data.objects)
    except AttributeError:  # bpy.data isn't available while Blender starts
        return 0


def tracked_object(context):
    obj = context.view_layer.objects.active
    return obj if obj is not None and obj.session_uid == state["uid"] else None


def save_undo_step(message):
    """Record what was just changed as an undo step. Without it Blender's undo
    history no longer matches the file, and the next undo (or a change in
    "Adjust Last Operation") can crash. It keeps that panel open."""
    window = bpy.context.window or bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        bpy.ops.ed.undo_push(message=message)


def set_quietly(wm, **values):
    quiet.append(True)
    try:
        for key, value in values.items():
            setattr(wm, key, value)
    finally:
        quiet.pop()


# -----------------------------------------------------------------------------
# What the popup's fields do. They live on the window manager, which isn't part
# of undo: Blender's own F2 field edits the object directly, which counts as a
# new undo step and closes "Adjust Last Operation".

def rename(wm, context):
    obj = tracked_object(context)
    if obj is not None and wm.name_first not in ("", obj.name):
        obj.name = wm.name_first
        state["name"] = obj.name
        save_undo_step("Name Object")


def move(wm, context):
    obj = tracked_object(context)
    if obj is not None and not quiet:
        ct.move_object(obj, ct.from_id(context.scene, wm.name_first_collection))
        state["collection"] = wm.name_first_collection
        save_undo_step("Move to Collection")


def cancel_new(context):
    """Undo the collection made in the popup: object back, collection gone."""
    wm, scene = context.window_manager, context.scene
    created = bpy.data.collections.get(state["new"]["name"]) if state["new"] else None
    obj = tracked_object(context)
    if obj is not None and created is not None:
        ct.move_object(obj, ct.from_id(scene, state["before"]))
        ct.remove_if_unused(created)
    state.update(new=None, collection=state["before"])
    set_quietly(wm, name_first_new_name="", name_first_color='NONE',
                name_first_collection=state["before"] or ct.id_of(scene, None))
    save_undo_step("Remove New Collection")


def change_parent(wm, context):
    if quiet:
        return
    parent = ct.from_id(context.scene, wm.name_first_parent)
    skip = state["new"]["name"] if state["new"] else None
    set_quietly(wm, name_first_after=ct.last_position(parent, skip))
    apply_new(wm, context)


def apply_new(wm, context):
    """Create the collection once it has a name; after that, every change to
    its name, color, parent or place applies right away."""
    obj = tracked_object(context)
    if quiet or obj is None:
        return
    scene = context.scene
    name = wm.name_first_new_name.strip()
    parent = ct.from_id(scene, wm.name_first_parent) or scene.collection
    created = bpy.data.collections.get(state["new"]["name"]) if state["new"] else None
    if created is None:
        if not name:
            return
        # New collections go inside the one shown in the list, at the end,
        # like Blender's own "New Collection".
        state["before"] = wm.name_first_collection
        parent = ct.from_id(scene, wm.name_first_collection) or scene.collection
        created = ct.create(scene, name, wm.name_first_color, parent, ct.FIRST)
        state["new"] = {"name": created.name}  # the lists below leave it out
        ct.move_object(obj, created)  # first, so it isn't counted among the siblings
        set_quietly(wm, name_first_parent=ct.id_of(scene, parent))
        set_quietly(wm, name_first_after=ct.last_position(parent, skip=created.name))
        ct.place(scene, created, parent, wm.name_first_after)
    else:
        if name and name != created.name:
            created.name = name
        created.color_tag = wm.name_first_color
        ct.place(scene, created, parent, wm.name_first_after)
    ct.move_object(obj, created)
    state["collection"] = created.name
    state["new"] = {"name": created.name, "color": created.color_tag,
                    "parent": wm.name_first_parent, "after": wm.name_first_after}
    if created.name != wm.name_first_new_name:
        set_quietly(wm, name_first_new_name=created.name)  # e.g. "Props.001"
    save_undo_step("New Collection")


def collection_enum(wm, context):
    enum_items["collection"] = ct.tree_items(context.scene)
    return enum_items["collection"]


def parent_enum(wm, context):
    skip = state["new"]["name"] if state["new"] else None
    enum_items["parent"] = ct.tree_items(context.scene, skip=skip)
    return enum_items["parent"]


def after_enum(wm, context):
    parent = ct.from_id(context.scene, wm.name_first_parent) or context.scene.collection
    skip = state["new"]["name"] if state["new"] else None
    enum_items["after"] = ct.position_items(parent, skip=skip)
    return enum_items["after"]


COLOR_ITEMS = [(c, c.replace("_", " ").title(), "", 'COLLECTION_' + c if c != 'NONE' else 'OUTLINER_COLLECTION', i)
               for i, c in enumerate(ct.COLORS)]


# -----------------------------------------------------------------------------
# Interface

def ask_collection():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon is not None and addon.preferences.ask_collection


class NAMEFIRST_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    ask_collection: bpy.props.BoolProperty(
        name="Also ask for the collection",
        description="Pick the collection the new object goes in, or make a new one, right under its name",
        default=False,
    )

    def draw(self, context):
        self.layout.prop(self, "ask_collection")


class NAMEFIRST_OT_cancel_collection(bpy.types.Operator):
    """Remove the new collection and put the object back"""
    bl_idname = "name_first.cancel_collection"
    bl_label = "Cancel New Collection"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        cancel_new(context)
        return {'FINISHED'}


def text_field(layout, wm, prop, placeholder):
    try:
        layout.prop(wm, prop, text="", placeholder=placeholder)
    except TypeError:  # Blender before 4.3
        layout.prop(wm, prop, text="")


class NAMEFIRST_PT_name(bpy.types.Panel):
    bl_space_type = 'TOPBAR'  # dummy, shown as a popup only
    bl_region_type = 'HEADER'
    bl_label = "Object Name"
    bl_ui_units_x = 14

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout
        layout.label(text="Object Name")
        created = state["new"] is not None

        row = layout.row()
        row.activate_init = True  # start typing right away
        row.label(icon='OBJECT_DATA')
        row.prop(wm, "name_first", text="")
        if not ask_collection():
            return

        if not created:
            row = layout.row()
            row.label(icon='OUTLINER_COLLECTION')
            row.prop(wm, "name_first_collection", text="")

        # Tab from the name lands here: type a name, Enter, and it exists.
        row = layout.row()
        row.label(icon='COLLECTION_NEW')
        text_field(row, wm, "name_first_new_name", "New collection")
        if not created:
            return

        # Once it exists: color, parent and place apply right away.
        row = layout.row()
        row.label(icon='BLANK1')
        row.prop(wm, "name_first_color", expand=True, icon_only=True)
        row.operator(NAMEFIRST_OT_cancel_collection.bl_idname, text="", icon='X', emboss=False)

        row = layout.row()
        row.label(icon='BLANK1')
        sub = row.row(align=True)
        sub.prop(wm, "name_first_parent", text="")
        sub.prop(wm, "name_first_after", text="")


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
        set_quietly(wm, name_first_new_name="", name_first_color='NONE',
                    name_first_collection=ct.id_of(bpy.context.scene, current))
    with bpy.context.temp_override(**window_override()):
        # With more than one field, Enter on the name mustn't close the popup.
        bpy.ops.wm.call_panel(name=NAMEFIRST_PT_name.__name__, keep_open=keep_open)


# -----------------------------------------------------------------------------
# Watching for new objects

def base_name(name):
    # "Cylinder.001" -> "Cylinder"
    stem, dot, number = name.rpartition(".")
    return stem if dot and number.isdigit() else name


def restore_name():
    # "Adjust Last Operation" undoes the add and runs it again, so the object
    # comes back under a default name, and a collection made since is gone.
    obj = bpy.context.view_layer.objects.active
    if obj is None or base_name(obj.name) != base_name(state["default"]):
        return
    scene = bpy.context.scene
    obj.name = state["name"]
    state["uid"] = obj.session_uid
    new = state["new"]
    if new and new["name"] not in bpy.data.collections:
        parent = ct.from_id(scene, new["parent"]) or scene.collection
        created = ct.create(scene, new["name"], new["color"], parent, new["after"])
        new["name"] = state["collection"] = created.name
    if state["collection"]:
        ct.move_object(obj, ct.from_id(scene, state["collection"]))
    save_undo_step("Name Object")


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
        state.update(op=op.as_pointer(), uid=obj.session_uid, default=obj.name, name=obj.name,
                     collection="", before="", new=None)
        run_soon(open_rename_popup)


@persistent
def on_load(_):
    state.update(op=0, uid=0, default="", name="", collection="", before="", new=None,
                 objects=object_count())


classes = (
    NAMEFIRST_AddonPreferences,
    NAMEFIRST_OT_cancel_collection,
    NAMEFIRST_PT_name,
)

PROPS = {
    "name_first": lambda: bpy.props.StringProperty(name="Name", update=rename),
    "name_first_collection": lambda: bpy.props.EnumProperty(
        name="Collection", items=collection_enum, update=move),
    "name_first_new_name": lambda: bpy.props.StringProperty(
        name="New Collection", description="Type a name and press Enter to make a collection for this object",
        update=apply_new),
    "name_first_color": lambda: bpy.props.EnumProperty(
        name="Color", items=COLOR_ITEMS, default='NONE', update=apply_new),
    "name_first_parent": lambda: bpy.props.EnumProperty(
        name="Inside", description="The collection it goes in", items=parent_enum, update=change_parent),
    "name_first_after": lambda: bpy.props.EnumProperty(
        name="Place", description="Where it goes in the Outliner", items=after_enum, update=apply_new),
}


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for name, make in PROPS.items():
        setattr(bpy.types.WindowManager, name, make())
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
    for name in PROPS:
        delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
