"""Parametric dish drainer ("escorredor"), styled like the reference product.

The reference is a compact drainer (61 x 17 x 20 cm): a slotted drain tray with
rounded corners, a row of thin plate-support fins, and a two-compartment cutlery
box at one end.

Because the tray is printed in pieces and glued together, the seams carry real
interlocking dovetail joints (see ``threed.split``) so the assembly does not
rely on glue alone. The body has a clean flat bottom with no feet and no
sockets; print a few smooth feet (one is included on the A1 plate, multiply it
in the slicer) and glue them wherever you like.

This model keeps those components at their original size/style but places them
in a larger tray with a 50 cm (X) x 60 cm (Y) footprint:

    - The "rack" (cutlery box + plate fins) sits in a ~17 cm deep strip along one
      edge. The cutlery box is at one end and the plate fins (same size/spacing
      as the reference) fill the rest of that edge.
    - The remaining depth is free, open, slotted drain space for anything.

Reusable primitives come from ``threed.geometry``. Tweak ``PARAMS`` to adjust.
"""

from __future__ import annotations

import cadquery as cq

from threed.geometry import (
    FootSpec,
    plain_foot,
    plate_fin,
    slot_centers_1d,
    slot_grid,
)

# Smooth glue-on foot (no peg/socket). One is laid out on the A1 plate; multiply
# it in the slicer and glue them wherever you want under the tray.
FOOT = FootSpec()

PARAMS: dict[str, float] = {
    # Overall tray (mm). Width = X = 50 cm, Depth = Y = 60 cm.
    "width": 500.0,
    "depth": 600.0,
    "tray_height": 30.0,
    "wall": 3.0,
    "corner_fillet": 24.0,
    "weld": 2.0,   # overlap between joined parts for clean, watertight unions
    # Drainage slots (long axis along Y, like the reference rows).
    "slot_w": 8.0,
    "slot_d": 30.0,
    "slot_pitch_x": 16.0,
    "slot_pitch_y": 42.0,
    "slot_margin": 28.0,
    # Rack strip along the back (keeps the reference's ~17 cm depth).
    "strip_depth": 170.0,
    # Cutlery box (two equal compartments), reference proportions ~13:17:19.
    "box_length": 130.0,
    "box_depth": 170.0,         # spans the full rack strip, like the reference
    "box_height": 190.0,
    "box_wall": 3.0,
    "box_fillet": 8.0,
    "box_gap": 12.0,
    "box_divider_offset": 0.0,   # centered divider -> two equal compartments
    # Plate-support fins (original size/spacing), hollow in the middle.
    "fin_thickness": 3.0,
    "fin_depth": 150.0,
    "fin_height": 95.0,
    "fin_top_fillet": 12.0,
    "fin_pitch": 30.0,
    "fin_gap_from_box": 24.0,
    "fin_end_margin": 18.0,
    "fin_split_gap": 60.0,   # empty space between the front/back prongs of a support
}


def _strip_center_y(p: dict[str, float]) -> float:
    """Y center of the rack strip (pushed against the back edge)."""
    return p["depth"] / 2 - p["strip_depth"] / 2


def _base_tray(p: dict[str, float]) -> cq.Workplane:
    """Rounded, slotted open tray spanning the full footprint."""
    width, depth, wall = p["width"], p["depth"], p["wall"]

    tray = (
        cq.Workplane("XY")
        .box(width, depth, p["tray_height"], centered=(True, True, False))
        .edges("|Z")
        .fillet(p["corner_fillet"])
        .faces(">Z")
        .shell(-wall)
    )

    centers = slot_grid(
        width - 2 * wall,
        depth - 2 * wall,
        p["slot_w"],
        p["slot_d"],
        p["slot_pitch_x"],
        p["slot_pitch_y"],
        margin_x=p["slot_margin"],
        margin_y=p["slot_margin"],
    )
    tray = (
        tray.faces("<Z")
        .workplane()
        .pushPoints(centers)
        .rect(p["slot_w"], p["slot_d"])
        .cutThruAll()
    )
    return tray


def _cutlery_box(p: dict[str, float]) -> cq.Workplane:
    """Two-compartment cutlery holder: a frame of walls, open top AND bottom.

    The box has no floor of its own. Items drain straight through the tray's
    slotted floor beneath it. Skipping a floor panel is what keeps the piece
    supportless: a raised floor would bridge the tray slots and the slicer would
    flag it as a floating cantilever.
    """
    length, depth, height = p["box_length"], p["box_depth"], p["box_height"]
    wall = p["box_wall"]

    box = (
        cq.Workplane("XY")
        .box(length, depth, height, centered=(True, True, False))
        .edges("|Z")
        .fillet(p["box_fillet"])
        .faces(">Z or <Z")
        .shell(-wall)
    )

    # Full-height divider across the length -> two pockets, resting on the tray.
    divider = cq.Workplane("XY").box(
        length - 2 * wall, wall, height, centered=(True, True, False)
    ).translate((0.0, p["box_divider_offset"], 0.0))
    box = box.union(divider)
    return box


def build() -> cq.Workplane:
    p = PARAMS
    width, wall = p["width"], p["wall"]
    floor_top = wall
    weld = p["weld"]
    # Parts on the floor are sunk by ``weld`` so the unions are watertight.
    seat_z = floor_top - weld
    strip_y = _strip_center_y(p)

    result = _base_tray(p)

    # --- Cutlery box at the RIGHT end of the rack strip -------------------
    # (+X is the right side when looking at the front of the model.)
    box_center_x = width / 2 - wall - p["box_gap"] - p["box_length"] / 2
    box = _cutlery_box(p).translate((box_center_x, strip_y, seat_z))
    result = result.union(box)

    # --- Plate fins filling the length from the left up to the box --------
    box_left = box_center_x - p["box_length"] / 2
    fin_zone_left = -width / 2 + wall + p["fin_end_margin"]
    fin_zone_right = box_left - p["fin_gap_from_box"]
    fin_zone_width = fin_zone_right - fin_zone_left
    fin_zone_center = (fin_zone_left + fin_zone_right) / 2

    fin_xs = [
        fin_zone_center + c
        for c in slot_centers_1d(fin_zone_width, p["fin_thickness"], p["fin_pitch"])
    ]
    for x in fin_xs:
        fin = plate_fin(
            p["fin_thickness"],
            p["fin_depth"],
            p["fin_height"],
            p["fin_top_fillet"],
            split_gap=p["fin_split_gap"],
        ).translate((x, strip_y, seat_z))
        result = result.union(fin)

    return result


def split_a1(result: cq.Workplane) -> list[cq.Workplane]:
    """Slice for the Bambu A1 plate, with real interlocking joints + one foot.

    Seams carry vertical dovetail keys (``connectors=True``): a wider head on one
    piece locks into a matching socket on its neighbour, so a glued seam cannot
    simply peel apart. The keys are vertical prisms rooted on the bed, so the
    pieces still print without supports; assemble by lowering the pieces together
    so the dovetails slide in, then glue.

    A single smooth foot rides along as its own object (set off in negative Y,
    clear of the tray pieces). All feet are identical, so just multiply this one
    in the slicer and glue them wherever you want.
    """
    from threed.split import SplitConfig, split_for_print

    pieces = split_for_print(result, SplitConfig(connectors=True))

    # Park the foot well clear to the side, just past the last laid-out piece.
    x_end = max(piece.val().BoundingBox().xmax for piece in pieces)
    y_start = min(piece.val().BoundingBox().ymin for piece in pieces)
    foot = plain_foot(FOOT)
    fb = foot.val().BoundingBox()
    pieces.append(
        foot.translate((x_end + 20.0 - fb.xmin, y_start - fb.ymin, -fb.zmin))
    )
    return pieces


if __name__ == "__main__":
    # Allow quick local debugging: `python model.py` writes next to this file.
    from pathlib import Path

    from cadquery import exporters

    out = Path(__file__).parent / "output" / "escorredor.3mf"
    out.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(build(), str(out), exportType=exporters.ExportTypes.THREEMF)
    print(f"Wrote {out}")
