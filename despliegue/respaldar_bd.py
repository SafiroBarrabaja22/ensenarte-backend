"""
Respalda la base de datos MySQL/MariaDB configurada en el .env antes de migrar.

Uso (lo llama despliegue/desplegar.sh):
    .venv/bin/python despliegue/respaldar_bd.py

Los respaldos van SIEMPRE a la carpeta "respaldos" junto al proyecto
(/srv/ensenarte/respaldos si el proyecto esta en /srv/ensenarte/ensenarte-backend).
La ruta no se recibe por argumento: asi nadie puede hacer que escriba en otro lugar.

- Lee la conexion de los settings de Django: no hay que repetir credenciales.
- La contrasena va en un archivo temporal con permisos 600 que se borra al
  terminar, nunca en la linea de comandos (ahi la veria cualquiera con `ps`).
- Guarda <base>-<fecha>.sql.gz con permisos 600 y conserva los 10 mas recientes.
- Incluye procedimientos y triggers (--routines --triggers).
- Si la base no es MySQL no hace nada.
"""

import gzip
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_RESPALDOS = RAIZ.parent / "respaldos"
RESPALDOS_A_CONSERVAR = 10

sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402


def valor_cnf(texto):
    """Valor entre comillas para un archivo de opciones de MySQL."""
    return '"' + str(texto).replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    if len(sys.argv) != 1:
        sys.exit("Uso: respaldar_bd.py (sin argumentos; guarda en ../respaldos)")
    bd = settings.DATABASES["default"]
    if "mysql" not in bd["ENGINE"]:
        print("La base no es MySQL; no se hace respaldo.")
        return
    programa = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    if not programa:
        sys.exit("No se encontro mariadb-dump ni mysqldump.")

    carpeta = CARPETA_RESPALDOS
    carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
    destino = carpeta / f"{bd['NAME']}-{time.strftime('%Y%m%d-%H%M%S')}.sql.gz"

    lineas = ["[client]", f"user={valor_cnf(bd['USER'])}", f"password={valor_cnf(bd['PASSWORD'])}"]
    if bd.get("HOST"):
        lineas.append(f"host={valor_cnf(bd['HOST'])}")
    if bd.get("PORT"):
        lineas.append(f"port={int(bd['PORT'])}")
    socket = (bd.get("OPTIONS") or {}).get("unix_socket")
    if socket:
        lineas.append(f"socket={valor_cnf(socket)}")

    # NamedTemporaryFile crea el archivo con permisos 600.
    with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as cnf:
        cnf.write("\n".join(lineas) + "\n")
    try:
        comando = [
            programa, f"--defaults-extra-file={cnf.name}",
            "--single-transaction", "--routines", "--triggers", "--no-tablespaces",
            bd["NAME"],
        ]
        with gzip.open(destino, "wb") as salida:
            os.chmod(destino, 0o600)
            proceso = subprocess.Popen(comando, stdout=subprocess.PIPE)
            shutil.copyfileobj(proceso.stdout, salida)
            if proceso.wait() != 0:
                raise SystemExit(f"{Path(programa).name} termino con codigo {proceso.returncode}.")
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    finally:
        os.unlink(cnf.name)

    print(f"Respaldo: {destino} ({destino.stat().st_size // 1024} KB)")
    viejos = sorted(carpeta.glob(f"{bd['NAME']}-*.sql.gz"))[:-RESPALDOS_A_CONSERVAR]
    for archivo in viejos:
        archivo.unlink()


if __name__ == "__main__":
    main()
