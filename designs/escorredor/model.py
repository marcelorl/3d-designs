"""Parametric dish drainer ("escorredor"), styled like the reference product.

The reference is a compact drainer (61 x 17 x 20 cm): a slotted drain tray with
rounded corners and four feet, a row of thin plate-support fins, and a
two-compartment cutlery box at one end.

This model keeps those components at their original size/style but places them
in a larger 60 x 50 cm tray:

    - The "rack" (cutlery box + plate fins) sits in a ~17 cm deep strip along the
      back of the 60 cm edge. The cutlery box is at one end and the plate fins
      (same size/spacing as the reference) fill the rest of the 60 cm length.
    - The remaining ~33 cm depth is free, open, slotted drain space for anything.

Reusable primitives come from ``threed.geometry``. Tweak ``PARAMS`` to adjust.
"""

from __future__ import annotations

import cadquery as cq

from threed.geometry import plate_fin, slot_centers_1d, slot_grid

PARAMS: dict[str, float] = {
    # Overall tray (mm). Width = X = 60 cm (length), Depth = Y = 50 cm.
    "width": 600.0,
    "depth": 500.0,
    "tray_height": 30.0,
    "wall": 3.0,
    "corner_fillet": 24.0,
    "weld": 2.0,   # overlap between joined parts for clean, watertight unions
    # Feet under the four corners.
    "foot_radius": 12.0,
    "foot_height": 14.0,
    "foot_inset": 36.0,
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
    "box_slot": 8.0,
    "box_slot_pitch": 16.0,
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


def _feet(p: dict[str, float]) -> cq.Workplane:
    """Four rounded feet under the corners, sitting below the tray bottom."""
    r, h, inset = p["foot_radius"], p["foot_height"], p["foot_inset"]
    weld = p["weld"]
    xs = (-p["width"] / 2 + inset, p["width"] / 2 - inset)
    ys = (-p["depth"] / 2 + inset, p["depth"] / 2 - inset)

    feet: cq.Workplane | None = None
    for x in xs:
        for y in ys:
            # Extend slightly into the base (weld) for a clean union.
            foot = (
                cq.Workplane("XY")
                .cylinder(h + weld, r, centered=(True, True, False))
                .translate((x, y, -h))
                .edges("<Z")
                .fillet(min(r * 0.6, h * 0.6))
            )
            feet = foot if feet is None else feet.union(foot)
    assert feet is not None
    return feet


def _cutlery_box(p: dict[str, float]) -> cq.Workplane:
    """Two-compartment box with solid walls and a slotted floor, centered."""
    length, depth, height = p["box_length"], p["box_depth"], p["box_height"]
    wall = p["box_wall"]

    box = (
        cq.Workplane("XY")
        .box(length, depth, height, centered=(True, True, False))
        .edges("|Z")
        .fillet(p["box_fillet"])
        .faces(">Z")
        .shell(-wall)
    )

    # Divider across the length -> two pockets (slightly unequal).
    divider = cq.Workplane("XY").box(
        length - 2 * wall, wall, height - wall, centered=(True, True, False)
    ).translate((0.0, p["box_divider_offset"], wall))
    box = box.union(divider)

    # Slotted floor for drainage.
    centers = slot_grid(
        length - 2 * wall,
        depth - 2 * wall,
        p["box_slot"],
        p["box_slot"],
        p["box_slot_pitch"],
        p["box_slot_pitch"],
        margin_x=12.0,
        margin_y=12.0,
    )
    box = (
        box.faces("<Z")
        .workplane()
        .pushPoints(centers)
        .rect(p["box_slot"], p["box_slot"])
        .cutBlind(-(wall + 1.0))
    )
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
    result = result.union(_feet(p))

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


if __name__ == "__main__":
    # Allow quick local debugging: `python model.py` writes next to this file.
    from pathlib import Path

    from cadquery import exporters

    out = Path(__file__).parent / "output" / "escorredor.3mf"
    out.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(build(), str(out), exportType=exporters.ExportTypes.THREEMF)
    print(f"Wrote {out}")
