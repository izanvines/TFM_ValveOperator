# Vuelca los parametros de fisica del rig de la valvula tal y como quedan COMPUESTOS
# (valve_rig_arena.usda -> valve_rig.usdz), que es lo que ve Isaac Sim.
from pxr import Usd, UsdGeom, UsdPhysics, Gf  # noqa: F401

STAGE = "/workspaces/isaaclab_arena/isaaclab_arena/assets/usd/valve_rig_arena.usda"
stage = Usd.Stage.Open(STAGE)

print("=" * 78)
for prim in stage.Traverse():
    path = str(prim.GetPath())
    tipo = prim.GetTypeName()

    if tipo in ("PhysicsRevoluteJoint", "PhysicsFixedJoint"):
        print(f"\n--- {tipo}  {path}")
        for a in prim.GetAttributes():
            n = a.GetName()
            if n.startswith(("physics:", "drive:", "physxJoint:", "limit:")):
                print(f"    {n:48s} = {a.Get()}")
        for rel in prim.GetRelationships():
            print(f"    [rel] {rel.GetName():42s} = {rel.GetTargets()}")

    if prim.IsA(UsdGeom.Mesh):
        api = UsdPhysics.CollisionAPI(prim)
        tiene_col = prim.HasAPI(UsdPhysics.CollisionAPI)
        meshcol = UsdPhysics.MeshCollisionAPI(prim)
        aprox = meshcol.GetApproximationAttr().Get() if prim.HasAPI(UsdPhysics.MeshCollisionAPI) else None
        pts = prim.GetAttribute("points").Get()
        print(f"\n--- Mesh {path}")
        print(f"    puntos            = {len(pts) if pts else 0}")
        print(f"    CollisionAPI      = {tiene_col}")
        print(f"    aproximacion      = {aprox}")
        if tiene_col:
            en = api.GetCollisionEnabledAttr().Get()
            print(f"    collisionEnabled  = {en}")

    if prim.HasAPI(UsdPhysics.MassAPI):
        m = UsdPhysics.MassAPI(prim)
        print(f"\n--- MassAPI {path}")
        print(f"    mass              = {m.GetMassAttr().Get()}")
        print(f"    density           = {m.GetDensityAttr().Get()}")
        print(f"    diagonalInertia   = {m.GetDiagonalInertiaAttr().Get()}")

    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
        rb = UsdPhysics.RigidBodyAPI(prim)
        print(f"\n--- RigidBodyAPI {path}  enabled={rb.GetRigidBodyEnabledAttr().Get()} kinematic={rb.GetKinematicEnabledAttr().Get()}")

    if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
        print(f"\n--- ArticulationRootAPI {path}")
print("=" * 78)
