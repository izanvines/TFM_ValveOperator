# Bibliografía: qué hay que verificar antes de entregar

Las entradas de `referencias.bib` se han escrito de memoria. Título, año e identificador de arXiv
son los campos de los que hay mayor certeza; **las listas de autores largas se han abreviado con
`and others` en lugar de completarlas a ojo**, porque una lista de autores inventada es peor que
una incompleta.

Antes de la entrega hay que abrir cada fuente y completar los campos. Una cita mal atribuida en un
TFM es un problema serio, y ninguna de estas se ha comprobado contra la fuente original.

## Prioridad alta — completar la lista de autores

| Clave | Qué falta | Dónde comprobarlo |
|---|---|---|
| `brohan2022rt1` | autores completos | arXiv:2212.06817 |
| `brohan2023rt2` | autores completos; la versión de congreso puede figurar con otro primer autor | arXiv:2307.15818 |
| `kim2024openvla` | autores completos; añadir la referencia de CoRL 2024 si se prefiere a la de arXiv | arXiv:2406.09246 |
| `black2024pi0` | autores completos | arXiv:2410.24164 |
| `nvidia2025gr00t` | autores completos | arXiv:2503.14734 |
| `oxe2023` | forma de citar una colaboración; comprobar si la revista/congreso final es ICRA | arXiv:2310.08864 |
| `mittal2023orbit` | autores completos, páginas y DOI | IEEE RA-L, vol. 8, n.º 6 |

## Prioridad media — confirmar el dato de publicación

| Clave | Qué confirmar |
|---|---|
| `zhao2023aloha` | páginas y editor de las actas de RSS 2023 |
| `chi2023diffusion` | ídem; existe además una versión ampliada en IJRR |
| `kerbl2023gaussian` | número de artículo y DOI de *ACM TOG* |
| `pomerleau1988alvinn` | páginas del volumen 1 de NIPS |
| `ross2011dagger` | ya lleva volumen y páginas; confirmar |

## Pendiente de decidir

- **GR00T N1.7.** El artículo publicado describe **N1**; la variante empleada en el trabajo es
  posterior y puede no tener publicación propia. Hay que decidir cómo citarla: nota en la entrada
  (como está ahora), referencia al repositorio, o ambas.
- **Isaac Lab Arena** y **Isaac Sim** no tienen entrada todavía. Probablemente deban citarse como
  software (`@misc` con URL), igual que LeRobot.
- **Unitree G1**: decidir si se cita la ficha técnica del fabricante.
- **Normativa** (ISO, ATEX, Reglamento de IA): la plantilla pide ISO 690. Comprobar si el tutor
  prefiere que las normas vayan en la bibliografía o citadas en el propio texto, que es lo
  habitual.
