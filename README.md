<div align="center">

<img src="icons/name-first.png" width="128" alt="Name First icon: a text field with a cursor">

# name-first

**Name every object the moment you add it, like a variable. No more `Cube.001`.**

A Blender extension · every platform · zero settings

[![Stars](https://img.shields.io/github/stars/bayromest/name-first?style=flat&logo=github&color=ffa028)](https://github.com/bayromest/name-first/stargazers)
[![Release](https://img.shields.io/github/v/release/bayromest/name-first?color=ffa028)](https://github.com/bayromest/name-first/releases/latest)
[![Blender](https://img.shields.io/badge/Blender-4.2%2B-ffa028?logo=blender&logoColor=white)](https://bayromest.github.io/name-first/)
[![Follow](https://img.shields.io/github/followers/bayromest?label=Follow&style=flat&logo=github&color=ffa028)](https://github.com/bayromest)

<img src="assets/preview.png" width="460" alt="A new cylinder with the Object Name popup open, typing Lighthouse, and the Add Cylinder panel still open below">

</div>

---

## The problem

In code, you name a variable first, then you work with it. In Blender you add a cube, get
`Cube.001`, start modeling, and an hour later your outliner is `Cylinder.004`,
`Cube.012`, `Plane.007`. You *could* press <kbd>F2</kbd> after every add. You forget.

## The fix

`name-first` opens the rename popup by itself, right after you add an object:

1. <kbd>Shift</kbd> <kbd>A</kbd> → *Cylinder*
2. The **Object Name** popup is already there, text selected. Type `Pillar`.
3. <kbd>Enter</kbd>. Done. (<kbd>Esc</kbd> keeps Blender's name.)

It works for everything in the *Add* menu: meshes, curves, surfaces, metaballs, text,
lights, cameras, empties, armatures, grease pencil, force fields, and primitives from other
add-ons. It stays quiet for things that aren't new objects (adding a modifier, a material
slot, a primitive inside Edit Mode) and for scripts.

### The "Adjust Last Operation" panel keeps working

Renaming with Blender's own <kbd>F2</kbd> closes the *Adjust Last Operation* panel, so you
can no longer change the cylinder's vertices or the cube's size. `name-first` doesn't: the
panel stays open, and if you change the vertices afterwards, the object keeps the name you
typed.

## Install

### From Blender, with automatic updates (recommended)

1. In Blender, open *Edit → Preferences → Get Extensions*.
2. Open *Repositories* (top right), click **+**, then *Add Remote Repository*.
3. Paste this URL and click *Create*:

   ```text
   https://bayromest.github.io/name-first/index.json
   ```

4. Search for **Name First** and click *Install*. That's it, there are no settings.

Blender now checks this repository for updates like any other extension.

### Drag and drop

Open the [Name First page](https://bayromest.github.io/name-first/) and drag the
**name_first** link into a Blender window. Blender installs it and offers to add the
repository, so you still get updates.

### Offline

Download **`name_first-1.0.0.zip`** from the [latest release](../../releases/latest) and drag
it into Blender (or *Get Extensions → ⌄ → Install from Disk*). You won't get updates this way.

**To turn it off:** disable or uninstall the extension.

## How it works

The whole extension is [one small file](extension/name_first/__init__.py):

| Step | How |
| --- | --- |
| Notice a new object | After each update, the last operator is an `…_add` and the object count went up |
| Ask for its name | Opens a popup panel, the same one <kbd>F2</kbd> shows, under the mouse |
| Rename without closing *Adjust Last Operation* | The text field lives on the window manager, which isn't part of undo, so typing in it doesn't end the operation the way <kbd>F2</kbd> does |
| Keep the name after a redo | Changing the vertices re-creates the object as `Cylinder`; it gets your name back |

Nothing runs in the background and no keymaps change.

## FAQ

**Can I still use F2?**
Yes, nothing about <kbd>F2</kbd> changes.

**Does it ask when I duplicate (<kbd>Shift</kbd> <kbd>D</kbd>) or import a file?**
No, only for the *Add* menu. A duplicate is usually "the same thing again".

**Can it also ask which collection the object goes in?**
Not yet. It's the next idea; open a [discussion](https://github.com/bayromest/name-first/discussions/categories/ideas) if you want it.

**Something else opens a popup when I add objects.**
Another add-on may do the same thing. [Open an issue](https://github.com/bayromest/name-first/issues) with its name.

## Building

To validate and build the extension and regenerate the update repository in
[`docs/`](docs) (served by GitHub Pages), using Blender's own validator and builder:

```bash
python tools/build_extension.py "C:\path\to\Blender\blender.exe"
```

To publish a new version: bump `version` in
[`blender_manifest.toml`](extension/name_first/blender_manifest.toml), run the command above,
then commit and push. Everyone who added the repository gets the update in Blender.

The icon and social image come from [`tools/make_images.py`](tools/make_images.py).

## Contributing

Issues and pull requests are welcome, especially the collection picker.

## License

[GPL-3.0-or-later](LICENSE), like Blender itself. Not affiliated with or endorsed by the
Blender Foundation.
