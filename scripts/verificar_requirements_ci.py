"""
Comprueba que requirements-ci.txt tenga las mismas versiones que
requirements.txt y requirements-dev.txt, y que requirements-docker.txt y
requirements-compilacion.txt (los que instala el Dockerfile) coincidan con
requirements.txt y requirements-compilacion.in. Lo corre la CI.

Si falla, regeneralo (ver la cabecera de requirements-ci.in):

    uv pip compile requirements-ci.in --universal --python-version 3.12 \\
        --generate-hashes --no-emit-package mysqlclient -o requirements-ci.txt
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIJADO = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)")
EXCLUIDOS = {"mysqlclient"}   # no va en la CI (ver requirements-ci.in)


def normalizar(nombre):
    return re.sub(r"[-_.]+", "-", nombre).lower()


def fijados(ruta):
    versiones = {}
    for linea in (RAIZ / ruta).read_text(encoding="utf-8").splitlines():
        coincidencia = FIJADO.match(linea.strip())
        if coincidencia:
            versiones[normalizar(coincidencia.group(1))] = coincidencia.group(2)
    return versiones


def comparar(pedidos, archivo, excluidos=frozenset()):
    """Errores de las dependencias de `pedidos` que no estan igual en `archivo`."""
    bloqueados = fijados(archivo)
    errores = []
    for nombre, version in sorted(pedidos.items()):
        if nombre in excluidos:
            continue
        if nombre not in bloqueados:
            errores.append(f"{nombre}=={version} falta en {archivo}")
        elif bloqueados[nombre] != version:
            errores.append(f"{nombre}: pedido {version}, en {archivo} {bloqueados[nombre]}")
    return errores


def main():
    produccion = fijados("requirements.txt")
    pedidos_ci = {**produccion, **fijados("requirements-dev.txt"), **fijados("requirements-ci.in")}
    # Los de Docker (Dockerfile) se generan con su propio comando: ver la
    # cabecera de requirements-docker.in y requirements-compilacion.in.
    errores = (
        comparar(pedidos_ci, "requirements-ci.txt", EXCLUIDOS)
        + comparar(produccion, "requirements-docker.txt")
        + comparar(fijados("requirements-compilacion.in"), "requirements-compilacion.txt")
    )
    if errores:
        print("Los archivos bloqueados no coinciden con los requirements:")
        print("\n".join(f"  - {e}" for e in errores))
        print(__doc__)
        print("Docker: ver la cabecera de requirements-docker.in y requirements-compilacion.in.")
        return 1
    print(f"requirements-ci.txt al dia ({len(pedidos_ci) - len(EXCLUIDOS)} dependencias directas).")
    print(f"requirements-docker.txt al dia ({len(produccion)} dependencias directas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
