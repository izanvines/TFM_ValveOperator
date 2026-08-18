# Mide donde acaba el robot de `g1_valve` y donde queda la rueda de la valvula, para el
# rig CAD (`valve_rig_arena.usda`).
#
# Por que existe otro script: `measure_valve_reach.py` muere sin imprimir nada (su log del
# 2026-08-05 acaba en los mismos warnings de qpsolvers), y ademas calculaba la posicion de
# la rueda con un offset hardcodeado de la valvula procedural (`raiz[0] - 0.12`, z=0.95)
# que ya no aplica: el rig CAD lleva la rueda en +Z local, no en -X.
#
# Diferencias:
#   * lee la posicion REAL del cuerpo de la rueda en la articulacion, sin asumir offsets
#   * imprime con flush segun avanza, para ver donde muere si muere
#   * envuelve el bucle de fisica en try/except para dar el diagnostico aunque pete
#
# Uso (sin XR, sin gafas):
#   docker exec isaaclab_arena-latest bash -c "cd /workspaces/isaaclab_arena && \
#     unset DISPLAY && export HOME=/home/ivines && \
#     /isaac-sim/python.sh -u /eval/arena_extras/measure_valve_rig.py \
#     --device cpu --settle_steps 60 g1_valve --background none"

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--settle_steps", type=int, default=60, help="pasos de simulacion antes de medir")
parser.add_argument(
    "--repeats",
    type=int,
    default=1,
    help=(
        "cuantas veces resetear y volver a asentar. El entorno corre con seed=None, asi que "
        "el asentamiento del WBC NO es reproducible: mide la dispersion antes de fiarte de un "
        "solo numero para colocar la valvula."
    ),
)
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import torch  # noqa: E402

from isaaclab_arena_environments.cli import get_arena_builder_from_cli  # noqa: E402


def _t(x):
    """IsaacLab puede devolver `wp.array` (backend Newton/Warp) en vez de tensores torch."""
    try:
        import warp as wp

        if isinstance(x, wp.array):
            return wp.to_torch(x)
    except Exception:
        pass
    return x


def _p(v) -> str:
    return f"({float(v[0]):+.3f}, {float(v[1]):+.3f}, {float(v[2]):+.3f})"


def log(msg: str) -> None:
    print(msg, flush=True)


def _hold_action(unwrapped):
    """Accion que mantiene al robot de pie con una pose de brazos estable.

    NO usar la accion de ceros: el indice [19] es base_height_cmd, y un cero le pide al WBC
    pelvis a 0 m -- el robot se acuclilla y se sienta, asi que se mediria un robot tumbado.
    Los indices [2:16] son las poses de muneca, que a cero apuntan al origen de la pelvis y
    meten las manos dentro del cuerpo. Mismos valores que `hold_pose_policy.py`.
    """
    import torch as _torch

    dev = unwrapped.device
    a = _torch.zeros((unwrapped.num_envs, unwrapped.action_manager.total_action_dim), device=dev)
    a[:, 2:5] = _torch.tensor([0.22, 0.20, 0.05], device=dev)  # muneca izq
    a[:, 5:9] = _torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)  # quat xyzw
    a[:, 9:12] = _torch.tensor([0.22, -0.20, 0.05], device=dev)  # muneca der
    a[:, 12:16] = _torch.tensor([0.0, 0.0, 0.0, 1.0], device=dev)
    a[:, 19] = 0.75  # base_height_cmd (g1_decoupled_wbc_joint_action.py:86)
    return a


def main() -> None:
    log(">> construyendo entorno")
    env = get_arena_builder_from_cli(args_cli).make_registered()
    log(">> reset")
    env.reset()

    unwrapped = env.unwrapped
    scene = unwrapped.scene
    robot = scene["robot"]
    nombres = list(robot.body_names)
    pelvis_idx = nombres.index("pelvis")
    izq_idx = nombres.index("left_wrist_yaw_link")
    der_idx = nombres.index("right_wrist_yaw_link")

    valvula = None
    for nombre in list(scene.keys()):
        if "valve" in str(nombre).lower():
            valvula = scene[nombre]
            break

    if valvula is None:
        log("!! la valvula no esta en la escena")
    else:
        log(f">> valvula: bodies={list(valvula.body_names)}")
        log(f">> valvula: joints={list(valvula.joint_names)}")
        lim = _t(valvula.data.joint_pos_limits)[0]
        for i, jn in enumerate(valvula.joint_names):
            lo, hi = float(lim[i][0]), float(lim[i][1])
            import math

            log(
                f"   joint '{jn}': [{lo:.4f}, {hi:.4f}] rad = "
                f"[{math.degrees(lo):.1f}, {math.degrees(hi):.1f}] deg "
                f"-> recorrido {math.degrees(hi - lo) / 360:.2f} vuelta(s)"
            )

    # indice del cuerpo de la rueda: el que NO esta fijado al mundo
    rueda_idx = None
    if valvula is not None:
        for i, bn in enumerate(valvula.body_names):
            if "wheel" in bn.lower() or "50_AL" in bn:
                rueda_idx = i
                break
        if rueda_idx is None and len(valvula.body_names) > 1:
            rueda_idx = 1
        log(f">> cuerpo de la rueda: idx={rueda_idx} nombre={valvula.body_names[rueda_idx] if rueda_idx is not None else None}")

    inicial = _t(robot.data.body_pos_w)[0, pelvis_idx].clone()
    log(f">> pelvis al resetear: {_p(inicial)}")

    if args_cli.repeats > 1:
        asentados = []
        for r in range(args_cli.repeats):
            env.reset()
            accion = _hold_action(unwrapped)
            for _ in range(args_cli.settle_steps):
                env.step(accion)
            p = _t(robot.data.body_pos_w)[0, pelvis_idx].clone()
            asentados.append(p)
            log(f"   repeticion {r + 1}/{args_cli.repeats}: pelvis asentada {_p(p)}")
        apilado = torch.stack(asentados)
        media = apilado.mean(dim=0)
        desv = apilado.std(dim=0) if len(asentados) > 1 else torch.zeros_like(media)
        rango = apilado.max(dim=0).values - apilado.min(dim=0).values
        log("\n" + "-" * 72)
        log(f"DISPERSION DEL ASENTAMIENTO sobre {args_cli.repeats} resets")
        log(f"  media  : {_p(media)}")
        log(f"  desv   : {_p(desv)}")
        log(f"  rango  : {_p(rango)}   <- margen que necesita la colocacion de la valvula")
        log("-" * 72 + "\n")

    # NO usar la accion de ceros: el indice [19] es base_height_cmd, y un cero le pide al
    # WBC pelvis a 0 m -- el robot se acuclilla y se sienta en el suelo, asi que la medida
    # sale de un robot tumbado. Y los indices [2:16] son las poses de muneca, que a cero
    # apuntan al origen de la pelvis y meten las manos dentro del cuerpo. Se usan los
    # mismos valores que `hold_pose_policy.py`: pose "en L" estable y pelvis a 0.75 m
    # (`g1_decoupled_wbc_joint_action.py:86`).
    action = torch.zeros((unwrapped.num_envs, unwrapped.action_manager.total_action_dim), device=unwrapped.device)
    action[:, 2:5] = torch.tensor([0.22, 0.20, 0.05], device=unwrapped.device)  # muneca izq
    action[:, 5:9] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=unwrapped.device)  # quat xyzw
    action[:, 9:12] = torch.tensor([0.22, -0.20, 0.05], device=unwrapped.device)  # muneca der
    action[:, 12:16] = torch.tensor([0.0, 0.0, 0.0, 1.0], device=unwrapped.device)
    action[:, 19] = 0.75  # base_height_cmd
    log(f">> accion 'hold pose' (base_height=0.75), dim={action.shape[1]}; asentando {args_cli.settle_steps} pasos")
    try:
        for i in range(args_cli.settle_steps):
            env.step(action)
            if (i + 1) % 20 == 0:
                p = _t(robot.data.body_pos_w)[0, pelvis_idx]
                log(f"   paso {i + 1}: pelvis {_p(p)}")
    except Exception as exc:  # noqa: BLE001
        log(f"!! el bucle de fisica ha petado en el paso {i}: {type(exc).__name__}: {exc}")

    cuerpos = _t(robot.data.body_pos_w)
    final, izq, der = cuerpos[0, pelvis_idx], cuerpos[0, izq_idx], cuerpos[0, der_idx]

    log("\n" + "=" * 72)
    log("MEDIDA DE ALCANCE  g1_valve  (rig CAD)")
    log("=" * 72)
    log(f"  pelvis al resetear    : {_p(inicial)}")
    log(f"  pelvis tras asentar   : {_p(final)}   ({args_cli.settle_steps} pasos)")
    log(f"  DERIVA de la pelvis   : {_p(final - inicial)}")
    log(f"  muneca izquierda      : {_p(izq)}")
    log(f"  muneca derecha        : {_p(der)}")
    if valvula is not None:
        raiz = _t(valvula.data.root_pos_w)[0]
        log(f"  valvula (raiz)        : {_p(raiz)}")
        if rueda_idx is not None:
            rueda = _t(valvula.data.body_pos_w)[0, rueda_idx]
            log(f"  rueda (MEDIDA real)   : {_p(rueda)}")
            log("  ---")
            log(f"  pelvis -> rueda       : {float(torch.norm(rueda - final)):.3f} m")
            log(f"     en X (frontal)     : {float(rueda[0] - final[0]):+.3f} m")
            log(f"     en Z (altura)      : {float(rueda[2] - final[2]):+.3f} m")
            log(f"  muneca_izq -> rueda   : {float(torch.norm(rueda - izq)):.3f} m")
            log(f"  muneca_der -> rueda   : {float(torch.norm(rueda - der)):.3f} m")
    log("=" * 72 + "\n")

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
