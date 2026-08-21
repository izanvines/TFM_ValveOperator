# Copyright (c) 2026. TFM Universidad de Leon -- G1 abriendo valvulas de volante.
# SPDX-License-Identifier: Apache-2.0
"""Vuelve a renderizar las imagenes de un HDF5 grabado, con otro fondo y sin XR.

**Por que existe.** El fondo Gaussian-Splatting de la oficina tiene que acabar en la camara del
robot, porque esa imagen ES la entrada de la politica. Pero NO puede estar en la vista del casco: el
splat se ve pixelado y con zonas negras en el producto de render de XR (problema abierto desde el
2026-08-04), y ademas 2,1 M de gaussianas en estereo tiraron la teleoperacion de 20 a 2 FPS.

La salida es separar las dos cosas:

    etapa A   teleoperar en la escena diafana y grabar SOLO las acciones   (record_demos.py)
    etapa B   volver a renderizar las imagenes con el fondo, sin XR        (este script)

No es un apano para esquivar el bug: desacopla la comodidad del operador del coste de render. En la
etapa B se puede usar el splat completo (3,96 M de gaussianas) porque ya no hay nadie esperando.

**Como funciona.** Es `isaaclab_arena/scripts/imitation_learning/replay_demos.py` con un cambio:
donde aquel hace `env_cfg.recorders = {}`, aqui se ponen los recorders de grabacion. El resto ya
estaba resuelto en upstream -- `env.reset_to(initial_state, is_relative=True)` restaura el estado
inicial exacto de cada episodio (incluida la pose de la valvula) y luego se reproducen las acciones
paso a paso. Los recorders se disparan solos desde `ManagerBasedRLEnv.step()`.

**El embodiment tiene que ser el de la grabacion** (`g1_wbc_agile_pink`): el HDF5 guarda acciones
crudas de 23 dims, que son las que ese embodiment consume, y usa `CameraCfg` (no tiled) mientras que
`g1_wbc_agile_joint` usa `TiledCameraCfg` -- dos rutas de render distintas.

Uso (dentro del contenedor, desde la raiz de Arena):

    /isaac-sim/python.sh -u /eval/arena_extras/rerender_demos.py \
        --dataset_file /datasets/isaaclab_arena/g1_valve/sesion_01.hdf5 \
        --output_file  /datasets/isaaclab_arena/g1_valve/sesion_01_office.hdf5 \
        --enable_cameras --device cuda:0 \
        g1_valve --background office_gs --embodiment g1_wbc_agile_pink
"""

import os

from isaaclab.app import AppLauncher

from isaaclab_arena.cli.isaaclab_arena_cli import get_isaaclab_arena_cli_parser
from isaaclab_arena_environments.cli import add_example_environments_cli_args, get_arena_builder_from_cli

parser = get_isaaclab_arena_cli_parser()
parser.add_argument("--dataset_file", type=str, required=True, help="HDF5 de entrada (no se modifica)")
parser.add_argument("--output_file", type=str, required=True, help="HDF5 de salida")
parser.add_argument(
    "--select_episodes",
    type=int,
    nargs="+",
    default=[],
    help="indices de episodio a re-renderizar; vacio = todos",
)
parser.add_argument(
    "--libre",
    action="store_true",
    default=False,
    help="reproduce en lazo abierto, sin imponer los estados grabados (comportamiento anterior)",
)
parser.add_argument(
    "--validate_states",
    action="store_true",
    default=False,
    help="compara el estado reproducido contra el grabado, paso a paso (tolerancia 0.01)",
)
add_example_environments_cli_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(vars(args_cli))
simulation_app = app_launcher.app

import contextlib  # noqa: E402
import gymnasium as gym  # noqa: E402
import h5py  # noqa: E402
import torch  # noqa: E402

from isaaclab.managers import DatasetExportMode  # noqa: E402
from isaaclab.utils.datasets import HDF5DatasetFileHandler  # noqa: E402

from isaaclab_arena.utils.isaaclab_utils.recorders import ArenaEnvRecorderManagerCfg  # noqa: E402


def comparar_estados(estado_dataset, estado_runtime, env_index) -> tuple[bool, str]:
    """Compara el estado reproducido contra el grabado. Tolerancia absoluta de 0.01 por componente.

    A diferencia de `compare_states` de replay_demos.py, aqui se APLANAN los dos lados antes de
    comparar. Aquel revienta con "Forma distinta" porque el estado guardado y el de runtime no
    siempre traen el mismo numero de dimensiones para el mismo campo (p. ej. `root_pose` de la
    valvula sale como (1,7) por un lado y (7,) por el otro); lo que importa son los 7 numeros, no
    como estan envueltos.
    """
    coinciden = True
    log = ""
    for tipo in ["articulation", "rigid_object"]:
        for nombre in estado_runtime.get(tipo, {}).keys():
            if nombre not in estado_dataset.get(tipo, {}):
                continue
            for campo in estado_runtime[tipo][nombre].keys():
                if campo not in estado_dataset[tipo][nombre]:
                    continue
                rt = torch.as_tensor(estado_runtime[tipo][nombre][campo][env_index]).flatten()
                ds = torch.as_tensor(estado_dataset[tipo][nombre][campo]).flatten()
                if ds.numel() != rt.numel():
                    log += f'  ["{tipo}"]["{nombre}"]["{campo}"]  tamanos {ds.numel()} vs {rt.numel()}\n'
                    coinciden = False
                    continue
                d = (ds.to(rt.device).float() - rt.float()).abs()
                if bool((d > 0.01).any()):
                    coinciden = False
                    i = int(d.argmax())
                    log += (f'  ["{tipo}"]["{nombre}"]["{campo}"]  max|d|={float(d.max()):.4f} '
                            f'en [{i}]: dataset {float(ds[i]):.4f} runtime {float(rt[i]):.4f}\n')
    return coinciden, log


def _a_torch(x):
    """Devuelve `x` como tensor de torch, venga como venga.

    `ArticulationData` entrega estos campos como `wp.array` en unas rutas y como tensor de torch
    en otras, y `wp.array` **no admite indexado por elemento**: `data.joint_pos[0, 0]` revienta
    con `RuntimeError: Item indexing is not supported on wp.array objects`. Pasaba solo al leer
    un escalar, asi que el re-render moria despues de construir el entorno -- dos minutos de
    carga tirados por una lectura de una sola cifra.
    """
    if isinstance(x, torch.Tensor):
        return x
    import warp as wp

    return wp.to_torch(x)


def main():
    if not os.path.exists(args_cli.dataset_file):
        raise FileNotFoundError(f"No existe el HDF5 de entrada: {args_cli.dataset_file}")
    if os.path.exists(args_cli.output_file):
        raise FileExistsError(
            f"El HDF5 de salida ya existe: {args_cli.output_file}. "
            "No se sobrescribe nada: elige otro nombre o borralo tu."
        )

    lector = HDF5DatasetFileHandler()
    lector.open(args_cli.dataset_file)
    n_episodios = lector.get_num_episodes()
    if n_episodios == 0:
        print("El HDF5 no tiene episodios.")
        return

    # h5py devuelve las claves en orden ALFABETICO (demo_0, demo_1, demo_10, demo_11, demo_2...).
    # Se reordenan numericamente para que el episodio N de la salida sea el demo_N de la entrada:
    # los recorders exportan con numeracion secuencial en el orden en que se reproducen, asi que
    # reproducir en orden numerico es lo que mantiene la correspondencia. Sin esto, el demo_2 de la
    # salida seria el demo_10 de la entrada, en silencio.
    nombres = sorted(lector.get_episode_names(), key=lambda n: int(n.split("_")[1]))
    indices = args_cli.select_episodes if args_cli.select_episodes else list(range(len(nombres)))
    indices = [i for i in indices if 0 <= i < len(nombres)]
    print(f"[rerender] {len(indices)} episodios de {args_cli.dataset_file}")
    print(f"[rerender] orden de reproduccion: {[nombres[i] for i in indices[:5]]}{' ...' if len(indices) > 5 else ''}")

    arena_builder = get_arena_builder_from_cli(args_cli)
    env_name, env_cfg = arena_builder.build_registered()

    # --- LA diferencia con replay_demos.py --------------------------------------------------
    # Alli es `env_cfg.recorders = {}`. Aqui van los 7 terminos de grabacion, que es lo que hace
    # `record_demos.py:237-243` cuando se le pasa --enable_cameras.
    salida_dir = os.path.dirname(os.path.abspath(args_cli.output_file))
    salida_nombre = os.path.splitext(os.path.basename(args_cli.output_file))[0]
    env_cfg.recorders = ArenaEnvRecorderManagerCfg()
    env_cfg.recorders.dataset_export_dir_path = salida_dir
    env_cfg.recorders.dataset_filename = salida_nombre
    env_cfg.recorders.dataset_export_mode = DatasetExportMode.EXPORT_ALL
    # Exportamos A MANO al final de cada episodio, con el numero de demo de la FUENTE.
    # Con la exportacion automatica la numeracion se desplaza: el `env.reset()` inicial deja un
    # episodio en el buffer y el primer `reset_to` lo exporta como demo_0, corriendo todo lo
    # demas un puesto. Medido: 2 episodios reproducidos -> 3 demos en el fichero.
    env_cfg.recorders.export_in_record_pre_reset = False

    # Las terminaciones SI se desactivan, igual que en replay_demos.py: si el termino `success`
    # siguiera activo, el episodio acabaria al cruzar el umbral, el entorno se auto-resetearia a
    # mitad de la reproduccion y el recorder cerraria el episodio antes de tiempo.
    env_cfg.terminations = {}

    env = gym.make(env_name, cfg=env_cfg)
    from isaaclab_arena.utils.isaaclab_utils.simulation_app import reapply_viewer_cfg

    reapply_viewer_cfg(env)
    env = env.unwrapped

    validar = args_cli.validate_states and args_cli.num_envs == 1
    if args_cli.validate_states and args_cli.num_envs > 1:
        print("[rerender] AVISO: --validate_states solo funciona con --num_envs 1; se ignora")

    env.reset()

    # Umbral de exito en unidades del joint: la apertura se normaliza linealmente sobre los limites
    # del joint (`Openable.get_openness`), y el exito es apertura > 0.5. Se leen los limites del
    # propio articulado en vez de dar por hecho 0..360 grados.
    lim = _a_torch(env.scene["valve"].data.joint_pos_limits)[0, 0]
    umbral_apertura = float(lim[0] + 0.5 * (lim[1] - lim[0]))
    print(f"[rerender] umbral de exito: joint_pos >= {umbral_apertura:.4f} rad "
          f"({umbral_apertura * 180.0 / 3.141592653589793:.1f} grados)")

    reproducidos, discrepancias = 0, 0
    with contextlib.suppress(KeyboardInterrupt), torch.inference_mode():
        for idx in indices:
            episodio = lector.load_episode(nombres[idx], env.device)
            estado_inicial = episodio.get_initial_state()
            # Restaura la pose de la valvula y la del robot tal y como se grabaron. Esto es lo que
            # hace valida la etapa B cuando la valvula se aleatoriza: no se re-sortea, se restaura.
            ids_entorno = torch.tensor([0], device=env.device)
            env.reset_to(estado_inicial, ids_entorno, is_relative=True)

            pasos = 0
            apertura_max = 0.0
            while True:
                accion = episodio.get_next_action()
                if accion is None:
                    break
                env.step(accion.unsqueeze(0) if accion.ndim == 1 else accion)
                pasos += 1

                esperado = episodio.get_next_state()
                if validar and esperado is not None:
                    ok, log = comparar_estados(esperado, env.scene.get_state(is_relative=True), 0)
                    if not ok:
                        discrepancias += 1
                        if discrepancias <= 3:
                            print(f"[rerender] {nombres[idx]} paso {pasos}: estados NO coinciden\n{log}")

                # FORZADO DE ESTADO. Sin esto la reproduccion no reproduce: se desvia en el paso 1
                # y nunca vuelve. Medido en demo_14 de sesion_02 con --validate_states, el primer
                # paso ya discrepa 13.1 rad/s en `right_ankle_pitch_joint`, y 472 de 473 pasos
                # discrepan. La causa es que el HDF5 solo guarda las 23 dims de la accion, que
                # gobiernan brazos y comandos; las PIERNAS las lleva AGILE en lazo cerrado y aqui
                # se vuelve a ejecutar en vez de reproducirse. Aterriza en otro sitio desde el
                # principio, el torso queda distinto, las munecas agarran el radio en otro punto y
                # el volante acaba girando 113 grados en vez de 191.
                #
                # Se usa `scene.reset_to` y NO `env.reset_to`: el segundo llama a
                # `record_pre_reset` y a `_reset_idx`, o sea que exportaria un episodio y volveria
                # a sortear la disposicion de la valvula EN CADA PASO. El de la escena solo
                # escribe el estado.
                #
                # Queda una desviacion acotada a UN paso -- la imagen se renderiza dentro de
                # `step()`, antes de imponer -- en vez de acumularse a lo largo del episodio.
                if not args_cli.libre and esperado is not None:
                    env.scene.reset_to(esperado, ids_entorno, is_relative=True)

                apertura_max = max(
                    apertura_max, float(_a_torch(env.scene["valve"].data.joint_pos)[0, 0])
                )
            # Cerrar el episodio y exportarlo con el numero de demo de la fuente, para que
            # demo_N de la salida sea demo_N de la entrada y no haga falta traducir despues.
            env.recorder_manager.record_pre_reset([0], force_export_or_skip=False)
            # El exito se calcula sobre LA REPRODUCCION, no se copia del original. Reproducir las
            # acciones crudas hace que Pink IK recalcule los objetivos de junta desde el estado
            # actual, asi que la trayectoria se desvia un poco y el giro final cambia. Medido sobre
            # las 25 demos: desviacion media +1.5 grados, rango -24 a +50. Con las demos originales
            # llegando a 181-232 grados contra un umbral de 180, las que iban justas se caen --
            # demo_6 paso de 180.8 a 156.8. Copiar el flag del original marcaria como buena una
            # demo que ya no abre la valvula.
            exito_reproducido = apertura_max >= umbral_apertura
            env.recorder_manager.set_success_to_episodes(
                [0], torch.tensor([exito_reproducido], dtype=torch.bool, device=env.device)
            )
            env.recorder_manager.export_episodes([0], demo_ids=[int(nombres[idx].split("_")[1])])

            reproducidos += 1
            print(f"[rerender] {reproducidos:3}/{len(indices)}  {nombres[idx]}  {pasos} pasos  "
                  f"giro {apertura_max * 180.0 / 3.141592653589793:6.1f} grados  "
                  f"{'exito' if exito_reproducido else 'PERDIDA'}")

    if validar:
        print(f"[rerender] validacion de estados: {discrepancias} pasos con discrepancia")
    env.close()

    if os.path.exists(args_cli.output_file):
        print(f"[rerender] escrito {args_cli.output_file}")
    else:
        print(f"[rerender] AVISO: no se ha creado {args_cli.output_file}")


if __name__ == "__main__":
    main()
    simulation_app.close()
