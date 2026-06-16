"""Split a solid into pieces that fit a printer build volume.

Large designs (e.g. the 60 x 50 cm escorredor) do not fit a Bambu Lab A1 plate
(256 x 256 x 256 mm). :func:`split_for_print` slices a CadQuery solid into a grid
of pieces, each fitting inside the given build volume, and adds **integrated snap
connectors** at the internal seams: a male tab/key on one piece that plugs into a
matching female socket on its neighbour, so the pieces can be assembled (and
glued) back into the whole.

The connectors are flat rectangular keys placed only where the seam crosses solid
material thick enough to host them (validated by point-in-solid tests), which is
robust on thin-walled models where round pins would not fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON


@dataclass
class TabSpec:
    """Geometry of one snap key on a seam (shared by the two mating pieces)."""

    embed: float = 4.0          # how far the key reaches back into its own piece
    protrusion: float = 6.0     # how far the male key sticks into the neighbour
    width: float = 10.0         # key width (along the seam, in-plane)
    max_thick: float = 2.4      # key thickness cap (across the thin wall)
    clearance: float = 0.3      # gap added to the female socket for a fit


@dataclass
class SplitConfig:
    build_volume: tuple[float, float, float] = (250.0, 250.0, 250.0)
    margin: float = 6.0                # keep pieces a little under the plate
    gap: float = 10.0                  # spacing between laid-out pieces
    connectors: bool = True            # add snap keys at seams (False = flat,
                                       # glue-only seams that print supportless)
    tab: TabSpec = field(default_factory=TabSpec)
    sample_along: float = 16.0         # candidate spacing along the seam
    scan_step: float = 0.5             # vertical scan resolution for material bands
    min_band: float = 2.0              # min material thickness to host a key
    straddle: float = 3.0              # material required each side of the seam
    min_tab_spacing: float = 38.0      # min distance between placed keys
    max_tabs_per_seam: int = 40


def _solids(shape: cq.Shape) -> list[cq.Solid]:
    solids = shape.Solids()
    return solids if solids else [shape]


def _classifiers(shape: cq.Shape) -> list[BRepClass3d_SolidClassifier]:
    out = []
    for s in _solids(shape):
        out.append(BRepClass3d_SolidClassifier(s.wrapped))
    return out


def _inside(classifiers: list[BRepClass3d_SolidClassifier], pt: tuple[float, float, float]) -> bool:
    p = gp_Pnt(*pt)
    for cls in classifiers:
        cls.Perform(p, 1e-6)
        state = cls.State()
        if state in (TopAbs_IN, TopAbs_ON):
            return True
    return False


def _box(dx: float, dy: float, dz: float, center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(dx, dy, dz).translate(center)


def _cuts(lo: float, length: float, max_len: float) -> list[float]:
    """Internal cut coordinates so each slice is <= ``max_len``."""
    n = max(1, math.ceil(length / max_len))
    step = length / n
    return [lo + step * i for i in range(1, n)]


def _point(axis: str, cut: float, off: float, a: float, b: float) -> tuple[float, float, float]:
    """A point at signed offset ``off`` from the seam, at in-plane coords (a, b)."""
    if axis == "x":
        return (cut + off, a, b)
    return (a, cut + off, b)


def _bands(classifiers, axis: str, cut: float, a: float, b_lo: float, b_hi: float,
           cfg: SplitConfig) -> list[tuple[float, float]]:
    """Contiguous ``b`` ranges where material straddles the seam at column ``a``."""
    bands: list[tuple[float, float]] = []
    start: float | None = None
    b = b_lo
    d = cfg.straddle
    while b <= b_hi:
        solid = (
            _inside(classifiers, _point(axis, cut, -d, a, b))
            and _inside(classifiers, _point(axis, cut, d, a, b))
        )
        if solid and start is None:
            start = b
        elif not solid and start is not None:
            bands.append((start, b - cfg.scan_step))
            start = None
        b += cfg.scan_step
    if start is not None:
        bands.append((start, b_hi))
    return bands


def _width_ok(classifiers, axis: str, cut: float, a: float, b: float, cfg: SplitConfig) -> bool:
    """The key width along the seam must sit on material on both sides."""
    hw = cfg.tab.width / 2
    d = cfg.straddle
    for da in (-hw, hw):
        if axis == "x":
            if not (_inside(classifiers, (cut - d, a + da, b))
                    and _inside(classifiers, (cut + d, a + da, b))):
                return False
        else:
            if not (_inside(classifiers, (a + da, cut - d, b))
                    and _inside(classifiers, (a + da, cut + d, b))):
                return False
    return True


def _seam_tabs(
    classifiers,
    axis: str,
    cut: float,
    span_a: tuple[float, float],
    span_b: tuple[float, float],
    cfg: SplitConfig,
) -> list[tuple[float, float, float]]:
    """Snap-key placements (a, b_center, thick) on one seam.

    ``axis`` is the seam normal ('x' -> in-plane (y, z); 'y' -> (x, z)). Keys are
    placed on material bands thick enough to host them and sized to fit the band.
    """
    a_lo, a_hi = span_a
    b_lo, b_hi = span_b
    placed: list[tuple[float, float, float]] = []

    a = a_lo + cfg.sample_along
    while a <= a_hi - cfg.sample_along:
        for blo, bhi in _bands(classifiers, axis, cut, a, b_lo, b_hi, cfg):
            blen = bhi - blo
            if blen < cfg.min_band:
                continue
            bc = (blo + bhi) / 2
            thick = min(cfg.tab.max_thick, blen * 0.7)
            if not _width_ok(classifiers, axis, cut, a, bc, cfg):
                continue
            if all(abs(a - pa) > cfg.min_tab_spacing or abs(bc - pb) > max(thick, pt) * 1.5
                   for pa, pb, pt in placed):
                placed.append((a, bc, thick))
                if len(placed) >= cfg.max_tabs_per_seam:
                    return placed
        a += cfg.sample_along
    return placed


def _male(axis: str, cut: float, a: float, b: float, thick: float, tab: TabSpec) -> cq.Workplane:
    length = tab.embed + tab.protrusion
    center = cut - tab.embed + length / 2
    if axis == "x":
        return _box(length, tab.width, thick, (center, a, b))
    return _box(tab.width, length, thick, (a, center, b))


def _socket(axis: str, cut: float, a: float, b: float, thick: float, tab: TabSpec) -> cq.Workplane:
    cl = tab.clearance
    length = tab.protrusion + 2 * cl
    center = cut - cl + length / 2
    if axis == "x":
        return _box(length, tab.width + 2 * cl, thick + 2 * cl, (center, a, b))
    return _box(tab.width + 2 * cl, length, thick + 2 * cl, (a, center, b))


def split_for_print(model: cq.Workplane, cfg: SplitConfig | None = None) -> list[cq.Workplane]:
    """Slice ``model`` into build-volume-sized pieces with snap connectors.

    Returns the pieces laid out side by side (spaced by ``cfg.gap``) and dropped
    onto ``z = 0`` so they are ready to arrange on plates.
    """
    cfg = cfg or SplitConfig()
    shape = model.val()
    classifiers = _classifiers(shape)
    bb = shape.BoundingBox()

    max_x = cfg.build_volume[0] - cfg.margin
    max_y = cfg.build_volume[1] - cfg.margin
    max_z = cfg.build_volume[2] - cfg.margin

    xcuts = _cuts(bb.xmin, bb.xlen, max_x)
    ycuts = _cuts(bb.ymin, bb.ylen, max_y)
    zcuts = _cuts(bb.zmin, bb.zlen, max_z)

    xedges = [bb.xmin, *xcuts, bb.xmax]
    yedges = [bb.ymin, *ycuts, bb.ymax]
    zedges = [bb.zmin, *zcuts, bb.zmax]

    # Pre-compute snap keys for every internal seam (skipped for flat seams).
    if cfg.connectors:
        x_tabs = {cx: _seam_tabs(classifiers, "x", cx, (bb.ymin, bb.ymax), (bb.zmin, bb.zmax), cfg)
                  for cx in xcuts}
        y_tabs = {cy: _seam_tabs(classifiers, "y", cy, (bb.xmin, bb.xmax), (bb.zmin, bb.zmax), cfg)
                  for cy in ycuts}
    else:
        x_tabs = {}
        y_tabs = {}

    pieces: list[cq.Workplane] = []
    for ix in range(len(xedges) - 1):
        xa, xb = xedges[ix], xedges[ix + 1]
        for iy in range(len(yedges) - 1):
            ya, yb = yedges[iy], yedges[iy + 1]
            for iz in range(len(zedges) - 1):
                za, zb = zedges[iz], zedges[iz + 1]
                cell = _box(
                    (xb - xa) + 1.0, (yb - ya) + 1.0, (zb - za) + 1.0,
                    ((xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2),
                )
                piece = model.intersect(cell)
                if piece.val().isNull() or piece.val().Volume() < 1.0:
                    continue

                # Male keys on the +X / +Y faces (internal seams only).
                if xb in x_tabs:
                    for (a, b, t) in x_tabs[xb]:
                        if ya < a < yb and za < b < zb:
                            piece = piece.union(_male("x", xb, a, b, t, cfg.tab))
                if yb in y_tabs:
                    for (a, b, t) in y_tabs[yb]:
                        if xa < a < xb and za < b < zb:
                            piece = piece.union(_male("y", yb, a, b, t, cfg.tab))
                # Female sockets on the -X / -Y faces.
                if xa in x_tabs:
                    for (a, b, t) in x_tabs[xa]:
                        if ya < a < yb and za < b < zb:
                            piece = piece.cut(_socket("x", xa, a, b, t, cfg.tab))
                if ya in y_tabs:
                    for (a, b, t) in y_tabs[ya]:
                        if xa < a < xb and za < b < zb:
                            piece = piece.cut(_socket("y", ya, a, b, t, cfg.tab))

                pieces.append(piece)

    return _layout(pieces, cfg.gap)


def _layout(pieces: list[cq.Workplane], gap: float) -> list[cq.Workplane]:
    """Spread pieces along X (dropped to z=0) so they do not overlap."""
    out: list[cq.Workplane] = []
    cursor = 0.0
    for piece in pieces:
        bb = piece.val().BoundingBox()
        out.append(piece.translate((cursor - bb.xmin, -bb.ymin, -bb.zmin)))
        cursor += bb.xlen + gap
    return out
