# 3MF Generator

A small, fully local project to generate and browse parametric 3D models as
`.3mf` files.

- Each **design** lives in its own folder under `designs/` and contains:
  - a `model.py` CadQuery script that builds the geometry,
  - an optional `reference.png` (or `.jpg`) reference image,
  - an `output/` folder with the generated `.3mf` file(s).
- A command-line tool (`generate`) builds the `.3mf` files.
- A **Streamlit** app lets you list the designs and view each model in an
  interactive 3D viewer.

No authentication, no server, no Docker. Everything runs on your machine.

## Requirements

- **Python 3.12** (CadQuery's OpenCASCADE/VTK wheels are reliable here; newer
  versions such as 3.14 are not yet supported).
- [Poetry](https://python-poetry.org/).

On macOS with Homebrew you likely already have Python 3.12:

```bash
brew install python@3.12   # if not installed
```

## Setup

Point Poetry at Python 3.12 and install the dependencies:

```bash
poetry env use python3.12
poetry install
```

## Generate models

```bash
poetry run generate              # generate every design
poetry run generate escorredor   # generate a single design
```

Generated files land in `designs/<name>/output/<name>.3mf`.

## View models

```bash
poetry run streamlit run src/threed/app.py
```

This opens a browser tab with:

- a **gallery** of all designs (folder name + reference image), and
- a **detail page** per design showing the reference image, the list of
  generated `.3mf` files, an interactive 3D viewer, and a **Regenerate** button.

## Add a new design

1. Create a folder `designs/<your-design>/`.
2. Add a `model.py` that defines a `build()` function returning a CadQuery
   object (a `Workplane`, `Shape`, `Compound`, or `Assembly`):

   ```python
   import cadquery as cq

   def build():
       return cq.Workplane("XY").box(40, 40, 10)
   ```

3. (Optional) Drop a `reference.png` next to it.
4. Run `poetry run generate <your-design>`.

It will automatically appear in the CLI and in the Streamlit app.

## Project layout

```
designs/
  escorredor/
    model.py        # parametric dish drainer
    reference.png   # reference image
    output/         # generated escorredor.3mf
src/threed/
  config.py         # resolves the designs directory
  designs.py        # discovery of designs and their files
  generate.py       # CLI that builds and exports 3MF files
  app.py            # Streamlit viewer
```
