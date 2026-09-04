# El Gaussian Splat se deforma al moverlo en Isaac Sim

**Resumen en una línea:** la matriz de transformación que viene dentro del `.usdz` está
**transpuesta**, y USD la interpreta como una matriz **proyectiva** en vez de como una rotación
+ traslación. Se arregla sobreescribiéndola con su transpuesta.

Verificado el 2026-07-28 con Isaac Sim 6.0 y un splat NuRec/3DGUT exportado desde COLMAP.

---

## El síntoma

Abres el `.usdz` con `File → Open` y **se ve perfecto**. Pero en cuanto lo trasladas o lo rotas
—para colocarlo sobre el suelo de tu escena— **se deforma y se estira**, cada vez peor cuanto
más lo mueves. Parece un problema del visor, o del `.nurec`, o de que "los splats no se pueden
transformar". No es nada de eso.

## La causa

Dentro del `.usdz`, el prim `Volume` trae una `xformOp:transform` así:

```
row0 = ( 0.99952, -0.03105,  0.00219, -0.16733)
row1 = ( 0.03105,  0.98961, -0.14036, -0.11647)
row2 = ( 0.00219,  0.14036,  0.99010,  0.50208)
row3 = ( 0,        0,        0,        1      )
```

USD usa convención **row-vector** (el punto se multiplica por la izquierda: `p * M`). En esa
convención:

- la **traslación** va en la **última fila** → aquí está a cero,
- la **última columna** tiene que ser `(0,0,0,1)` → aquí tiene `(-0.167, -0.116, 0.502)`.

Está justo al revés. La matriz se escribió en **column-major** (la convención de
COLMAP/OpenGL/PyTorch) y se metió en el USD sin transponer. Como esos tres números caen en la
columna proyectiva, USD hace la **división homogénea** y el resultado es una deformación
perspectiva que crece con la distancia al origen:

| punto original | dónde acaba | factor |
|---|---|---|
| (1, 0, 0) | 1.20 | ×1.2 |
| (5, 0, 0) | 30.6 | ×6.1 |
| x ≈ 5.98 | infinito | `w` cruza cero y la geometría se invierte |

Una sala de 12 m entra de lleno en esa zona. Por eso al moverla se descompone.

## Cómo comprobar si te pasa a ti

```python
from pxr import Usd, UsdGeom

st = Usd.Stage.Open("tu_splat.usdz")
prim = st.GetPrimAtPath("/World/gauss/gauss")      # el prim de tipo Volume
M = UsdGeom.Xformable(prim).GetOrderedXformOps()[0].Get()

print("ultima columna (debe ser 0,0,0):", [round(M[i][3], 6) for i in range(3)])
print("ultima fila (traslacion)      :", [round(M[3][j], 6) for j in range(3)])
```

- Última columna a `(0,0,0)` → **bien**, matriz rígida.
- Última columna con números y última fila a cero → **está transpuesta**.

## El arreglo

**No hay que tocar el `.usdz`.** Se crea un `.usda` que lo referencia y sobreescribe esa matriz
con la transpuesta, usando un `over`:

```usda
#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{
    def Xform "Office" (
        prepend references = @./tu_splat.usdz@
    )
    {
        # Tus transformaciones: mueve y gira ESTO, no lo de dentro.
        double3 xformOp:translate = (0, 0, 0)
        float3 xformOp:rotateXYZ = (0, 0, 0)
        double3 xformOp:scale = (1, 1, 1)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]

        # El parche: la matriz de dentro, TRANSPUESTA.
        over "gauss"
        {
            over "gauss"
            {
                matrix4d xformOp:transform = ( ( 0.99952,  0.03105,  0.00219, 0),
                                               (-0.03105,  0.98961,  0.14036, 0),
                                               ( 0.00219, -0.14036,  0.99010, 0),
                                               (-0.16733, -0.11647,  0.50208, 1) )
                uniform token[] xformOpOrder = ["xformOp:transform"]
            }
        }
    }
}
```

Ojo: **los números de arriba son los de mi splat**. Saca los tuyos con el script de
comprobación y transpónlos (intercambia filas por columnas).

Para verificar que el arreglo funciona sin necesidad de mirarlo: transforma dos puntos separados
1 m y comprueba que **siguen a 1 m** después de aplicar una rotación y una traslación
cualesquiera. Si la distancia cambia, la matriz sigue sin ser rígida.

## Un par de cosas más que te van a morder

- **El `extent` del USD es basura.** En mi caso declaraba ~8900 × 13466 × 10686 unidades con
  `metersPerUnit = 1.0`, o sea kilómetros. Las gaussianas de verdad viven en el `.nurec`, no en
  el USD. **La escala correcta es 1.0**; no la deduzcas del extent.
- **Empieza siempre desde la identidad.** Cualquier rotación o traslación que estimes "a ojo"
  encima de la matriz proyectiva estará mal, porque estás midiendo sobre algo ya deformado.
- **Kit cachea las capas USD.** Si editas el `.usda` y vuelves a hacer `File → Open` sobre la
  misma ruta, puedes seguir viendo la versión vieja. Guarda con **otro nombre** para asegurarte.
- **El splat no tiene colisión** — es puramente visual. El suelo físico lo pones tú aparte.
  Y conviene **mover el splat al mundo**, no la física al splat: si tu robot y tu suelo asumen
  Z=0, moverlos rompe más cosas de las que arregla.
- **Un dato independiente para validar la altura**: si tu export trae las cámaras de captura
  (`Cameras/camera_0` con `timeSamples`), su trayectoria en coordenadas de mundo debería quedar
  a ~1.2–1.7 m del suelo si se grabó a mano. Si te sale a 4 m o bajo tierra, la traslación
  vertical está mal aunque en el viewport "parezca" bien.

---

## Y una vez que se mueve bien: colócalo con el dato, no a ojo

Cuando ya no se deforma viene el segundo problema, y este es más traicionero porque **a ojo no
se nota**. Yo alineé la sala a mano en el GUI, quedó convincente, y midiendo resultó que el
suelo estaba **14° en cuesta** y la oficina flotando 3,9 m. En un viewport sin referencias no
lo ves; el robot es el que te lo chiva, porque aparece enano o hundido.

La trayectoria de captura te da las tres cosas gratis:

- **Cuál es la vertical** → el eje de **menor varianza** del recorrido. Quien grabó anduvo
  mucho y subió poco. En mi caso: desviación 0,21 en un eje frente a 2,4 y 3,6 en los otros
  dos, así que la vertical era `−Y` local (¡aunque el USD declarase `upAxis = "Z"`!). El signo
  te lo fija el "arriba" medio de las cámaras (la fila 1 de su matriz, que es su +Y).
- **Cuál es la escala** → el splat viene en unidades de COLMAP, que **no son metros**. Proyecta
  el recorrido sobre el plano del suelo, hazle un PCA en 2D (así la caja sale alineada con las
  paredes, no girada) y compara con lo que mide tu sala de verdad. Como la persona anduvo
  *dentro*, eso la acota. Segunda comprobación gratis: a la escala correcta, la cámara en mano
  debe subir y bajar del orden de **0,2–0,4 m** mientras anda.
- **Dónde está el suelo** → traslada de forma que la altura media de las cámaras quede a ~1,5 m.

Truco que ahorra rehacer el trabajo: si ya habías encuadrado la sala a mano y solo quieres
quitarle el desnivel, **no vuelvas a alinear**. Multiplica tu matriz **por la derecha** por la
rotación mínima que lleva la vertical medida a `(0,0,1)`:

```
R_nueva = R_tuya @ R_corrección
```

Tu encuadre (qué pared queda enfrente) se conserva intacto y solo desaparece la cuesta.

- **Y revisa el recorte**: `omni:nurec:crop:minBounds` / `maxBounds` suelen venir **idénticos
  al `extent` inflado**, o sea desactivados, y entonces se cuela toda la reconstrucción de fuera
  de la sala (lo que se ve por las ventanas, los flotantes). Se escriben en el mismo `over`.
  Dos avisos: van en el **espacio local del `Volume`** (no en mundo, hay que pasar la caja por
  la inversa de la cadena), y el margen **no puede ser el mismo en todas las direcciones** —
  el recorrido abarca metros en horizontal pero apenas medio metro en vertical, así que un
  margen isótropo generoso en horizontal te recorta el suelo y el techo.
