"""Discovery helpers for designs stored on disk.

A design is a folder under ``designs/`` that contains a ``model.py`` script.
Optionally it holds a reference image and an ``output/`` folder with the
generated ``.3mf`` files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_designs_dir

MODEL_FILENAME = "model.py"
OUTPUT_DIRNAME = "output"
REFERENCES_DIRNAME = "references"
REFERENCE_STEMS = ("reference",)
REFERENCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


@dataclass(frozen=True)
class Design:
    """A single design folder on disk."""

    name: str
    path: Path

    @property
    def model_file(self) -> Path:
        return self.path / MODEL_FILENAME

    @property
    def output_dir(self) -> Path:
        return self.path / OUTPUT_DIRNAME

    @property
    def references_dir(self) -> Path:
        return self.path / REFERENCES_DIRNAME

    def reference_images(self) -> list[Path]:
        """Return all reference images for this design, sorted by name.

        Images are collected from a ``references/`` subfolder (any image file)
        and from any top-level ``reference.*`` file, deduplicated.
        """
        images: list[Path] = []

        if self.references_dir.is_dir():
            for entry in sorted(self.references_dir.iterdir()):
                if entry.is_file() and entry.suffix.lower() in REFERENCE_EXTENSIONS:
                    images.append(entry)

        for stem in REFERENCE_STEMS:
            for ext in REFERENCE_EXTENSIONS:
                candidate = self.path / f"{stem}{ext}"
                if candidate.is_file():
                    images.append(candidate)

        return images

    def reference_image(self) -> Path | None:
        """Return the first reference image (used for the gallery thumbnail)."""
        images = self.reference_images()
        return images[0] if images else None

    def outputs(self) -> list[Path]:
        """Return generated ``.3mf`` files, sorted by name."""
        if not self.output_dir.is_dir():
            return []
        return sorted(self.output_dir.glob("*.3mf"))


def discover() -> list[Design]:
    """Return all designs found under the designs directory, sorted by name."""
    designs_dir = get_designs_dir()
    if not designs_dir.is_dir():
        return []

    designs: list[Design] = []
    for entry in sorted(designs_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / MODEL_FILENAME).is_file():
            continue
        designs.append(Design(name=entry.name, path=entry))
    return designs


def get(name: str) -> Design:
    """Return a single design by folder name, or raise ``KeyError``."""
    for design in discover():
        if design.name == name:
            return design
    raise KeyError(f"Design not found: {name!r}")
