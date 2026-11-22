# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Collections: listing them, moving an object, creating and placing one."""

from contextlib import contextmanager
from zlib import crc32

import bpy

SCENE_COLLECTION = "__scene__"
FIRST = "__first__"
COLORS = ['NONE'] + ['COLOR_%02d' % n for n in range(1, 9)]


def number(identifier):
    """A fixed number per item: Blender stores a dropdown's choice as a number,
    so it must not change when the list around it does."""
    # Under 2**24: a clickable enum item keeps its number as a 32-bit float.
    return crc32(identifier.encode()) & 0xFFFFFF


def icon(collection):
    if collection is None:
        return 'SCENE_DATA'
    return 'OUTLINER_COLLECTION' if collection.color_tag == 'NONE' else 'COLLECTION_' + collection.color_tag


def from_id(scene, identifier):
    if identifier == SCENE_COLLECTION:
        return scene.collection
    return bpy.data.collections.get(identifier)


def id_of(scene, collection):
    return SCENE_COLLECTION if collection in (None, scene.collection) else collection.name


def tree_items(scene, skip=None):
    """Enum items for every collection in the scene, indented like the Outliner.
    `skip` leaves out a collection and everything inside it."""
    items = [(SCENE_COLLECTION, "Scene Collection", "", 'SCENE_DATA', number(SCENE_COLLECTION))]
    used = {items[0][4]}

    def walk(parent, depth):
        for child in parent.children:
            if child.name == skip:
                continue
            value = number(child.name)
            while value in used:  # two names with the same number: rare
                value = (value + 1) & 0xFFFFFF
            used.add(value)
            items.append((child.name, "    " * depth + child.name, "", icon(child), value))
            walk(child, depth + 1)

    walk(scene.collection, 0)
    return items


# Blender 5.3+ keeps a custom Outliner order (sort_index) where collections and
# objects mix freely. Older versions only order collections, by link order.
CUSTOM_ORDER = "sort_index" in bpy.types.CollectionChild.bl_rna.properties


def siblings(parent, skip=None):
    """What's inside `parent`, in Outliner order: (identifier, label, icon, entry)."""
    items = []
    entries = parent.collection_children if CUSTOM_ORDER else [None] * len(parent.children)
    for child, entry in zip(parent.children, entries):
        if child.name != skip:
            items.append(("C:" + child.name, child.name, icon(child), entry))
    if CUSTOM_ORDER:
        for obj, entry in zip(parent.objects, parent.collection_objects):
            items.append(("O:" + obj.name, obj.name, 'OBJECT_DATA', entry))
        items.sort(key=lambda item: item[3].sort_index)
    return items


def last_position(parent, skip=None):
    items = siblings(parent, skip)
    return items[-1][0] if items else FIRST


def move_object(obj, collection):
    if collection is None or list(obj.users_collection) == [collection]:
        return
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for other in obj.users_collection:
        if other != collection:
            other.objects.unlink(obj)


@contextmanager
def keep_view_layers():
    """Relinking collections resets their Outliner checkboxes: remember them
    and put them back."""
    flags = ("exclude", "hide_viewport", "holdout", "indirect_only")
    saved, active = {}, {}

    def walk(layer, key):
        for child in layer.children:
            saved[key + (child.collection.name,)] = [getattr(child, f) for f in flags]
            walk(child, key)

    for scene in bpy.data.scenes:
        for view_layer in scene.view_layers:
            key = (scene.name, view_layer.name)
            walk(view_layer.layer_collection, key)
            active[key] = view_layer.active_layer_collection.collection.name
    yield

    def restore(layer, key, view_layer):
        for child in layer.children:
            values = saved.get(key + (child.collection.name,))
            for flag, value in zip(flags, values or ()):
                if getattr(child, flag) != value:
                    setattr(child, flag, value)
            if child.collection.name == active[key]:
                view_layer.active_layer_collection = child
            restore(child, key, view_layer)

    for scene in bpy.data.scenes:
        for view_layer in scene.view_layers:
            key = (scene.name, view_layer.name)
            restore(view_layer.layer_collection, key, view_layer)


def place(scene, collection, parent, after):
    """Put `collection` inside `parent`, right after the sibling `after`
    (an identifier from siblings), or first."""
    for other in [scene.collection, *bpy.data.collections]:
        if other != parent and collection.name in other.children:
            other.children.unlink(collection)
    if collection.name not in parent.children:
        parent.children.link(collection)

    rest = siblings(parent, skip=collection.name)
    index = 0 if after == FIRST else next((i + 1 for i, item in enumerate(rest) if item[0] == after), len(rest))

    if CUSTOM_ORDER:
        mine = next(e for c, e in zip(parent.children, parent.collection_children) if c == collection)
        order = [item[3] for item in rest]
        order.insert(index, mine)
        for number, entry in enumerate(order):
            if entry.sort_index != number:
                entry.sort_index = number
        return

    # Older Blender: a collection's place is its link order, so relink the
    # ones that must come after it.
    later = [bpy.data.collections[item[1]] for item in rest[index:]]
    if not later:
        return
    with keep_view_layers():
        for child in [collection, *later]:
            parent.children.unlink(child)
        for child in [collection, *later]:
            parent.children.link(child)


def parent_of(scene, collection):
    for parent in [scene.collection, *bpy.data.collections]:
        if collection.name in parent.children:
            return parent
    return scene.collection


def where(scene, collection):
    """(parent, the sibling right before it, or FIRST): enough to put it back."""
    parent = parent_of(scene, collection)
    ids = [item[0] for item in siblings(parent)]
    index = ids.index("C:" + collection.name)
    return parent, ids[index - 1] if index else FIRST


def tree(scene):
    """Every collection in Outliner order: (collection, depth)."""
    rows = []

    def walk(parent, depth):
        for identifier, *_ in siblings(parent):
            if identifier.startswith("C:"):
                child = parent.children[identifier[2:]]
                rows.append((child, depth))
                walk(child, depth + 1)

    walk(scene.collection, 0)
    return rows


def moves(scene, collection):
    """The moves that do something right now: {'UP': bool, ...}."""
    parent = parent_of(scene, collection)
    nested = parent != scene.collection
    ids = [item[0] for item in siblings(parent) if item[0].startswith("C:")]
    index = ids.index("C:" + collection.name)
    return {'UP': index > 0 or nested, 'DOWN': index < len(ids) - 1 or nested,
            'OUT': nested, 'IN': index > 0}


def move(scene, collection, action, target=""):
    """Move a collection one step, like dragging it in the Outliner:
    UP / DOWN past its neighbour (out of its parent at the ends), OUT of its
    parent, IN the collection above it, or INTO `target`, at the bottom."""
    if action == 'INTO':
        parent = from_id(scene, target) or scene.collection
        place(scene, collection, parent, last_position(parent, skip=collection.name))
        return
    parent = parent_of(scene, collection)
    mine = "C:" + collection.name
    everything = [item[0] for item in siblings(parent)]
    others = [i for i in everything if i != mine]
    colls = [i for i in everything if i.startswith("C:")]
    index = colls.index(mine)
    grand = parent_of(scene, parent) if parent != scene.collection else None

    if action == 'UP' and index > 0:
        above = others.index(colls[index - 1])
        place(scene, collection, parent, others[above - 1] if above else FIRST)
    elif action == 'DOWN' and index < len(colls) - 1:
        place(scene, collection, parent, colls[index + 1])
    elif action == 'IN' and index > 0:
        new_parent = parent.children[colls[index - 1][2:]]
        place(scene, collection, new_parent, last_position(new_parent, skip=collection.name))
    elif action == 'UP' and grand is not None:  # first: go just above the parent
        around = [item[0] for item in siblings(grand)]
        at = around.index("C:" + parent.name)
        place(scene, collection, grand, around[at - 1] if at else FIRST)
    elif action in ('DOWN', 'OUT') and grand is not None:  # just below the parent
        place(scene, collection, grand, "C:" + parent.name)


def create(scene, name, color, parent, after):
    collection = bpy.data.collections.new(name)
    collection.color_tag = color
    place(scene, collection, parent, after)
    return collection


def remove_if_unused(collection):
    if not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)


def set_active(view_layer, collection):
    """Make `collection` the Outliner's active collection, if it's in this view layer."""
    def find(layer):
        if layer.collection == collection:
            return layer
        for child in layer.children:
            found = find(child)
            if found is not None:
                return found
        return None

    layer = find(view_layer.layer_collection) if collection is not None else None
    if layer is not None and view_layer.active_layer_collection != layer:
        view_layer.active_layer_collection = layer
