# Copyright (c) 2026. TFM: G1 valve manipulation.
# SPDX-License-Identifier: Apache-2.0
"""Faithful 3D preview of the hand-wheel valve model (host-side, no Isaac Sim needed).

Reconstructs the exact geometry authored in generate_valve_usd.py and renders the wheel at
three rotation angles so the valve shape and its actuation are visible at a glance.
"""

import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# --- geometry constants (must match generate_valve_usd.py) ---
PILLAR_R, WHEEL_Z, STUB_LEN = 0.04, 0.95, 0.12
MAJOR_R, TUBE_R = 0.16, 0.018
HUB_R, HUB_LEN = 0.03, 0.06
SPOKE_R, N_SPOKES = 0.012, 4
C = np.array([-STUB_LEN, 0.0, WHEEL_Z])  # wheel centre in valve-local frame
GREY, RED, YEL = "#8f9296", "#bf2620", "#f4c020"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "_valve_preview", "valve_model_angles.png")


def rot_x(pts, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = pts[..., 0], pts[..., 1], pts[..., 2]
    return np.stack([x, y * c - z * s, y * s + z * c], axis=-1)


def draw_cyl_z(ax, r, z0, z1, color, n=40):
    th = np.linspace(0, 2 * np.pi, n)
    zc = np.linspace(z0, z1, 2)
    T, Z = np.meshgrid(th, zc)
    ax.plot_surface(r * np.cos(T), r * np.sin(T), Z, color=color, alpha=0.95, linewidth=0, shade=True)


def draw_cyl_x(ax, r, x0, x1, center, color, n=24):
    th = np.linspace(0, 2 * np.pi, n)
    xc = np.linspace(x0, x1, 2)
    T, X = np.meshgrid(th, xc)
    ax.plot_surface(X + center[0], r * np.cos(T) + center[1], r * np.sin(T) + center[2],
                    color=color, alpha=0.95, linewidth=0, shade=True)


def draw_torus(ax, angle, n_u=60, n_v=18):
    u = np.linspace(0, 2 * np.pi, n_u)
    v = np.linspace(0, 2 * np.pi, n_v)
    U, V = np.meshgrid(u, v)
    x = TUBE_R * np.sin(V)
    y = (MAJOR_R + TUBE_R * np.cos(V)) * np.cos(U)
    z = (MAJOR_R + TUBE_R * np.cos(V)) * np.sin(U)
    pts = rot_x(np.stack([x, y, z], axis=-1), angle) + C
    ax.plot_surface(pts[..., 0], pts[..., 1], pts[..., 2], color=RED, alpha=0.95, linewidth=0, shade=True)


def draw_valve(ax, angle):
    # ground
    gx, gy = np.meshgrid(np.linspace(-0.5, 0.5, 2), np.linspace(-0.5, 0.5, 2))
    ax.plot_surface(gx, gy, np.zeros_like(gx), color="#dfe3e8", alpha=0.35, linewidth=0)
    # pillar + axle stub (fixed, grey)
    draw_cyl_z(ax, PILLAR_R, 0.0, WHEEL_Z, GREY)
    draw_cyl_x(ax, PILLAR_R * 0.6, -STUB_LEN, 0.0, np.array([0, 0, WHEEL_Z]), GREY)
    # wheel: hub + rim + spokes (rotates)
    draw_cyl_x(ax, HUB_R, -HUB_LEN / 2, HUB_LEN / 2, C, RED)
    draw_torus(ax, angle)
    for k in range(N_SPOKES):
        a = math.radians(360.0 * k / N_SPOKES) + math.radians(angle)
        p0 = C + np.array([0, HUB_R * math.cos(a), HUB_R * math.sin(a)])
        p1 = C + np.array([0, MAJOR_R * math.cos(a), MAJOR_R * math.sin(a)])
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]], color=RED, linewidth=4)
    # tracking marker on the rim to make rotation obvious
    am = math.radians(angle)
    m = C + np.array([0, MAJOR_R * math.cos(am), MAJOR_R * math.sin(am)])
    ax.scatter([m[0]], [m[1]], [m[2]], color=YEL, s=60, depthshade=False)
    # framing
    ax.set_xlim(-0.35, 0.15)
    ax.set_ylim(-0.25, 0.25)
    ax.set_zlim(0.0, 1.15)
    ax.set_box_aspect((0.5, 0.5, 1.15))
    ax.view_init(elev=12, azim=-72)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    ax.set_axis_off()


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    angles = [(0.0, "Cerrada  0%  (0°)"), (165.0, "~46%  (165°)"), (330.0, "Abierta ~92%  (330°)")]
    fig = plt.figure(figsize=(15, 6))
    for i, (ang, title) in enumerate(angles, 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        draw_valve(ax, ang)
        ax.set_title(title, fontsize=13, color="#222")
    fig.suptitle("Válvula de volante (modelo procedural)  ·  el volante gira sobre valve_joint (eje X)",
                 fontsize=13, y=0.93)
    fig.tight_layout()
    fig.savefig(os.path.abspath(OUT), dpi=130, bbox_inches="tight")
    print("WROTE", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
