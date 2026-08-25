#!/usr/bin/env bash
# Compila la memoria. Tres pasadas mas bibtex: la primera resuelve el texto, bibtex construye la
# bibliografia y las dos ultimas fijan indices y referencias cruzadas.
set -e
cd "$(dirname "$0")"
DOC=Plantilla_Principal_TFM_MARSI

pdflatex -interaction=nonstopmode -halt-on-error $DOC.tex > /dev/null
bibtex $DOC > /dev/null || true
pdflatex -interaction=nonstopmode $DOC.tex > /dev/null
pdflatex -interaction=nonstopmode $DOC.tex > /dev/null

echo "paginas:                  $(pdfinfo $DOC.pdf | awk '/Pages/{print $2}')"
echo "referencias sin resolver: $(grep -cE 'Reference .* undefined' $DOC.log || true)"
echo "citas sin resolver:       $(grep -cE 'Citation .* undefined' $DOC.log || true)"
echo "cajas desbordadas:        $(grep -c 'Overfull \\hbox' $DOC.log || true)"
echo "flotantes que no caben:   $(grep -c 'Float too large' $DOC.log || true)"
# El aviso de headheight lo trae la plantilla: no fija \headheight y fancyhdr quiere 14.5pt.
grep -E '^LaTeX Warning' $DOC.log | sort -u || true
