"""
Crea el grupo del rol Validador en las bases que ya habian corrido 0003.

En una base nueva 0003 ya lo crea (recorre TODOS_LOS_ROLES); get_or_create
hace que correr las dos no duplique nada.
"""

from django.db import migrations

from apps.usuarios.roles import ROL_VALIDADOR


def crear_grupo_validador(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ROL_VALIDADOR)


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0004_tabla_cache"),
    ]

    operations = [
        # Al revertir no se borra el grupo: puede tener usuarios asignados.
        migrations.RunPython(crear_grupo_validador, migrations.RunPython.noop),
    ]
