"""
Comprueba que requirements-ci.txt tenga las mismas versiones que
requirements.txt y requirements-dev.txt. Lo corre la CI.

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


def main():
    pedidos = {**fijados("requirements.txt"), **fijados("requirements-dev.txt"), **fijados("requirements-ci.in")}
    bloqueados = fijados("requirements-ci.txt")
    errores = []
    for nombre, version in sorted(pedidos.items()):
        if nombre in EXCLUIDOS:
            continue
        if nombre not in bloqueados:
            errores.append(f"{nombre}=={version} falta en requirements-ci.txt")
        elif bloqueados[nombre] != version:
            errores.append(f"{nombre}: pedido {version}, en requirements-ci.txt {bloqueados[nombre]}")
    if errores:
        print("requirements-ci.txt no coincide con los requirements:")
        print("\n".join(f"  - {e}" for e in errores))
        print(__doc__)
        return 1
    print(f"requirements-ci.txt al dia ({len(pedidos) - len(EXCLUIDOS)} dependencias directas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
