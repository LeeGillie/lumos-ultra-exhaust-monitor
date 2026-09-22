"""
Shaded renders of the enclosure fitment model (cad/out/render_*.png).

    python cad/render.py [--populate laser|fan]

Uses the same parametric model as enclosure.py, so the pictures can never drift
from the geometry. The box is drawn as a translucent shell so the internals show.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import cadquery as cq
import enclosure as enc


def triangles(shape: cq.Workplane | cq.Shape, tol: float = 0.4):
    s = shape.val() if isinstance(shape, cq.Workplane) else shape
    verts, faces = s.tessellate(tol)
    pts = [(v.x, v.y, v.z) for v in verts]
    return [[pts[i] for i in f] for f in faces]


def add(ax, shape, color, alpha=1.0, lw=0.0):
    tris = triangles(shape)
    coll = Poly3DCollection(tris, facecolors=color, edgecolors=(0, 0, 0, 0.25 if lw else 0),
                            linewidths=lw, alpha=alpha)
    coll.set_sort_zpos(0)
    ax.add_collection3d(coll)


def render(populate: str, out: Path) -> None:
    parts = enc.build_parts(populate)
    shell = enc.box_shell()

    views = [("render_iso.png", 22, -60, "LumosAir node — populated for the %s box" % populate),
             ("render_top.png", 89, -90, "Top view (lid removed)"),
             ("render_front.png", 4, -89, "Front view through the port wall")]

    for fname, elev, azim, title in views:
        fig = plt.figure(figsize=(11, 7), dpi=110)
        ax = fig.add_subplot(111, projection="3d")
        add(ax, shell, (0.62, 0.64, 0.67), alpha=0.10, lw=0.0)
        for p in parts:
            add(ax, p.solid(), p.color[:3], alpha=1.0, lw=0.15)
            if p.name.startswith("SDP810"):
                add(ax, enc.sdp_barbs(p), (0.93, 0.78, 0.2), alpha=1.0)

        ax.set_box_aspect((enc.BOX_OUT_L, enc.BOX_OUT_W, enc.BOX_OUT_H))
        ax.set_xlim(-enc.WALL, enc.BOX_IN_L + enc.WALL)
        ax.set_ylim(-enc.WALL, enc.BOX_IN_W + enc.WALL)
        ax.set_zlim(-enc.WALL, enc.BOX_IN_H + 4)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)"); ax.set_zlabel("z (mm)")
        ax.set_title(title, fontsize=12)
        ax.grid(False)
        for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
            pane.pane.set_alpha(0.0)

        # legend
        seen: dict[str, tuple] = {}
        for p in parts:
            key = p.name.split("#")[0].strip()
            seen.setdefault(key, p.color[:3])
        handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=8, color=c, label=k)
                   for k, c in seen.items()]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(-0.12, 0.95),
                  fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(out / fname, bbox_inches="tight")
        plt.close(fig)
        print("wrote", out / fname)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--populate", choices=["laser", "fan"], default="laser")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    a = ap.parse_args()
    o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
    render(a.populate, o)
