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
    """Geometry of one dovetail key on a seam (shared by the two mating pieces).

    A key is a vertical prism (constant cross-section in Z, rooted on the bed)
    with a dovetail plan profile: it is narrow at the seam and flares to a wider
    head inside the neighbour. The flared head is captured by the matching
    socket, so a glued seam is mechanically locked against pulling apart. Because
    the prism spans the material from the bed upward, it prints without supports;
    pieces are assembled by lowering them together (the dovetail slides in Z).
    """

    embed: float = 5.0          # how far the key reaches back into its own piece
    protrusion: float = 7.0     # how far the dovetail reaches into the neighbour
    width: float = 7.0          # neck/root width (along the seam)
    flare: float = 1.4          # head width = width * flare (the locking taper)
    clearance: float = 0.35     # gap added to the female socket for a glued fit


@dataclass
class SplitConfig:
    build_volume: tuple[float, float, float] = (250.0, 250.0, 250.0)
    margin: float = 6.0                # keep pieces a little under the plate
    gap: float = 10.0                  # spacing between laid-out pieces
    connectors: bool = True            # add snap keys at seams (False = flat,
                                       # glue-only seams that print supportless)
    tab: TabSpec = field(default_factory=TabSpec)
    sample_along: float = 8.0          # candidate spacing along the seam
    scan_step: float = 0.5             # vertical scan resolution for material bands
    min_band: float = 2.0              # min material thickness to host a key
    straddle: float = 3.0              # material required each side of the seam
    min_tab_spacing: float = 22.0      # min distance between placed keys
    max_tabs_per_seam: int = 60


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
    """Dovetail-key placements ``(a, b_lo, b_hi)`` on one seam.

    ``axis`` is the seam normal ('x' -> in-plane (y, z); 'y' -> (x, z)). Each key
    fills a material band (``b_lo``..``b_hi`` in z) so the prism is co-extensive
    with the wall/floor it sits in (and rooted on the bed), and is placed only
    where the material is wide enough on both sides to host it.
    """
    a_lo, a_hi = span_a
    b_lo, b_hi = span_b
    placed: list[tuple[float, float, float]] = []

    a = a_lo + cfg.sample_along
    while a <= a_hi - cfg.sample_along:
        for blo, bhi in _bands(classifiers, axis, cut, a, b_lo, b_hi, cfg):
            if bhi - blo < cfg.min_band:
                continue
            bc = (blo + bhi) / 2
            if not _width_ok(classifiers, axis, cut, a, bc, cfg):
                continue
            too_close = False
            for pa, pblo, pbhi in placed:
                pbc = (pblo + pbhi) / 2
                if abs(a - pa) <= cfg.min_tab_spacing and abs(bc - pbc) <= max(bhi - blo, pbhi - pblo):
                    too_close = True
                    break
            if not too_close:
                placed.append((a, blo, bhi))
                if len(placed) >= cfg.max_tabs_per_seam:
                    return placed
        a += cfg.sample_along
    return placed


def _dovetail_prism(pts: list[tuple[float, float]], blo: float, bhi: float) -> cq.Workplane:
    """A vertical prism: the in-plane polygon ``pts`` extruded in z over the band."""
    return (
        cq.Workplane("XY")
        .polyline(pts)
        .close()
        .extrude(bhi - blo)
        .translate((0.0, 0.0, blo))
    )


def _male(axis: str, cut: float, a: float, blo: float, bhi: float, tab: TabSpec) -> cq.Workplane:
    """Dovetail tenon: anchored in this piece, flaring into the neighbour."""
    e, pr = tab.embed, tab.protrusion
    rw = tab.width / 2.0
    hw = tab.width * tab.flare / 2.0
    if axis == "x":
        pts = [(cut - e, a - rw), (cut - e, a + rw),
               (cut + pr, a + hw), (cut + pr, a - hw)]
    else:
        pts = [(a - rw, cut - e), (a + rw, cut - e),
               (a + hw, cut + pr), (a - hw, cut + pr)]
    return _dovetail_prism(pts, blo, bhi)


def _socket(axis: str, cut: float, a: float, blo: float, bhi: float, tab: TabSpec) -> cq.Workplane:
    """The dovetail mortise: the tenon shape grown by ``clearance`` for a fit."""
    cl = tab.clearance
    e, pr = tab.embed, tab.protrusion + cl
    rw = tab.width / 2.0 + cl
    hw = tab.width * tab.flare / 2.0 + cl
    if axis == "x":
        pts = [(cut - e, a - rw), (cut - e, a + rw),
               (cut + pr, a + hw), (cut + pr, a - hw)]
    else:
        pts = [(a - rw, cut - e), (a + rw, cut - e),
               (a + hw, cut + pr), (a - hw, cut + pr)]
    return _dovetail_prism(pts, blo - cl, bhi + cl)


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

                # Male dovetails on the +X / +Y faces (internal seams only).
                if xb in x_tabs:
                    for (a, blo, bhi) in x_tabs[xb]:
                        if ya < a < yb:
                            piece = piece.union(_male("x", xb, a, blo, bhi, cfg.tab))
                if yb in y_tabs:
                    for (a, blo, bhi) in y_tabs[yb]:
                        if xa < a < xb:
                            piece = piece.union(_male("y", yb, a, blo, bhi, cfg.tab))
                # Female mortises on the -X / -Y faces.
                if xa in x_tabs:
                    for (a, blo, bhi) in x_tabs[xa]:
                        if ya < a < yb:
                            piece = piece.cut(_socket("x", xa, a, blo, bhi, cfg.tab))
                if ya in y_tabs:
                    for (a, blo, bhi) in y_tabs[ya]:
                        if xa < a < xb:
                            piece = piece.cut(_socket("y", ya, a, blo, bhi, cfg.tab))

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
