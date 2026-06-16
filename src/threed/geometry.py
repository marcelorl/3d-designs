"""Reusable CadQuery geometry helpers shared across designs.

These are intentionally small, composable building blocks (slot arrays,
perforations, plate fins) so each design's ``model.py`` can assemble a shape
without duplicating low-level geometry code.
"""

from __future__ import annotations

import cadquery as cq


def slot_centers_1d(length: float, slot: float, pitch: float, margin: float = 0.0) -> list[float]:
    """Centered positions for slots of size ``slot`` repeated every ``pitch``.

    Fits as many slots as possible within ``length`` (minus ``margin`` on each
    side) and centers the whole row on 0.
    """
    usable = length - 2 * margin - slot
    if usable < 0:
        return [0.0]
    count = int(usable // pitch) + 1
    span = (count - 1) * pitch
    start = -span / 2
    return [start + i * pitch for i in range(count)]


def slot_grid(
    region_w: float,
    region_d: float,
    slot_w: float,
    slot_d: float,
    pitch_x: float,
    pitch_y: float,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
) -> list[tuple[float, float]]:
    """Centered (x, y) positions for a rectangular slot grid filling a region."""
    xs = slot_centers_1d(region_w, slot_w, pitch_x, margin_x)
    ys = slot_centers_1d(region_d, slot_d, pitch_y, margin_y)
    return [(x, y) for x in xs for y in ys]


def cut_rect_array(
    wp: cq.Workplane,
    centers: list[tuple[float, float]],
    width: float,
    height: float,
    depth: float | None = None,
) -> cq.Workplane:
    """Cut a rectangular array on the current workplane in a single operation.

    ``centers`` are 2D points in the workplane's local coordinates. When
    ``depth`` is ``None`` the cut goes through the whole solid, otherwise it is a
    blind cut of ``depth`` along the workplane's negative normal (useful to
    perforate a single wall).
    """
    if not centers:
        return wp
    sketched = wp.pushPoints(centers).rect(width, height)
    if depth is None:
        return sketched.cutThruAll()
    return sketched.cutBlind(-abs(depth))


def tapered_fin(
    thickness: float,
    span: float,
    front_height: float,
    back_height: float,
) -> cq.Workplane:
    """A single trapezoidal plate-support fin, centered on X.

    The fin is a thin wall of ``thickness`` (along X) spanning ``span`` (along Y),
    standing on the XY plane. Its top edge slopes from ``back_height`` at the back
    (-Y) down to ``front_height`` at the front (+Y), matching the reference photo.
    """
    profile = (
        cq.Workplane("YZ")
        .polyline(
            [
                (-span / 2, 0.0),
                (span / 2, 0.0),
                (span / 2, front_height),
                (-span / 2, back_height),
            ]
        )
        .close()
    )
    solid = profile.extrude(thickness)
    return solid.translate((-thickness / 2, 0.0, 0.0))


def plate_fin(
    thickness: float,
    depth: float,
    height: float,
    top_fillet: float = 0.0,
    split_gap: float = 0.0,
) -> cq.Workplane:
    """A plate-support divider with rounded top corners.

    Centered on X, standing on the XY plane: ``thickness`` along X, ``depth``
    along Y, ``height`` along Z. The top edges running along X are filleted so
    the corners are rounded, matching the reference photo.

    When ``split_gap`` > 0, a centered gap is cut along the depth so the divider
    becomes two separate prongs (front + back) that together hold a single
    plate, with empty space between them -- like the reference.
    """
    prongs: list[cq.Workplane] = []
    if split_gap > 0 and split_gap < depth:
        prong_depth = (depth - split_gap) / 2.0
        for sign in (-1, 1):
            center_y = sign * (split_gap / 2.0 + prong_depth / 2.0)
            prong = cq.Workplane("XY").box(
                thickness, prong_depth, height, centered=(True, True, False)
            )
            if top_fillet > 0:
                safe = min(top_fillet, height * 0.49, prong_depth * 0.49)
                prong = prong.edges("|X and >Z").fillet(safe)
            prongs.append(prong.translate((0.0, center_y, 0.0)))
        fin = prongs[0].union(prongs[1])
        return fin

    fin = cq.Workplane("XY").box(thickness, depth, height, centered=(True, True, False))
    if top_fillet > 0:
        safe = min(top_fillet, height * 0.49, depth * 0.49)
        fin = fin.edges("|X and >Z").fillet(safe)
    return fin


def perforate_face(
    solid: cq.Workplane,
    face_selector: str,
    centers: list[tuple[float, float]],
    slot_w: float,
    slot_h: float,
    wall_thickness: float,
) -> cq.Workplane:
    """Cut a slot array into one face, perforating only that wall."""
    wp = solid.faces(face_selector).workplane(centerOption="CenterOfBoundBox")
    return cut_rect_array(wp, centers, slot_w, slot_h, depth=wall_thickness + 1.0)
