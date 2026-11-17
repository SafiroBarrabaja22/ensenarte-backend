#!/usr/bin/env python
"""Utilidad de linea de comandos de Django."""
import os
import sys


def main():
    # `manage.py test` usa SQLite en memoria: nunca la base del .env.
    por_defecto = "config.settings_pruebas" if sys.argv[1:2] == ["test"] else "config.settings"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", por_defecto)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Verifica que este instalado y que el "
            "entorno virtual este activo."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
