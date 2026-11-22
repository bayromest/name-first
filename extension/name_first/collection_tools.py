# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Collections: listing them, moving an object, creating and placing one."""

from contextlib import contextmanager

import bpy

SCENE_COLLECTION = "__scene__"
FIRST = "__first__"
COLORS = ['NONE'] + ['COLOR_%02d' % n for n in range(1, 9)]


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


def order(parent, mine, after):
    """Blender 5.3+: put the item `mine` right after `after` (or FIRST) among
    what's inside `parent`, by renumbering the Outliner order."""
    items = siblings(parent)
    entry = next(item[3] for item in items if item[0] == mine)
    rest = [item for item in items if item[0] != mine]
    index = 0 if after == FIRST else next((i + 1 for i, item in enumerate(rest) if item[0] == after), len(rest))
    entries = [item[3] for item in rest]
    entries.insert(index, entry)
    for number, each in enumerate(entries):
        if each.sort_index != number:
            each.sort_index = number


def place(scene, collection, parent, after):
    """Put `collection` inside `parent`, right after the sibling `after`
    (an identifier from siblings), or first."""
    for other in [scene.collection, *bpy.data.collections]:
        if other != parent and collection.name in other.children:
            other.children.unlink(collection)
    if collection.name not in parent.children:
        parent.children.link(collection)

    if CUSTOM_ORDER:
        order(parent, "C:" + collection.name, after)
        return

    # Older Blender: a collection's place is its link order, so relink the
    # ones that must come after it.
    rest = siblings(parent, skip=collection.name)
    index = 0 if after == FIRST else next((i + 1 for i, item in enumerate(rest) if item[0] == after), len(rest))
    later = [bpy.data.collections[item[1]] for item in rest[index:]]
    if not later:
        return
    with keep_view_layers():
        for child in [collection, *later]:
            parent.children.unlink(child)
        for child in [collection, *later]:
            parent.children.link(child)


def place_object(obj, source, parent, after):
    """Move `obj` from `source` into `parent`, right after `after` (5.3+;
    before that, objects are always sorted by name)."""
    if obj.name not in parent.objects:
        parent.objects.link(obj)
    if source is not None and source != parent and obj.name in source.objects:
        source.objects.unlink(obj)
    if CUSTOM_ORDER:
        order(parent, "O:" + obj.name, after)


def contents(parent):
    """What the Outliner shows inside `parent`, in its order: (identifier, name)."""
    if CUSTOM_ORDER:
        return [(item[0], item[1]) for item in siblings(parent)]
    return ([("C:" + c.name, c.name) for c in parent.children]
            + [("O:" + o.name, o.name) for o in sorted(parent.objects, key=lambda o: o.name)])


def parent_of(scene, collection):
    for parent in [scene.collection, *bpy.data.collections]:
        if collection.name in parent.children:
            return parent
    return scene.collection


def ancestors(scene, collection):
    """The collections above `collection`, up to the scene's."""
    found = []
    while collection is not None and collection != scene.collection:
        collection = parent_of(scene, collection)
        found.append(collection)
    return found


def drop(scene, items, parent, after=None):
    """Move dragged items, keeping their order, into `parent` right after
    `after` (None: at the bottom). `items`: (kind 'C' or 'O', name, source id)."""
    dragged = {kind + ":" + name for kind, name, _ in items}
    if after is None:
        rest = [item[0] for item in siblings(parent) if item[0] not in dragged]
        after = rest[-1] if rest else FIRST
    for kind, name, source in items:
        if kind == 'C':
            collection = bpy.data.collections.get(name)
            if collection is None or collection == parent or collection in ancestors(scene, parent):
                continue  # gone, or it would go inside itself
            place(scene, collection, parent, after)
        else:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            place_object(obj, from_id(scene, source), parent, after)
        after = kind + ":" + name


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
