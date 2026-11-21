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
    return crc32(identifier.encode()) & 0x7FFFFFFF


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

    def walk(parent, depth):
        for child in parent.children:
            if child.name == skip:
                continue
            items.append((child.name, "    " * depth + child.name, "", icon(child), number(child.name)))
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


def position_items(parent, skip=None):
    items = [(FIRST, "First", "At the top of the list", 'TRIA_UP', number(FIRST))]
    for identifier, label, icon_name, _ in siblings(parent, skip):
        items.append((identifier, "After " + label, "", icon_name, number(identifier)))
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
    (an identifier from position_items), or first."""
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


def create(scene, name, color, parent, after):
    collection = bpy.data.collections.new(name)
    collection.color_tag = color
    place(scene, collection, parent, after)
    return collection


def remove_if_unused(collection):
    if not collection.objects and not collection.children:
        bpy.data.collections.remove(collection)
