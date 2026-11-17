"""
Crea la tabla de la cache de base de datos (settings.CACHES), donde se guardan
los contadores de intentos de login, registro y recuperacion.

Equivale a `manage.py createcachetable`: si la tabla ya existe no hace nada, y
si la cache configurada no es de base de datos (las pruebas usan memoria)
tampoco. No se deshace al revertir: la tabla no guarda nada importante.
"""

from django.core.management import call_command
from django.db import migrations


def crear_tabla_cache(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0003_grupos_de_roles"),
    ]

    operations = [
        migrations.RunPython(crear_tabla_cache, migrations.RunPython.noop),
    ]
