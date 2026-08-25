#!/usr/bin/env python3
"""Comprobaciones sobre la memoria que NO necesitan compilar.

    python3 docs/memoria/comprobar.py

No sustituye a `pdflatex`: no valida la sintaxis de LaTeX. Coge la clase de errores que en un
documento partido en diez ficheros aparece sola y cuesta encontrar en el registro de compilacion:

  - entornos \\begin{...} sin su \\end{...}
  - llaves descompensadas fichero a fichero
  - \\includegraphics apuntando a una imagen que no existe
  - \\ref a una etiqueta que nadie define, y etiquetas definidas dos veces
  - \\cite a una clave que no esta en el .bib
  - marcadores [PENDIENTE] que se han quedado dentro

Sale con codigo 1 si hay algun problema, para poder encadenarlo.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# Entornos que la propia plantilla abre y cierra a lo largo de varias lineas.
RE_BEGIN = re.compile(r"\\begin\{([^}]+)\}")
RE_END = re.compile(r"\\end\{([^}]+)\}")
RE_GRAF = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
RE_REF = re.compile(r"\\(?:ref|autoref|pageref)\{([^}]+)\}")
RE_CITE = re.compile(r"\\cite\{([^}]+)\}")
RE_BIBKEY = re.compile(r"@\w+\{([^,]+),")
EXT_GRAF = (".pdf", ".png", ".jpg", ".jpeg")


def ficheros_tex():
    for base, _, nombres in os.walk(RAIZ):
        for n in sorted(nombres):
            if n.endswith(".tex"):
                yield os.path.join(base, n)


def sin_comentarios(texto):
    """Quita los comentarios de LaTeX respetando el \\% escapado."""
    fuera = []
    for linea in texto.split("\n"):
        i, esc = 0, False
        corte = len(linea)
        while i < len(linea):
            if linea[i] == "\\":
                esc = not esc
            elif linea[i] == "%" and not esc:
                corte = i
                break
            else:
                esc = False
            i += 1
        fuera.append(linea[:corte])
    return "\n".join(fuera)


def main():
    problemas = []
    etiquetas, refs, citas, graficos = {}, [], [], []

    for ruta in ficheros_tex():
        rel = os.path.relpath(ruta, RAIZ)
        texto = sin_comentarios(open(ruta, encoding="utf-8").read())

        # Entornos.
        pila = []
        for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", texto):
            tipo, nombre = m.group(1), m.group(2)
            if tipo == "begin":
                pila.append(nombre)
            elif not pila:
                problemas.append(f"{rel}: \\end{{{nombre}}} sin \\begin")
            elif pila[-1] != nombre:
                problemas.append(f"{rel}: \\end{{{nombre}}} cierra un \\begin{{{pila[-1]}}}")
                pila.pop()
            else:
                pila.pop()
        for n in pila:
            problemas.append(f"{rel}: \\begin{{{n}}} sin cerrar")

        # Llaves. Se ignoran las escapadas.
        limpio = re.sub(r"\\[{}]", "", texto)
        d = limpio.count("{") - limpio.count("}")
        if d:
            problemas.append(f"{rel}: llaves descompensadas ({d:+d})")

        # LaTeX convierte el salto de linea en espacio dentro de la llave: se
        # normaliza igual, o una etiqueta partida parece rota sin estarlo.
        norm = lambda s: " ".join(s.split())
        for m in RE_LABEL.finditer(texto):
            if norm(m.group(1)) in etiquetas:
                problemas.append(f"{rel}: etiqueta duplicada '{norm(m.group(1))}' "
                                 f"(ya en {etiquetas[norm(m.group(1))]})")
            etiquetas[norm(m.group(1))] = rel
        refs += [(norm(m.group(1)), rel) for m in RE_REF.finditer(texto)]
        for m in RE_CITE.finditer(texto):
            citas += [(c.strip(), rel) for c in m.group(1).split(",")]
        graficos += [(m.group(1), rel) for m in RE_GRAF.finditer(texto)]

        for n, linea in enumerate(texto.split("\n"), 1):
            if "[PENDIENTE" in linea:
                problemas.append(f"{rel}:{n}: marcador [PENDIENTE] sin rellenar")

    for destino, rel in graficos:
        ruta = os.path.join(RAIZ, destino)
        if os.path.isfile(ruta):
            continue
        if any(os.path.isfile(ruta + e) for e in EXT_GRAF):
            continue
        problemas.append(f"{rel}: falta la imagen '{destino}'")

    for etq, rel in refs:
        if etq not in etiquetas:
            problemas.append(f"{rel}: \\ref a una etiqueta inexistente '{etq}'")

    bib = os.path.join(RAIZ, "referencias.bib")
    claves = set()
    if os.path.isfile(bib):
        claves = {m.group(1).strip() for m in RE_BIBKEY.finditer(open(bib, encoding="utf-8").read())}
    for clave, rel in citas:
        if clave not in claves:
            problemas.append(f"{rel}: \\cite a una clave que no esta en referencias.bib '{clave}'")

    sin_citar = claves - {c for c, _ in citas}

    print(f"ficheros .tex     {len(list(ficheros_tex()))}")
    print(f"etiquetas         {len(etiquetas)}")
    print(f"referencias       {len(refs)}")
    print(f"figuras incluidas {len(graficos)}")
    print(f"citas             {len(citas)} a {len(set(c for c, _ in citas))} claves distintas")
    if sin_citar:
        print(f"\nAVISO: {len(sin_citar)} entradas del .bib no se citan y no apareceran en la "
              f"bibliografia:\n  " + ", ".join(sorted(sin_citar)))

    pend = [p for p in problemas if "PENDIENTE" in p]
    duros = [p for p in problemas if "PENDIENTE" not in p]

    if duros:
        print(f"\n{len(duros)} PROBLEMAS:")
        for p in duros:
            print("  " + p)
    if pend:
        print(f"\n{len(pend)} marcadores pendientes de rellenar:")
        for p in pend:
            print("  " + p)
    if not problemas:
        print("\nsin problemas")
    return 1 if duros else 0


if __name__ == "__main__":
    sys.exit(main())
