"""Parametric dish drainer ("escorredor"), styled like the reference product.

The reference is a compact drainer (61 x 17 x 20 cm): a slotted drain tray with
rounded corners, a row of thin plate-support fins, and a two-compartment cutlery
box at one end.

Because the tray is printed in pieces and glued together, the body itself
carries no feet -- only shallow glue sockets on its underside (one under every
printed piece plus the corners). The feet are printed and glued into those
sockets, so the assembled piece is supported across its whole footprint and can
hold heavy items (pots, cups, ...). The feet ride along on the A1 export as
their own selectable parts.

This model keeps those components at their original size/style but places them
in a larger tray with a 50 cm (X) x 60 cm (Y) footprint:

    - The "rack" (cutlery box + plate fins) sits in a ~17 cm deep strip along one
      edge. The cutlery box is at one end and the plate fins (same size/spacing
      as the reference) fill the rest of that edge.
    - The remaining depth is free, open, slotted drain space for anything.

Reusable primitives come from ``threed.geometry``. Tweak ``PARAMS`` to adjust.
"""

from __future__ import annotations

import math

import cadquery as cq

from threed.geometry import (
    FootSpec,
    mounting_boss,
    plate_fin,
    slot_centers_1d,
    slot_grid,
    socket_foot,
)

# Shared foot/socket geometry. The separate ``pe`` design prints feet with the
# very same spec so each peg fits a socket here.
FOOT = FootSpec()

PARAMS: dict[str, float] = {
    # Overall tray (mm). Width = X = 50 cm, Depth = Y = 60 cm.
    "width": 500.0,
    "depth": 600.0,
    "tray_height": 30.0,
    "wall": 3.0,
    "corner_fillet": 24.0,
    "weld": 2.0,   # overlap between joined parts for clean, watertight unions
    # Glue-in feet: the body only carries sockets (print feet from the `pe`
    # design and glue them in). One foot sits under each printed/glued piece
    # plus the four corners, so the assembly is supported as a whole.
    "foot_corner_inset": 42.0,   # corner foot distance from the outer edges
    "print_build": 250.0,        # Bambu A1 plate side used to lay out the pieces
    "print_margin": 6.0,         # must match split.SplitConfig.margin
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


def foot_positions(p: dict[str, float]) -> list[tuple[float, float]]:
    """(x, y) of every foot: one under each printed (glued) piece + the corners.

    The tray is sliced for printing on a grid of ``print_build`` cells (the same
    grid ``split.split_for_print`` uses), so placing a foot at each cell center
    guarantees every glued piece is supported. The four outer corners are added
    for stability where the pieces overhang their cell centers.
    """
    spacing = p["print_build"] - p["print_margin"]

    def cell_centers(length: float) -> list[float]:
        n = max(1, math.ceil(length / spacing))
        step = length / n
        return [-length / 2 + step * (i + 0.5) for i in range(n)]

    xs = cell_centers(p["width"])
    ys = cell_centers(p["depth"])
    points = [(x, y) for x in xs for y in ys]

    inset = p["foot_corner_inset"]
    corners = [
        (sx * (p["width"] / 2 - inset), sy * (p["depth"] / 2 - inset))
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]
    min_sep = 2 * FOOT.boss_radius
    for cx, cy in corners:
        if all(math.hypot(cx - x, cy - y) > min_sep for x, y in points):
            points.append((cx, cy))
    return points


def _foot_sockets(p: dict[str, float]) -> cq.Workplane:
    """A reinforcing pad + glue socket at every foot position.

    Each pad keeps the tray's underside flat (it rises into the interior) so the
    body prints without supports; the socket is bored up from the flat bottom.
    """
    bosses: cq.Workplane | None = None
    for x, y in foot_positions(p):
        boss = mounting_boss(FOOT, p["wall"]).translate((x, y, 0.0))
        bosses = boss if bosses is None else bosses.union(boss)
    assert bosses is not None
    return bosses


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
    result = result.union(_foot_sockets(p))

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


def _feet_for_plate() -> list[cq.Workplane]:
    """The glue-in feet as separate objects, arranged in a grid (each on z=0).

    One foot per socket on the body (see :func:`foot_positions`). They ride along
    on the A1 export as their own selectable parts, so in the slicer you simply
    pick the tray pieces and/or the feet you want to print.
    """
    foot = socket_foot(FOOT)
    bb = foot.val().BoundingBox()
    pitch = bb.xlen + 8.0
    count = len(foot_positions(PARAMS))
    cols = math.ceil(math.sqrt(count))

    feet: list[cq.Workplane] = []
    for i in range(count):
        row, col = divmod(i, cols)
        # Lay the feet out in negative Y, clear of the tray pieces (y >= 0).
        feet.append(foot.translate((col * pitch, -(row + 1) * pitch, 0.0)))
    return feet


def split_a1(result: cq.Workplane) -> list[cq.Workplane]:
    """Slice for the Bambu A1 plate: flat glue-only seams + the loose feet.

    Snap connectors are intentionally disabled: they stick out horizontally from
    the seams and the slicer flags them as floating cantilevers (needing
    supports). Flat seams keep every piece a clean, flat-bottomed solid that
    prints with no supports, and the pieces are glued together anyway.

    The glue-in feet are appended as their own objects, so everything lives in a
    single ``escorredor_a1.3mf`` and you select what to print in the slicer.
    """
    from threed.split import SplitConfig, split_for_print

    pieces = split_for_print(result, SplitConfig(connectors=False))
    pieces.extend(_feet_for_plate())
    return pieces


if __name__ == "__main__":
    # Allow quick local debugging: `python model.py` writes next to this file.
    from pathlib import Path

    from cadquery import exporters

    out = Path(__file__).parent / "output" / "escorredor.3mf"
    out.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(build(), str(out), exportType=exporters.ExportTypes.THREEMF)
    print(f"Wrote {out}")
