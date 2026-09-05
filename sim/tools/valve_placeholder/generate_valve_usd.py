# Copyright (c) 2026. TFM: G1 valve manipulation.
# SPDX-License-Identifier: Apache-2.0
"""Procedurally author a hand-wheel valve as a fixed-base articulation USD.

The result is a *standpipe* valve: a vertical fixed pillar with a hand-wheel at
graspable height. The wheel is a separate rigid link connected to the pillar by a
single revolute joint (``valve_joint``) whose axis points toward the robot (+X in the
scene once placed), so the humanoid reaches forward and turns the wheel to "open" it.

Design constraints baked in so it plugs into Isaac Lab-Arena's ``Openable`` affordance:
  * Finite joint limits (0 deg = closed, 360 deg = fully open) -- required by
    ``get_normalized_joint_position`` (infinite limits -> NaN openness).
  * A fixed-base articulation (ArticulationRootAPI on the root, a FixedJoint to world)
    so the pillar never moves.
  * A viscous drive (stiffness 0, damping > 0) so the wheel holds where the robot
    leaves it instead of free-spinning.

Run with any interpreter that has ``pxr`` (host: env_isaaclab):
    python tools/valve/generate_valve_usd.py
"""

from __future__ import annotations

import math
import os

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

# ---------------------------------------------------------------------------
# Geometry parameters (metres). Tuned for a G1 reaching forward at chest height.
# ---------------------------------------------------------------------------
PILLAR_RADIUS = 0.04
WHEEL_CENTER_Z = 0.95          # hand-wheel height above the ground
STUB_LEN = 0.12                # axle housing sticking out toward the robot (-X)
WHEEL_MAJOR_R = 0.16           # rim radius  -> ~0.32 m diameter wheel
WHEEL_TUBE_R = 0.018           # thickness of the rim tube
HUB_RADIUS = 0.03
HUB_LEN = 0.06
SPOKE_RADIUS = 0.012
NUM_SPOKES = 4
TORUS_MAJOR_SEG = 48
TORUS_MINOR_SEG = 12

WHEEL_CENTER = Gf.Vec3f(-STUB_LEN, 0.0, WHEEL_CENTER_Z)  # in /Valve local frame

GREY = (0.55, 0.57, 0.60)
RED = (0.75, 0.15, 0.12)

OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "isaaclab_arena", "assets", "usd", "valve_handwheel_v1.usda"
)


def _set_color(gprim, rgb):
    gprim.CreateDisplayColorAttr([Gf.Vec3f(*rgb)])


def _add_translate(prim, xyz):
    UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3f(*xyz))


def _make_torus_mesh(stage, path, major_r, tube_r, major_seg, minor_seg):
    """A torus lying in the YZ plane (tube axis along X), centred at the prim origin."""
    pts, counts, indices = [], [], []
    for i in range(major_seg):
        u = 2.0 * math.pi * i / major_seg
        cy, cz = math.cos(u), math.sin(u)  # radial direction in YZ
        for j in range(minor_seg):
            v = 2.0 * math.pi * j / minor_seg
            r = major_r + tube_r * math.cos(v)
            pts.append(Gf.Vec3f(tube_r * math.sin(v), r * cy, r * cz))
    for i in range(major_seg):
        for j in range(minor_seg):
            a = i * minor_seg + j
            b = ((i + 1) % major_seg) * minor_seg + j
            c = ((i + 1) % major_seg) * minor_seg + (j + 1) % minor_seg
            d = i * minor_seg + (j + 1) % minor_seg
            counts.append(4)
            indices.extend([a, b, c, d])
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(pts)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr("none")
    return mesh


def main():
    stage = Usd.Stage.CreateNew(os.path.abspath(OUT_PATH))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)

    # Root articulation prim -----------------------------------------------------
    valve = UsdGeom.Xform.Define(stage, "/Valve")
    stage.SetDefaultPrim(valve.GetPrim())
    UsdPhysics.ArticulationRootAPI.Apply(valve.GetPrim())

    # --- Pillar link (fixed base): vertical standpipe + horizontal axle stub -----
    pillar = UsdGeom.Xform.Define(stage, "/Valve/pillar")
    UsdPhysics.RigidBodyAPI.Apply(pillar.GetPrim())
    UsdPhysics.MassAPI.Apply(pillar.GetPrim()).CreateMassAttr(20.0)

    shaft = UsdGeom.Cylinder.Define(stage, "/Valve/pillar/shaft")
    shaft.CreateAxisAttr("Z")
    shaft.CreateRadiusAttr(PILLAR_RADIUS)
    shaft.CreateHeightAttr(WHEEL_CENTER_Z)
    shaft.CreateExtentAttr([(-PILLAR_RADIUS, -PILLAR_RADIUS, -WHEEL_CENTER_Z / 2),
                            (PILLAR_RADIUS, PILLAR_RADIUS, WHEEL_CENTER_Z / 2)])
    _add_translate(shaft.GetPrim(), (0.0, 0.0, WHEEL_CENTER_Z / 2))
    UsdPhysics.CollisionAPI.Apply(shaft.GetPrim())
    _set_color(shaft, GREY)

    stub = UsdGeom.Cylinder.Define(stage, "/Valve/pillar/stub")
    stub.CreateAxisAttr("X")
    stub.CreateRadiusAttr(PILLAR_RADIUS * 0.6)
    stub.CreateHeightAttr(STUB_LEN)
    stub.CreateExtentAttr([(-STUB_LEN / 2, -PILLAR_RADIUS, -PILLAR_RADIUS),
                           (STUB_LEN / 2, PILLAR_RADIUS, PILLAR_RADIUS)])
    _add_translate(stub.GetPrim(), (-STUB_LEN / 2, 0.0, WHEEL_CENTER_Z))
    UsdPhysics.CollisionAPI.Apply(stub.GetPrim())
    _set_color(stub, GREY)

    # Fix the pillar to the world -------------------------------------------------
    fixed = UsdPhysics.FixedJoint.Define(stage, "/Valve/fixed_joint")
    fixed.CreateBody1Rel().SetTargets(["/Valve/pillar"])
    fixed.CreateLocalPos0Attr(Gf.Vec3f(0, 0, 0))
    fixed.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))

    # --- Wheel link (rotates): hub + torus rim + spokes --------------------------
    wheel = UsdGeom.Xform.Define(stage, "/Valve/wheel")
    UsdGeom.Xformable(wheel).AddTranslateOp().Set(WHEEL_CENTER)
    UsdPhysics.RigidBodyAPI.Apply(wheel.GetPrim())
    UsdPhysics.MassAPI.Apply(wheel.GetPrim()).CreateMassAttr(1.0)

    hub = UsdGeom.Cylinder.Define(stage, "/Valve/wheel/hub")
    hub.CreateAxisAttr("X")
    hub.CreateRadiusAttr(HUB_RADIUS)
    hub.CreateHeightAttr(HUB_LEN)
    hub.CreateExtentAttr([(-HUB_LEN / 2, -HUB_RADIUS, -HUB_RADIUS), (HUB_LEN / 2, HUB_RADIUS, HUB_RADIUS)])
    UsdPhysics.CollisionAPI.Apply(hub.GetPrim())
    _set_color(hub, RED)

    rim = _make_torus_mesh(stage, "/Valve/wheel/rim", WHEEL_MAJOR_R, WHEEL_TUBE_R, TORUS_MAJOR_SEG, TORUS_MINOR_SEG)
    UsdPhysics.CollisionAPI.Apply(rim.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(rim.GetPrim()).CreateApproximationAttr("convexDecomposition")
    _set_color(rim, RED)

    for k in range(NUM_SPOKES):
        ang = 2.0 * math.pi * k / NUM_SPOKES
        spoke_x = UsdGeom.Xform.Define(stage, f"/Valve/wheel/spoke_{k}")
        UsdGeom.Xformable(spoke_x).AddRotateXOp().Set(math.degrees(ang))
        cyl = UsdGeom.Cylinder.Define(stage, f"/Valve/wheel/spoke_{k}/cyl")
        cyl.CreateAxisAttr("Y")
        cyl.CreateRadiusAttr(SPOKE_RADIUS)
        cyl.CreateHeightAttr(WHEEL_MAJOR_R)
        cyl.CreateExtentAttr([(-SPOKE_RADIUS, -WHEEL_MAJOR_R / 2, -SPOKE_RADIUS),
                              (SPOKE_RADIUS, WHEEL_MAJOR_R / 2, SPOKE_RADIUS)])
        _add_translate(cyl.GetPrim(), (0.0, WHEEL_MAJOR_R / 2, 0.0))
        _set_color(cyl, RED)

    # Revolute joint: pillar -> wheel, axis X (points toward the robot once placed) --
    rev = UsdPhysics.RevoluteJoint.Define(stage, "/Valve/valve_joint")
    rev.CreateAxisAttr("X")
    rev.CreateLowerLimitAttr(0.0)
    rev.CreateUpperLimitAttr(360.0)
    rev.CreateBody0Rel().SetTargets(["/Valve/pillar"])
    rev.CreateBody1Rel().SetTargets(["/Valve/wheel"])
    rev.CreateLocalPos0Attr(WHEEL_CENTER)            # anchor in pillar frame
    rev.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))       # anchor in wheel frame (its origin)

    drive = UsdPhysics.DriveAPI.Apply(rev.GetPrim(), "angular")
    drive.CreateTypeAttr("force")
    drive.CreateStiffnessAttr(0.0)
    drive.CreateDampingAttr(15.0)                    # viscous hold / turning resistance
    drive.CreateTargetVelocityAttr(0.0)

    stage.GetRootLayer().Save()
    print(f"WROTE {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
