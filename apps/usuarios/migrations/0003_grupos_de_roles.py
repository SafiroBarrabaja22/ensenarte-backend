"""
Crea los grupos de roles en cualquier base de datos al correr `migrate`.

Ademas conserva el acceso de las cuentas que ya existian:
- Los usuarios `is_staff` (no superusuarios) antes pasaban todos los permisos;
  ahora `is_staff` ya no da roles, asi que se agregan al grupo Administrador.
- Las cuentas sin ningun rol (registradas antes de que existiera Estudiante)
  pasan a Estudiante para no perder acceso a cursos y evaluaciones.
"""

from django.db import migrations

from apps.usuarios.roles import ROL_ADMINISTRADOR, ROL_ESTUDIANTE, TODOS_LOS_ROLES


def crear_grupos_de_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    grupos = {
        nombre: Group.objects.get_or_create(name=nombre)[0]
        for nombre in TODOS_LOS_ROLES
    }

    for usuario in User.objects.filter(is_staff=True, is_superuser=False):
        usuario.groups.add(grupos[ROL_ADMINISTRADOR])

    sin_rol = User.objects.filter(is_superuser=False).exclude(
        groups__name__in=TODOS_LOS_ROLES
    )
    for usuario in sin_rol:
        usuario.groups.add(grupos[ROL_ESTUDIANTE])


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("usuarios", "0002_alter_perfilusuario_avatar"),
    ]

    operations = [
        # Al revertir no se borran grupos ni membresias: podrian tener usuarios
        # asignados a mano despues de esta migracion.
        migrations.RunPython(crear_grupos_de_roles, migrations.RunPython.noop),
    ]
