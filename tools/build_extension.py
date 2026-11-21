"""Build the extension and the self-hosted extension repository.

Validates and builds the extension with Blender's own tooling, then
regenerates the static repository in docs/, which GitHub Pages serves at
https://bayromest.github.io/name-first/.

Usage: python tools/build_extension.py <path-to-blender.exe>
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "extension" / "name_first"
REPO = ROOT / "docs"


def blender_command(blender, *args):
    subprocess.run([blender, "--factory-startup", "--command", "extension", *args], check=True)


def main(blender):
    # The repository only offers the latest version.
    REPO.mkdir(exist_ok=True)
    for old in REPO.glob("*.zip"):
        old.unlink()

    blender_command(blender, "validate", str(SOURCE))
    blender_command(blender, "build", "--source-dir", str(SOURCE), "--output-dir", str(REPO))
    blender_command(
        blender, "server-generate", "--repo-dir", str(REPO),
        "--html", "--html-template", str(ROOT / "tools" / "repo_template.html"),
    )
    shutil.copyfile(ROOT / "assets" / "preview.png", REPO / "preview.png")
    shutil.copyfile(ROOT / "icons" / "name-first.png", REPO / "icon.png")
    shutil.copyfile(ROOT / "assets" / "social-preview.png", REPO / "social.png")
    (REPO / ".nojekyll").touch()


if __name__ == "__main__":
    main(*sys.argv[1:])
