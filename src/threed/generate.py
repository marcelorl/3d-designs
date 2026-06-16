"""Generate ``.3mf`` files from design scripts.

Each design folder contains a ``model.py`` that exposes a ``build()`` function
returning a CadQuery object. This module imports that script dynamically, calls
``build()`` and exports the result to ``<design>/output/<design>.3mf``.

Usage::

    poetry run generate              # generate every design
    poetry run generate escorredor   # generate a single design
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from . import designs as designs_module
from .designs import Design


def _import_model(design: Design) -> ModuleType:
    """Import a design's ``model.py`` as a standalone module."""
    module_name = f"threed_design_{design.name}"
    spec = importlib.util.spec_from_file_location(module_name, design.model_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load model for design {design.name!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _export(obj: object, path: Path) -> None:
    """Export a CadQuery object to a 3MF file at ``path``."""
    import cadquery as cq
    from cadquery import exporters

    # Assemblies must be flattened to a compound before mesh export.
    if isinstance(obj, cq.Assembly):
        obj = obj.toCompound()

    path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(obj, str(path), exportType=exporters.ExportTypes.THREEMF)


def generate_design(design: Design) -> Path:
    """Build a single design and return the path of the generated 3MF file."""
    module = _import_model(design)
    build = getattr(module, "build", None)
    if not callable(build):
        raise AttributeError(
            f"Design {design.name!r} model.py must define a callable build()"
        )
    result = build()
    output_path = design.output_dir / f"{design.name}.3mf"
    _export(result, output_path)
    return output_path


def generate_all(names: list[str] | None = None) -> list[Path]:
    """Generate the named designs, or every design when ``names`` is empty."""
    all_designs = {d.name: d for d in designs_module.discover()}
    if not all_designs:
        print("No designs found.", file=sys.stderr)
        return []

    selected: list[Design]
    if names:
        selected = []
        for name in names:
            if name not in all_designs:
                raise SystemExit(f"Design not found: {name!r}")
            selected.append(all_designs[name])
    else:
        selected = list(all_designs.values())

    generated: list[Path] = []
    for design in selected:
        print(f"Generating {design.name} ...")
        path = generate_design(design)
        print(f"  -> {path}")
        generated.append(path)
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 3MF files from designs.")
    parser.add_argument(
        "designs",
        nargs="*",
        help="Design folder names to generate. Omit to generate all designs.",
    )
    args = parser.parse_args()
    generate_all(args.designs)


if __name__ == "__main__":
    main()
