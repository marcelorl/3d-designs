"""Streamlit viewer for the generated designs.

Run with::

    poetry run streamlit run src/threed/app.py

Shows a gallery of all designs and a detail page per design with the reference
image, the generated ``.3mf`` files, and an interactive 3D viewer.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pyvista as pv

# Render off-screen so VTK never tries to open a native window. On macOS this is
# essential: Streamlit runs the script in a worker thread and creating a Cocoa
# window off the main thread crashes the process.
pv.OFF_SCREEN = True

import panel as pn  # noqa: E402 - must be imported after OFF_SCREEN is set
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402
import trimesh  # noqa: E402

from threed import designs as designs_module  # noqa: E402
from threed.designs import Design  # noqa: E402
from threed.generate import generate_design  # noqa: E402

pn.extension("vtk")

# On headless Linux a virtual framebuffer is still required for off-screen GL.
if sys.platform.startswith("linux") and "xvfb_started" not in st.session_state:
    pv.start_xvfb()
    st.session_state["xvfb_started"] = True


st.set_page_config(page_title="3MF Designs", page_icon="🧊", layout="wide")


def load_pyvista_mesh(path: Path) -> pv.PolyData:
    """Load a 3MF file into a single PyVista mesh."""
    loaded = trimesh.load(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate(
            [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        )
    return pv.wrap(loaded)


def _grid_lines(bounds: tuple[float, ...], step: float = 100.0) -> pv.PolyData:
    """A flat reference grid (line segments) on the floor, aligned to the min corner."""
    xmin, xmax, ymin, ymax, zmin, _ = bounds
    xs = list(np.arange(xmin, xmax + step / 2, step)) + [xmax]
    ys = list(np.arange(ymin, ymax + step / 2, step)) + [ymax]

    points: list[tuple[float, float, float]] = []
    lines: list[int] = []
    idx = 0
    for x in xs:
        points += [(x, ymin, zmin), (x, ymax, zmin)]
        lines += [2, idx, idx + 1]
        idx += 2
    for y in ys:
        points += [(xmin, y, zmin), (xmax, y, zmin)]
        lines += [2, idx, idx + 1]
        idx += 2
    return pv.PolyData(np.array(points, dtype=float), lines=np.array(lines))


def _label_mesh(text: str, anchor: tuple[float, float, float], height: float) -> pv.PolyData:
    """An upright 3D text mesh (mm value) centered on ``anchor``, facing -Y."""
    mesh = pv.Text3D(text, depth=0.5)
    b = mesh.bounds
    cur_h = b[3] - b[2]
    scale = height / cur_h if cur_h else 1.0
    mesh.points *= scale
    # Stand the text upright (its height moves onto the Z axis) so it reads
    # naturally in the isometric/front view instead of lying flat on the floor.
    mesh.rotate_x(90, point=(0.0, 0.0, 0.0), inplace=True)
    b = mesh.bounds
    cx = (b[0] + b[1]) / 2
    cy = (b[2] + b[3]) / 2
    cz = (b[4] + b[5]) / 2
    mesh.points += np.array([anchor[0] - cx, anchor[1] - cy, anchor[2] - cz])
    return mesh


def _grid_labels(bounds: tuple[float, ...], step: float = 100.0) -> list[pv.PolyData]:
    """mm ruler labels along the X and Y edges, measured from the min corner."""
    xmin, xmax, ymin, ymax, zmin, _ = bounds
    text_h = max(step * 0.30, 28.0)
    base_z = zmin + text_h * 0.6
    labels: list[pv.PolyData] = []
    for x in list(np.arange(xmin, xmax + step / 2, step)) + [xmax]:
        labels.append(_label_mesh(f"{x - xmin:.0f}", (x, ymin - text_h * 0.9, base_z), text_h))
    for y in list(np.arange(ymin, ymax + step / 2, step)) + [ymax]:
        labels.append(_label_mesh(f"{y - ymin:.0f}", (xmin - text_h * 1.4, y, base_z), text_h))
    return labels


def render_model(path: Path, show_grid: bool = False, height: int = 900) -> None:
    """Render a 3MF file as a self-contained interactive vtk.js viewer."""
    try:
        mesh = load_pyvista_mesh(path)
    except Exception as exc:  # noqa: BLE001 - surface any load error to the UI
        st.error(f"Could not load {path.name}: {exc}")
        return

    xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
    dims = (xmax - xmin, ymax - ymin, zmax - zmin)
    st.caption(
        f"Size: {dims[0]:.0f} x {dims[1]:.0f} x {dims[2]:.0f} mm "
        f"({dims[0] / 10:.1f} x {dims[1] / 10:.1f} x {dims[2] / 10:.1f} cm)"
    )

    plotter = pv.Plotter(off_screen=True, window_size=[1600, height])
    plotter.add_mesh(mesh, color="#9ecae1", show_edges=False, smooth_shading=True)
    plotter.background_color = "white"

    if show_grid:
        plotter.add_mesh(_grid_lines(mesh.bounds, 100.0), color="#9aa6b2", line_width=1)
        plotter.add_mesh(mesh.outline(), color="#ef4444", line_width=2)
        for label in _grid_labels(mesh.bounds, 100.0):
            plotter.add_mesh(label, color="#1f2937")

    # Front-facing isometric: the cutlery box sits on the right and the mm ruler
    # edges face the viewer (the default isometric would hide them behind the model).
    plotter.view_vector((0.35, -1.0, 0.45), viewup=(0.0, 0.0, 1.0))

    # Panel serializes the scene to a standalone vtk.js page that is interactive
    # client-side (rotate / zoom / pan), so no rendering server is needed.
    pane = pn.pane.VTK(
        plotter.ren_win,
        height=height,
        sizing_mode="stretch_width",
        orientation_widget=True,
    )
    buffer = StringIO()
    pane.save(buffer, title=path.name)
    components.html(buffer.getvalue(), height=height + 20, scrolling=False)
    plotter.close()


def show_gallery(designs: list[Design]) -> None:
    st.title("3MF Designs")
    st.caption("Local gallery of parametric designs. Pick one to view it in 3D.")

    if not designs:
        st.info(
            "No designs found yet. Create a folder under `designs/` with a "
            "`model.py`, then run `poetry run generate`."
        )
        return

    columns = st.columns(3)
    for index, design in enumerate(designs):
        column = columns[index % 3]
        with column:
            with st.container(border=True):
                st.subheader(design.name)
                reference = design.reference_image()
                if reference is not None:
                    st.image(str(reference), use_container_width=True)
                else:
                    st.caption("No reference image.")
                st.write(f"Generated files: {len(design.outputs())}")
                if st.button("Open", key=f"open-{design.name}"):
                    st.query_params["design"] = design.name
                    st.rerun()


def show_detail(design: Design) -> None:
    # Controls + reference live in the sidebar so the 3D viewer can use the full
    # page width.
    with st.sidebar:
        if st.button("< Back to gallery"):
            st.query_params.clear()
            st.rerun()

        st.header(design.name)

        outputs = design.outputs()
        selected_path = None
        show_grid = False
        if outputs:
            labels = [path.name for path in outputs]
            selected = st.selectbox("3MF file", labels, key=f"select-{design.name}")
            selected_path = outputs[labels.index(selected)]
            show_grid = st.checkbox(
                "Show measurement grid (mm, 100 mm spacing)",
                value=False,
                key=f"grid-{design.name}",
            )

        if st.button("Regenerate", type="primary"):
            with st.spinner(f"Generating {design.name} ..."):
                try:
                    path = generate_design(design)
                    st.success(f"Generated {path.name}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Generation failed: {exc}")
            st.rerun()

        st.subheader("Reference")
        references = design.reference_images()
        if references:
            for image in references:
                st.image(str(image), use_container_width=True)
        else:
            st.caption("No reference image.")

    if not outputs:
        st.info(
            "No `.3mf` files yet. Click **Regenerate**, or run "
            f"`poetry run generate {design.name}`."
        )
        return

    st.caption(str(selected_path))
    render_model(selected_path, show_grid=show_grid)


def main() -> None:
    designs = designs_module.discover()
    designs_by_name = {d.name: d for d in designs}

    selected_name = st.query_params.get("design")
    if selected_name and selected_name in designs_by_name:
        show_detail(designs_by_name[selected_name])
    else:
        if selected_name:
            # Stale query param (design was removed); reset to gallery.
            st.query_params.clear()
        show_gallery(designs)


main()
