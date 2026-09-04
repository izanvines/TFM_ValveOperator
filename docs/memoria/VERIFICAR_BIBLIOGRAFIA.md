# Bibliografía: registro de verificación

Todas las entradas de `referencias.bib` se contrastaron el **2026-09-04** (las tres del anexo D, la misma noche) contra una fuente
primaria. Antes de esa fecha estaban escritas de memoria; ya no. Este fichero deja constancia de
qué se comprobó, contra qué, y de las tres decisiones de forma que conviene conocer.

## Qué se comprobó y contra qué

| Clave | Fuente primaria consultada | Resultado |
|---|---|---|
| `pomerleau1988alvinn` | Página oficial de NeurIPS (proceedings.neurips.cc, 1988) | Título y autor confirmados; añadidos editor (Touretzky), editorial (Morgan Kaufmann) y páginas 305–313 |
| `ross2011dagger` | Página de PMLR v15 (ross11a), con su BibTeX | Confirmado; añadidos serie, editorial y ciudad |
| `zhao2023aloha` | API de arXiv (2304.13705) + dblp | Autores confirmados; añadido el DOI de RSS 2023: 10.15607/RSS.2023.XIX.016 |
| `chi2023diffusion` | API de arXiv (2303.04137) + dblp | La versión de RSS 2023 tiene **7 autores** en otro orden que la de arXiv v5 (8, con Tedrake); se cita la de RSS con DOI 10.15607/RSS.2023.XIX.026 y se anota la versión IJRR 44(10–11):1684–1704, 2025 |
| `brohan2022rt1` | API de arXiv (2212.06817) + dblp | **Lista completa de 52 autores**; venue RSS 2023, DOI 10.15607/RSS.2023.XIX.025 |
| `brohan2023rt2` | Página de PMLR v229 (zitkovich23a), con su BibTeX | **Ojo: la versión de CoRL lleva a Zitkovich como primera autora**, no a Brohan; 54 autores, páginas 2165–2183. La clave se conserva por no romper las citas |
| `kim2024openvla` | Página de PMLR v270 (kim25c) | 17 autores según el registro de PMLR (arXiv lista 18); páginas 2679–2713, publicado en 2025 |
| `black2024pi0` | Página de arXiv (2410.24164) | 24 autores completos; el campo *Comments* dice «Published in RSS 2025». **No se ha localizado DOI** de RSS 2025 |
| `nvidia2025gr00t` | API de arXiv (2503.14734) | 59 autores en orden alfabético con NVIDIA como primer autor; se cita «NVIDIA et al.», que es la forma que el artículo indica |
| `oxe2023` | API de arXiv (2310.08864) + Crossref (10.1109/ICRA57147.2024.10611477) | 389 autores; se cita como colaboración. ICRA 2024, páginas 6892–6903 |
| `mittal2023orbit` | API de arXiv (2301.04195) + dblp | 15 autores completos; RA-L 8(6):3740–3747, DOI 10.1109/LRA.2023.3270034 |
| `cadene2024lerobot` | README de github.com/huggingface/lerobot, bloque *Citation* | Lista de 18 autores tal como la pide el repositorio. Existe además un artículo de ICLR 2026 (arXiv:2602.22818) que no se usa porque lo empleado es la biblioteca |
| `cheng2024television` | API de arXiv (2407.01512) + PMLR v270 (cheng25b) | 5 autores; CoRL 2024, páginas 2729–2749 |
| `kerbl2023gaussian` | API de arXiv (2308.04079) + Crossref (10.1145/3592433) | TOG 42(4), julio de 2023, 14 páginas. Crossref no da el número de artículo; el 139 es el que consta en ACM |
| `krotkov2017drc` | Crossref (10.1002/rob.21683) + Semantic Scholar | 8 autores, JFR 34(2):229–240 |
| `isaacsim` | developer.nvidia.com/isaac/sim | Resuelve; nombre de producto confirmado |
| `isaaclab_arena` | github.com/isaac-sim/IsaacLab-Arena | Resuelve; se adopta el bloque de cita que da el propio README (título y autor corporativo) |
| `unitree_g1` | unitree.com/g1 | Resuelve. **Confirma las cifras del capítulo 1: 1320 mm y ~35 kg** |
| `nvidia_cloudxr` | developer.nvidia.com/cloudxr-sdk | Resuelve; producto «NVIDIA CloudXR 6.0» |
| `pico4ultra` | picoxr.com/global/products/pico4-ultra | Resuelve, sin redirección |
| `williams2024fvdb` | API de arXiv (2407.01781) + Crossref (10.1145/3658226) | 12 autores; ACM TOG 43(4), julio de 2024 |
| `fvdb_reality_capture` | github.com/openvdb/fvdb-reality-capture (localizado por búsqueda; la ruta antigua bajo `voxel-foundation` devuelve 404) | Cita a software; mantenido por NVIDIA dentro de la organización OpenVDB |
| `schonberger2016sfm` | Crossref (10.1109/CVPR.2016.445) | CVPR 2016, páginas 4104–4113 |

Eliminada `fernandez2019grupo`: venía de la plantilla y no se citaba.

## Tres decisiones de forma

1. **Autores completos**, sin «et al.», en todas las entradas salvo dos: Open X-Embodiment (389
   autores; el artículo pide citarse como colaboración) y GR00T N1 (59 autores alfabéticos; el
   artículo pide «NVIDIA» como primer autor). RT-1 y RT-2 llevan sus 52 y 54 nombres: ocupan
   varias líneas en la bibliografía. Si se prefiere acortarlas, la norma ISO 690 admite el primer
   autor seguido de «et al.» cuando la lista es larga.
2. **Se cita la versión de congreso** cuando existe (RSS, CoRL), con el identificador de arXiv en
   una nota, porque es la revisada por pares; para Diffusion Policy se anota además la versión de
   revista.
3. **Software** (Isaac Sim, Arena, LeRobot, CloudXR) y **hardware** (G1, PICO) como `@misc` con
   URL y, cuando procede, la versión empleada.

## Lo que queda abierto

- DOI de $\pi_0$ en RSS 2025: no localizado; la entrada lleva el arXiv.
- El texto menciona el **reto ARGOS** de Total sin cita, y la tabla de normativa incluye
  **ISO/IEC TR 5469** sin entrada bibliográfica. Las normas se citan en el texto, como es habitual.
