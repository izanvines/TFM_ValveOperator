# La memoria del TFM

Plantilla oficial de la titulación, rellenada. El original tal como se entregó está en
`TFM_MURIA_2026_Izan.zip` y en el primer commit de este directorio, para poder contrastar qué es
de la plantilla y qué es nuestro.

## Cómo compilar

```bash
./docs/memoria/compilar.sh
```

Hace las tres pasadas de `pdflatex` más `bibtex` —la primera resuelve el texto, `bibtex` construye
la bibliografía y las dos últimas fijan índices y referencias cruzadas— e imprime el recuento de
páginas y los avisos que importan: referencias y citas sin resolver, cajas desbordadas y flotantes
que no caben en su página.

Requiere TeX Live:

```bash
sudo apt-get install -y texlive-latex-recommended texlive-latex-extra \
    texlive-lang-spanish texlive-fonts-recommended texlive-bibtex-extra
```

Queda un aviso que **viene de la plantilla**: `fancyhdr` pide `\headheight` de 14,5\,pt y la
plantilla lo deja en los 12\,pt por defecto. No rompe nada; corregirlo son dos líneas en el
preámbulo, que es justo lo que se ha decidido no tocar.

## Cómo está organizado

El fichero principal conserva **el preámbulo de la plantilla sin tocar** y solo llama a los
capítulos con `\input`, igual que la plantilla ya hacía con la portada y la hoja de firmas.

```
Plantilla_Principal_TFM_MARSI.tex   preámbulo + \input de cada capítulo
Plantillas/                         portada y hoja de firmas
capitulos/                          un fichero por capítulo y por anexo
figuras/
├── logos/          de la plantilla
├── resultados/     las nueve figuras de docs/figuras/
├── sistema/        diagramas: cadena, arquitectura, Gantt, riesgos
└── simulacion/     capturas del simulador
referencias.bib                     bibliografía
```

## Antes de tocar nada

- **No se añaden paquetes al preámbulo.** Los diagramas entran como PDF vectorial, generados con
  `train/scripts/figuras_memoria.py`, y no con TikZ.
- Los estilos de figura, tabla y código son los de la plantilla. Los patrones exactos, extraídos
  del capítulo de ejemplos antes de borrarlo, están en `PATRONES_PLANTILLA.md`.
- **Ninguna cifra de la memoria se inventa.** Todas salen de `docs/resultados_100demos.md`,
  `docs/ensayo_2026-08.md` y el `CLAUDE.md` del repositorio.

## Comprobaciones

```bash
python3 docs/memoria/comprobar.py
```

Coge lo que `pdflatex` tarda en decirte o directamente no dice: entornos sin cerrar, llaves
descompensadas, imágenes que faltan, `\ref` a etiquetas inexistentes, `\cite` a claves que no
están en el `.bib`, y los marcadores `[PENDIENTE]` que aún quedan por rellenar.

`VERIFICAR_BIBLIOGRAFIA.md` lista lo que hay que contrastar contra las fuentes originales antes de
entregar. **Las entradas del `.bib` están escritas de memoria y no se han comprobado.**
