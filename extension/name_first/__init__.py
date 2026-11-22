# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ask for a name as soon as you add an object.

Right after Shift+A (or any "Add" menu), an F2-style rename popup opens, so
the new object gets a real name instead of "Cube.001". The "Adjust Last
Operation" panel keeps working: change the cylinder's vertices afterwards and
the object keeps the name you typed.

Optionally (in the preferences) a small Outliner opens next to it, to drag the
object (or anything else) where it goes, and the popup can make a new
collection for it.
"""

import bpy
from bpy.app.handlers import persistent

from . import collection_tools as ct
from . import outliner

# The last object we asked a name for.
state = {
    "op": 0,          # the "Add" operation, so a redo isn't taken for a new add
    "uid": 0,         # the object (session_uid survives undo)
    "default": "",    # the name Blender gave it, e.g. "Cylinder"
    "name": "",       # the name the user typed
    "collection": "", # the collection made for it in the popup ("" = none)
    "new": None,      # where that collection was made: name, parent, after
    "moves": [],      # what was done in the small Outliner, to do again after a redo
    "objects": 0,     # object count at the previous update
    "active": "",     # the Outliner's active collection when the object was added
}
quiet = []  # non-empty while the popup's fields are filled in from code


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


def make_collection(wm, context):
    """Enter in "New collection": make it where the object is, at the bottom
    (like Blender's own New Collection), and put the object in it."""
    obj = tracked_object(context)
    name = wm.name_first_new_name.strip()
    if quiet or obj is None or not name or state["new"]:
        return
    scene = context.scene
    parent = obj.users_collection[0] if obj.users_collection else scene.collection
    created = ct.create(scene, name, 'NONE', parent, ct.FIRST)
    ct.move_object(obj, created)
    after = ct.last_position(parent, skip=created.name)
    ct.place(scene, created, parent, after)
    state["collection"] = created.name
    state["new"] = {"name": created.name, "parent": ct.id_of(scene, parent), "after": after}
    save_undo_step("New Collection")


# -----------------------------------------------------------------------------
# What the small Outliner does. Moves are written down with "@object" and
# "@new" for the new object and collection, whose names can change.

def resolve(name):
    if name == "@object":
        return state["name"]
    if name == "@new":
        return state["collection"]
    return name


def apply_move(scene, move):
    if move[0] == 'DROP':
        _, items, parent, after = move
        items = [(kind, resolve(name), resolve(source)) for kind, name, source in items]
        target = ct.from_id(scene, resolve(parent))
        if after and after != ct.FIRST:
            after = after[:2] + resolve(after[2:])
        if target is not None:
            ct.drop(scene, items, target, after)
    else:
        _, names, tag = move
        for name in names:
            collection = bpy.data.collections.get(resolve(name))
            if collection is not None:
                collection.color_tag = tag


def stand_in(name, kind):
    """The "@" name for the new object or collection, else the name itself."""
    if kind == 'O' and name == state["name"]:
        return "@object"
    if kind == 'C' and state["collection"] and name == state["collection"]:
        return "@new"
    return name


def record(move):
    state["moves"].append(move)
    apply_move(bpy.context.scene, move)


def outliner_target():
    """The row the small Outliner highlights, or None once the user moved on."""
    context = bpy.context
    ops = context.window_manager.operators
    obj = tracked_object(context)
    if not ops or ops[-1].as_pointer() != state["op"] or obj is None or not obj.select_get():
        return None
    if state["collection"] in bpy.data.collections:
        return "C:" + state["collection"]
    return "O:" + obj.name


def outliner_drop(items, parent, after):
    items = [(kind, stand_in(name, kind), stand_in(source, 'C')) for kind, name, source in items]
    if after and after != ct.FIRST:
        after = after[:2] + stand_in(after[2:], after[0])
    record(('DROP', items, stand_in(parent, 'C'), after))
    save_undo_step("Move in Outliner")


def outliner_color(names, tag):
    record(('COLOR', [stand_in(name, 'C') for name in names], tag))
    save_undo_step("Set Color Tag")


outliner.hooks.update(target=outliner_target, drop=outliner_drop, color=outliner_color)


# -----------------------------------------------------------------------------
# Interface

def ask_collection():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon is not None and addon.preferences.ask_collection


class NAMEFIRST_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    ask_collection: bpy.props.BoolProperty(
        name="Also place it in the Outliner",
        description="Next to the name, show a small Outliner to drag the object (or anything) "
                    "where it goes, and a field to make a new collection for it",
        default=False,
    )

    def draw(self, context):
        self.layout.prop(self, "ask_collection")


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
        row = layout.row()
        row.activate_init = True  # start typing right away
        row.label(icon='OBJECT_DATA')
        row.prop(wm, "name_first", text="")
        if ask_collection() and not state["new"]:
            # Tab from the name lands here: type a name, Enter, and it exists.
            row = layout.row()
            row.label(icon='COLLECTION_NEW')
            text_field(row, wm, "name_first_new_name", "New collection")


def window_override():
    window = bpy.context.window or bpy.context.window_manager.windows[0]
    override = {"window": window}
    areas = [a for a in window.screen.areas if a.type == 'VIEW_3D']
    if areas:
        area = max(areas, key=lambda a: a.width * a.height)
        override["area"] = area
        override["region"] = next(r for r in area.regions if r.type == 'WINDOW')
    return override


def move_to_active(context):
    """New objects belong in the Outliner's active collection: put it there
    if Blender didn't."""
    layer = context.view_layer.active_layer_collection
    obj = tracked_object(context)
    usable = not (layer.exclude or layer.collection.library or layer.collection.override_library)
    if obj is not None and usable and layer.collection not in obj.users_collection:
        ct.move_object(obj, layer.collection)
        save_undo_step("Move to Collection")


def open_rename_popup():
    wm = bpy.context.window_manager
    wm.name_first = state["name"]
    set_quietly(wm, name_first_new_name="")
    if ask_collection():
        move_to_active(bpy.context)
    override = window_override()
    with bpy.context.temp_override(**override):
        # With two fields, a change mustn't close the popup, or Tab can't reach the second.
        bpy.ops.wm.call_panel(name=NAMEFIRST_PT_name.__name__, keep_open=ask_collection())
    if ask_collection():
        # Opened after the popup, so it sees the mouse first.
        outliner.open_outliner(override)


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
    state["name"], state["uid"] = obj.name, obj.session_uid
    new = state["new"]
    if new and new["name"] not in bpy.data.collections:
        parent = ct.from_id(scene, new["parent"]) or scene.collection
        created = ct.create(scene, new["name"], 'NONE', parent, new["after"])
        state["collection"] = created.name
    if state["collection"]:
        ct.move_object(obj, ct.from_id(scene, state["collection"]))
    for move in state["moves"]:
        apply_move(scene, move)
    # Redoing can also leave another collection active in the Outliner.
    ct.set_active(bpy.context.view_layer, ct.from_id(scene, state["active"]))
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
        if state["name"] != state["default"] or state["collection"] or state["moves"]:
            run_soon(restore_name)
    elif op.bl_idname.endswith("_add") and state["objects"] > previous and obj.select_get():
        # A new object, not a modifier or material slot added to an existing one.
        state.update(op=op.as_pointer(), uid=obj.session_uid, default=obj.name, name=obj.name,
                     collection="", new=None, moves=[],
                     active=ct.id_of(scene, bpy.context.view_layer.active_layer_collection.collection))
        run_soon(open_rename_popup)


@persistent
def on_load(_):
    state.update(op=0, uid=0, default="", name="", collection="", new=None, moves=[], active="",
                 objects=object_count())


classes = (
    NAMEFIRST_AddonPreferences,
    NAMEFIRST_PT_name,
    *outliner.classes,
)

PROPS = {
    "name_first": lambda: bpy.props.StringProperty(name="Name", update=rename),
    "name_first_new_name": lambda: bpy.props.StringProperty(
        name="New Collection", description="Type a name and press Enter to make a collection for this object",
        update=make_collection),
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
