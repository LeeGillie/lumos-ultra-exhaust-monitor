"""
Shaded renders of the enclosure fitment model (cad/out/render_*.png).

    python cad/render.py [--populate laser|fan] [--box auto|F|G|J|H] [--mcu module|devkit]

Uses the same parametric model as enclosure.py, so the pictures can never drift
from the geometry. The box is drawn as a translucent shell so the internals — and
in particular the hose runs — show through.
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


TUBE_COLOR = (0.90, 0.45, 0.15)


def render(d: enc.Design, out: Path) -> None:
    il, iw, ih = d.box.inside
    ol, ow, oh = d.box.out
    shell = enc.box_shell(d.box, d.switch_z, d.fittings)

    views = [
        ("render_iso.png", 24, -62,
         f"LumosAir node — {d.populate} box, {d.box.code}"),
        ("render_top.png", 89, -90, "Top view through the clear lid"),
        ("render_front.png", 6, -89, "Front view — the port wall and the hose runs"),
        ("render_side.png", 8, 0, "Side view — the two-board stack"),
    ]

    for fname, elev, azim, title in views:
        fig = plt.figure(figsize=(11, 7), dpi=110)
        ax = fig.add_subplot(111, projection="3d")
        add(ax, shell, (0.62, 0.64, 0.67), alpha=0.10, lw=0.0)
        for x, z, lab in d.port_labels:
            add(ax, enc.bulkhead(d.box, x, z), (0.72, 0.70, 0.62), alpha=0.9)
        for p in d.parts:
            add(ax, p.solid(), p.color[:3], alpha=1.0, lw=0.15)
        for t in d.tubes:
            add(ax, t.solid(), TUBE_COLOR, alpha=1.0)

        ax.set_box_aspect((ol, ow, oh))
        ax.set_xlim(-enc.WALL, il + enc.WALL)
        ax.set_ylim(-enc.WALL, iw + enc.WALL)
        ax.set_zlim(-enc.WALL, ih + 4)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)"); ax.set_zlabel("z (mm)")
        ax.set_title(title, fontsize=12)
        ax.grid(False)
        for pane in (ax.xaxis, ax.yaxis, ax.zaxis):
            pane.pane.set_alpha(0.0)

        seen: dict[str, tuple] = {}
        for p in d.parts:
            if p.name in ("standoff", "spacer"):
                continue
            key = p.name.split("#")[0].strip()
            for prefix in ("SDP810 ", "XGZP ", "barb ", "elbow "):
                if key.startswith(prefix):
                    key = prefix.strip() + "s"
            seen.setdefault(key, p.color[:3])
        seen["silicone hose"] = TUBE_COLOR
        handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=8, color=c, label=k)
                   for k, c in seen.items()]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(-0.14, 0.97),
                  fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(out / fname, bbox_inches="tight")
        plt.close(fig)
        print("wrote", out / fname)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--populate", choices=["laser", "fan"], default="laser")
    ap.add_argument("--box", choices=list(enc.BOXES) + ["auto"], default="auto")
    ap.add_argument("--mcu", choices=["module", "devkit"], default="module")
    ap.add_argument("--fittings", choices=["elbow", "straight"], default="elbow")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    a = ap.parse_args()
    o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
    code = enc.pick_box(a.populate, a.mcu, a.fittings) if a.box == "auto" else a.box
    render(enc.build(a.populate, code, a.mcu, a.fittings), o)
