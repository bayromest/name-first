# SPDX-FileCopyrightText: 2026 Bayrem
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A small Outliner drawn over the 3D view, next to the name popup.

It looks and works like Blender's Outliner: drag collections and objects
(one, or several with Ctrl / Shift) above, below or into a collection, open
and close branches, color the selected collections. It is drawn by hand
because Blender's real Outliner closes "Adjust Last Operation" on every drag,
and add-ons can't put draggable rows in a popup.

The add-on fills `hooks` with what the Outliner needs from it.
"""

import time

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import collection_tools as ct

ROOT = "S:"
hooks = {
    "target": lambda: None,  # identifier of the row to highlight ("C:Props", "O:Chair"), or None to close
    "drop": lambda items, parent, after: None,
    "color": lambda names, tag: None,
}


# -----------------------------------------------------------------------------
# Looks

def scale():
    return bpy.context.preferences.system.ui_scale


def rgba(color, alpha=1.0):
    color = tuple(color)
    return color if len(color) == 4 else color + (alpha,)


def theme():
    t = bpy.context.preferences.themes[0]
    outliner, ui = t.outliner, t.user_interface
    text = rgba(outliner.space.text)
    return {
        "back": rgba(outliner.space.back),
        "text": text,
        "text_hi": rgba(outliner.space.text_hi),
        "dim": text[:3] + (0.45,),
        "selected": rgba(getattr(outliner, "selected_highlight", (0.2, 0.33, 0.55)), 1.0),
        "active": rgba(getattr(outliner, "active_highlight", (0.25, 0.4, 0.65)), 1.0),
        "alternate": text[:3] + (0.025,),
        "hover": text[:3] + (0.06,),
        "tags": [rgba(c.color) for c in t.collection_color],
        "object": rgba(getattr(ui, "icon_object", (0.93, 0.57, 0.28, 1))),
        "drop": rgba(getattr(ui, "wcol_regular").inner_sel, 1.0)[:3] + (1.0,),
    }


_shader = None


def shader():
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    return _shader


def draw(kind, points, color):
    gpu.state.blend_set('ALPHA')  # drawing text turns blending off
    sh = shader()
    sh.uniform_float("color", color)
    batch_for_shader(sh, kind, {"pos": points}).draw(sh)


def rect(x, y, w, h, color):
    draw('TRIS', [(x, y), (x + w, y), (x + w, y + h), (x, y), (x + w, y + h), (x, y + h)], color)


def outline(points, color):
    draw('LINES', [p for a, b in zip(points, points[1:] + points[:1]) for p in (a, b)], color)


def collection_icon(x, y, size, color):
    """Blender's collection icon: a box with a lid."""
    u = size / 16
    rect(x + 2 * u, y + 10 * u, 12 * u, 3 * u, color)  # lid
    outline([(x + 3 * u, y + 3 * u), (x + 13 * u, y + 3 * u),
             (x + 13 * u, y + 9 * u), (x + 3 * u, y + 9 * u)], color)
    rect(x + 6 * u, y + 6 * u, 4 * u, 1.2 * u, color)  # handle


def object_icon(x, y, size, color, kind):
    u = size / 16
    if kind in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'CURVES', 'POINTCLOUD', 'VOLUME', 'GREASEPENCIL'}:
        outline([(x + 3 * u, y + 12 * u), (x + 13 * u, y + 12 * u), (x + 8 * u, y + 3 * u)], color)
    else:
        outline([(x + 8 * u, y + 13 * u), (x + 13 * u, y + 8 * u),
                 (x + 8 * u, y + 3 * u), (x + 3 * u, y + 8 * u)], color)


def disclosure(x, y, size, is_open, color):
    u = size / 16
    if is_open:
        draw('TRIS', [(x + 4 * u, y + 10 * u), (x + 12 * u, y + 10 * u), (x + 8 * u, y + 5 * u)], color)
    else:
        draw('TRIS', [(x + 6 * u, y + 12 * u), (x + 6 * u, y + 4 * u), (x + 11 * u, y + 8 * u)], color)


def text(x, y, value, size, color, width):
    blf.size(0, size)
    blf.color(0, *color)
    while value and blf.dimensions(0, value)[0] > width:
        value = value[:-2] + "…" if len(value) > 2 else ""
    blf.position(0, x, y, 0)
    blf.draw(0, value)


# -----------------------------------------------------------------------------
# What's shown

def build_rows(scene, expanded):
    """The visible rows: dicts with id ("S:", "C:name", "O:name"), name, kind,
    depth, parent (a collection id, as from_id takes), children, open."""
    rows = [{"id": ROOT, "name": "Scene Collection", "kind": 'S', "depth": 0,
             "parent": None, "children": True, "open": True}]

    def walk(collection, collection_id, depth):
        for identifier, name in ct.contents(collection):
            if identifier.startswith("C:"):
                child = collection.children.get(name)
                if child is None:
                    continue
                has = bool(child.children) or bool(child.objects)
                is_open = has and name in expanded
                rows.append({"id": identifier, "name": name, "kind": 'C', "depth": depth,
                             "parent": collection_id, "children": has, "open": is_open})
                if is_open:
                    walk(child, name, depth + 1)
            else:
                rows.append({"id": identifier, "name": name, "kind": 'O', "depth": depth,
                             "parent": collection_id, "children": False, "open": False})

    walk(scene.collection, ct.SCENE_COLLECTION, 1)
    return rows


def path_to(scene, identifier):
    """The collections to open so `identifier` is visible."""
    if identifier.startswith("C:"):
        collection = bpy.data.collections.get(identifier[2:])
        return {c.name for c in ct.ancestors(scene, collection)} if collection else set()
    obj = bpy.data.objects.get(identifier[2:])
    found = set()
    for collection in (obj.users_collection if obj else ()):
        if collection != scene.collection:
            found |= {collection.name} | {c.name for c in ct.ancestors(scene, collection)}
    return found


# -----------------------------------------------------------------------------
# The operator

class NAMEFIRST_OT_outliner(bpy.types.Operator):
    """A small Outliner to place the new object or collection"""
    bl_idname = "name_first.outliner"
    bl_label = "Name First Outliner"
    bl_options = {'INTERNAL'}

    running = False

    def invoke(self, context, event):
        cls = type(self)
        # The 3D view under the mouse, where the name popup opened.
        areas = [a for a in context.window.screen.areas if a.type == 'VIEW_3D'
                 and a.x <= event.mouse_x < a.x + a.width and a.y <= event.mouse_y < a.y + a.height]
        area = areas[0] if areas else context.area
        if cls.running or area is None or area.type != 'VIEW_3D':
            return {'CANCELLED'}
        cls.running = True
        self.area = area
        self.region = next(r for r in area.regions if r.type == 'WINDOW')
        self.expanded = set()
        self.selected = []      # row ids, in click order
        self.anchor = None      # for Shift+click ranges
        self.target = None      # the highlighted row, from the add-on
        self.scroll = 0
        self.press = None       # (x, y, row id, modifiers) while the button is down
        self.drag = None        # the dragged row ids
        self.drop = None        # (row id, 'BEFORE' | 'AFTER' | 'INTO')
        self.hover = None
        self.hover_since = 0.0
        self.trouble = 0        # timer ticks the add-on asked to close
        self.mouse = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        self.place_near(*self.mouse)
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self.paint, (), 'WINDOW', 'POST_PIXEL')
        self.timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.refresh(context)
        return {'RUNNING_MODAL'}

    # --- layout ---------------------------------------------------------------

    def place_near(self, mx, my):
        """Right of the name popup (which opens under the mouse), or left of it."""
        s = scale()
        self.width = 260 * s
        gap = 160 * s
        x = mx + gap if mx + gap + self.width < self.region.width - 10 * s else mx - gap - self.width
        self.x = max(10 * s, x)
        self.top = min(self.region.height - 10 * s, my + 60 * s)

    def metrics(self):
        s = scale()
        return {"s": s, "row": 20 * s, "indent": 16 * s, "icon": 16 * s, "header": 24 * s,
                "font": bpy.context.preferences.ui_styles[0].widget.points * s}

    def rows(self, context):
        return build_rows(context.scene, self.expanded)

    def frame(self, count):
        """(x, y, w, h) of the panel and the height the rows can use."""
        m = self.metrics()
        wanted = count * m["row"]
        room = max(m["row"] * 3, self.top - 10 * m["s"] - m["header"])
        visible = min(wanted, room)
        self.scroll = max(0, min(self.scroll, wanted - visible))
        h = visible + m["header"]
        return self.x, self.top - h, self.width, h, visible

    def row_at(self, context, mx, my):
        """(row, index, fraction from the bottom of the row) under the mouse."""
        rows = self.rows(context)
        x, y, w, h, visible = self.frame(len(rows))
        m = self.metrics()
        list_top = self.top - m["header"]
        if not (x <= mx <= x + w and list_top - visible <= my <= list_top):
            return None, None, 0
        index = int((list_top - my + self.scroll) // m["row"])
        if not 0 <= index < len(rows):
            return None, None, 0
        bottom = list_top + self.scroll - (index + 1) * m["row"]
        return rows[index], index, (my - bottom) / m["row"]

    def inside(self, context, mx, my):
        x, y, w, h, _ = self.frame(len(self.rows(context)))
        return x <= mx <= x + w and y <= my <= y + h

    def swatch_at(self, context, mx, my):
        """The color tag under the mouse in the header, or None."""
        x, y, w, h, _ = self.frame(len(self.rows(context)))
        m = self.metrics()
        size = 14 * m["s"]
        if not (y + h - m["header"] <= my <= y + h):
            return None
        for i, tag in enumerate(ct.COLORS):
            sx = x + w - (len(ct.COLORS) - i) * (size + 3 * m["s"]) - 4 * m["s"]
            if sx <= mx <= sx + size:
                return tag
        return None

    # --- drawing ----------------------------------------------------------------

    def paint(self):
        context = bpy.context
        try:
            if context.area is None or context.area.as_pointer() != self.area.as_pointer():
                return
            self.paint_panel(context)
        except Exception:  # never let a drawing error take Blender's redraw down
            import traceback
            traceback.print_exc()

    def paint_panel(self, context):
        t, m = theme(), self.metrics()
        s, row_h = m["s"], m["row"]
        rows = self.rows(context)
        x, y, w, h, visible = self.frame(len(rows))
        gpu.state.blend_set('ALPHA')

        rect(x + 3 * s, y - 3 * s, w, h, (0, 0, 0, 0.25))  # shadow
        rect(x, y, w, h, t["back"])
        outline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], (0, 0, 0, 0.6))

        # Header: a hint, and the color tags for the selected collections.
        header_y = y + h - m["header"]
        rect(x, header_y, w, m["header"], tuple(c * 0.85 for c in t["back"][:3]) + (1,))
        text(x + 8 * s, header_y + 7 * s, "Drag to move", m["font"] * 0.9, t["dim"], w * 0.4)
        colorable = any(r.startswith("C:") for r in self.selected)
        size = 14 * s
        for i, tag in enumerate(ct.COLORS):
            sx = x + w - (len(ct.COLORS) - i) * (size + 3 * s) - 4 * s
            sy = header_y + (m["header"] - size) / 2
            color = t["text"] if tag == 'NONE' else t["tags"][int(tag[-2:]) - 1]
            if not colorable:
                color = color[:3] + (0.3,)
            collection_icon(sx, sy, size, color)

        # Rows, clipped to the list area.
        list_top = header_y
        gpu.state.scissor_test_set(True)
        # The 3D view draws overlays in its own buffer: region coordinates.
        gpu.state.scissor_set(int(x), int(list_top - visible), int(w), int(visible))
        try:
            for index, row in enumerate(rows):
                top = list_top + self.scroll - index * row_h
                bottom = top - row_h
                if top < list_top - visible or bottom > list_top:
                    continue
                self.paint_row(t, m, row, index, x, bottom, w)
            self.paint_drop(t, m, rows, x, list_top, w)
        finally:
            gpu.state.scissor_test_set(False)
        if self.drag:
            # A small tag under the cursor, like the Outliner's drag tooltip.
            label = self.drag[0][2:] if len(self.drag) == 1 else "%d items" % len(self.drag)
            blf.size(0, m["font"])
            tw = min(blf.dimensions(0, label)[0], 200 * s)
            lx, ly = self.mouse[0] + 16 * s, self.mouse[1] - 26 * s
            rect(lx - 6 * s, ly - 5 * s, tw + 12 * s, 18 * s, t["back"][:3] + (0.95,))
            text(lx, ly, label, m["font"], t["text_hi"], 200 * s)
        gpu.state.blend_set('NONE')

    def paint_row(self, t, m, row, index, x, bottom, w):
        s, row_h, size = m["s"], m["row"], m["icon"]
        if index % 2:
            rect(x, bottom, w, row_h, t["alternate"])
        if row["id"] in self.selected:
            rect(x, bottom, w, row_h, t["active"] if row["id"] == self.target else t["selected"])
        elif row["id"] == self.hover and not self.drag:
            rect(x, bottom, w, row_h, t["hover"])
        left = x + 4 * s + row["depth"] * m["indent"]
        icon_y = bottom + (row_h - size) / 2
        if row["children"]:
            disclosure(left, icon_y, size, row["open"], t["text"][:3] + (0.7,))
        left += size
        name, color = row["name"], t["text"]
        if row["kind"] == 'O':
            obj = bpy.data.objects.get(name)
            object_icon(left, icon_y, size, t["object"], obj.type if obj else 'MESH')
        else:
            collection = bpy.data.collections.get(name) if row["kind"] == 'C' else None
            tag = collection.color_tag if collection else 'NONE'
            icon_color = t["text"] if tag == 'NONE' else t["tags"][int(tag[-2:]) - 1]
            collection_icon(left, icon_y, size, icon_color)
        if row["id"] == self.target:
            color = t["text_hi"]
        text(left + size + 4 * s, bottom + 6 * s, name, m["font"], color, x + w - left - size - 10 * s)

    def paint_drop(self, t, m, rows, x, list_top, w):
        if not (self.drag and self.drop):
            return
        row_id, where = self.drop
        index = next((i for i, r in enumerate(rows) if r["id"] == row_id), None)
        if index is None:
            return
        s, row_h = m["s"], m["row"]
        top = list_top + self.scroll - index * row_h
        row = rows[index]
        if where == 'INTO':
            outline([(x + 1, top - row_h + 1), (x + w - 1, top - row_h + 1),
                     (x + w - 1, top - 1), (x + 1, top - 1)], t["drop"])
            return
        line_y = top if where == 'BEFORE' else top - row_h
        left = x + 4 * s + row["depth"] * m["indent"] + m["icon"]
        rect(left, line_y - 1 * s, x + w - left - 4 * s, 2 * s, t["drop"])

    # --- events -----------------------------------------------------------------

    def refresh(self, context):
        """Follow the add-on: highlight its row, and open the way to it."""
        target = hooks["target"]()
        if target and target != self.target:
            self.target = target
            self.selected, self.anchor = [target], target
            self.expanded |= path_to(context.scene, target)
            if target.startswith("C:"):
                self.expanded.add(target[2:])  # show what's in the new collection
            self.area.tag_redraw()

    def finish(self, context):
        type(self).running = False
        bpy.types.SpaceView3D.draw_handler_remove(self.handle, 'WINDOW')
        context.window_manager.event_timer_remove(self.timer)
        try:
            self.area.tag_redraw()
        except ReferenceError:  # the area was closed
            pass
        return {'FINISHED', 'PASS_THROUGH'}

    def modal(self, context, event):
        try:
            return self.handle_event(context, event)
        except Exception:
            import traceback
            traceback.print_exc()
            return self.finish(context)

    def handle_event(self, context, event):
        if event.type == 'TIMER':
            return self.tick(context)
        if event.type == 'ESC':
            return self.finish(context)

        mx, my = event.mouse_x - self.region.x, event.mouse_y - self.region.y
        self.mouse = (mx, my)
        inside = self.inside(context, mx, my)

        if event.type == 'MOUSEMOVE':
            return self.mouse_move(context, mx, my, inside)
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and inside:
            self.scroll += (-1 if event.type == 'WHEELUPMOUSE' else 1) * self.metrics()["row"] * 2
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE' and (inside or self.drag):
            self.drag = self.press = self.drop = None
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and inside:
                return self.mouse_press(context, event, mx, my)
            if event.value == 'RELEASE' and (self.press or self.drag):
                return self.mouse_release(context, event, mx, my)
        return {'PASS_THROUGH'}

    def tick(self, context):
        target = hooks["target"]()
        self.trouble = 0 if target else self.trouble + 1
        if self.trouble > 5:  # half a second: give a redo time to finish
            return self.finish(context)
        if target:
            self.refresh(context)
        # Hovering a closed collection while dragging opens it, like the Outliner.
        if self.drag and self.drop and self.drop[1] == 'INTO' and time.time() - self.hover_since > 0.7:
            name = self.drop[0][2:]
            if self.drop[0].startswith("C:") and name not in self.expanded:
                self.expanded.add(name)
                self.area.tag_redraw()
        return {'PASS_THROUGH'}

    def mouse_move(self, context, mx, my, inside):
        row, _, fraction = self.row_at(context, mx, my)
        hover = row["id"] if row else None
        if hover != self.hover:
            self.hover, self.hover_since = hover, time.time()
            self.area.tag_redraw()
        if self.press and not self.drag:
            px, py, row_id, _ = self.press
            if abs(mx - px) + abs(my - py) > 6 * scale() and row_id != ROOT:
                if row_id not in self.selected:
                    self.selected, self.anchor = [row_id], row_id
                order = [r["id"] for r in self.rows(context)]
                self.drag = sorted((r for r in self.selected if r != ROOT and r in order), key=order.index)
        if self.drag:
            self.drop = self.drop_target(context, row, fraction)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'} if inside else {'PASS_THROUGH'}

    def mouse_press(self, context, event, mx, my):
        row, _, _ = self.row_at(context, mx, my)
        tag = self.swatch_at(context, mx, my)
        if tag is not None:
            names = [r[2:] for r in self.selected if r.startswith("C:")]
            if names:
                hooks["color"](names, tag)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if row is None:
            return {'RUNNING_MODAL'}
        m = self.metrics()
        left = self.x + 4 * m["s"] + row["depth"] * m["indent"]
        if row["children"] and row["kind"] == 'C' and left <= mx <= left + m["icon"]:
            self.expanded ^= {row["name"]}
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        self.press = (mx, my, row["id"], (event.ctrl, event.shift))
        return {'RUNNING_MODAL'}

    def mouse_release(self, context, event, mx, my):
        if self.drag:
            if self.drop:
                self.do_drop(context)
            self.drag = self.drop = self.press = None
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        _, _, row_id, (ctrl, shift) = self.press
        self.press = None
        order = [r["id"] for r in self.rows(context)]
        if shift and self.anchor in order:
            a, b = sorted((order.index(self.anchor), order.index(row_id)))
            self.selected = order[a:b + 1]
        elif ctrl:
            if row_id in self.selected:
                self.selected.remove(row_id)
            else:
                self.selected.append(row_id)
            self.anchor = row_id
        else:
            self.selected, self.anchor = [row_id], row_id
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    # --- dropping ---------------------------------------------------------------

    def drop_target(self, context, row, fraction):
        """Where the dragged rows would go: (row id, 'BEFORE' | 'AFTER' | 'INTO')."""
        if row is None or row["id"] in self.drag:
            return None
        if row["kind"] == 'S':
            where = 'INTO'
        elif row["kind"] == 'C':
            where = 'BEFORE' if fraction > 0.75 else 'AFTER' if fraction < 0.25 else 'INTO'
        else:
            where = 'BEFORE' if fraction >= 0.5 else 'AFTER'
        # Without Blender 5.3's free order, only collections sort among collections.
        if where != 'INTO' and not ct.CUSTOM_ORDER and (
                row["kind"] == 'O' or any(d.startswith("O:") for d in self.drag)):
            return (row["id"], 'INTO') if row["kind"] == 'C' else None
        # A collection can't go inside itself.
        parent_id = self.drop_parent(row, where)
        parent = ct.from_id(context.scene, parent_id)
        if parent is None:
            return None
        for item in self.drag:
            if item.startswith("C:"):
                dragged = bpy.data.collections.get(item[2:])
                if dragged is not None and (dragged == parent or dragged in ct.ancestors(context.scene, parent)):
                    return None
        return (row["id"], where)

    def drop_parent(self, row, where):
        if where == 'INTO':
            return ct.SCENE_COLLECTION if row["kind"] == 'S' else row["name"]
        if where == 'AFTER' and row["kind"] == 'C' and row["open"]:
            return row["name"]  # under an open collection: first inside it
        return row["parent"]

    def do_drop(self, context):
        rows = {r["id"]: r for r in self.rows(context)}
        row_id, where = self.drop
        row = rows[row_id]
        parent_id = self.drop_parent(row, where)
        if where == 'INTO':
            after = None
        elif where == 'AFTER' and row["kind"] == 'C' and row["open"]:
            after = ct.FIRST
        elif where == 'AFTER':
            after = row_id
        else:  # BEFORE: after whatever comes before it, skipping what's dragged
            parent = ct.from_id(context.scene, parent_id)
            before = [i for i, _ in ct.contents(parent) if i not in self.drag]
            if not ct.CUSTOM_ORDER:
                before = [i for i in before if i.startswith("C:")]
            at = before.index(row_id) if row_id in before else 0
            after = before[at - 1] if at else ct.FIRST
        items = [(d[0], d[2:], rows[d]["parent"]) for d in self.drag if d in rows]
        hooks["drop"](items, parent_id, after)
        if where == 'INTO' and row["kind"] == 'C':
            self.expanded.add(row["name"])


classes = (NAMEFIRST_OT_outliner,)


def open_outliner(override):
    with bpy.context.temp_override(**override):
        bpy.ops.name_first.outliner('INVOKE_DEFAULT')
