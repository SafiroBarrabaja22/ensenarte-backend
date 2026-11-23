"""
Roles del sistema.

Este es el UNICO lugar donde se escriben los nombres de los grupos de Django que
representan roles. Cualquier otro modulo (permisos, serializers, migraciones,
comandos, pruebas) debe importar estas constantes: un nombre mal escrito en un
string suelto rompe el permiso sin dar ningun error visible.

Los grupos se crean solos con la migracion usuarios/0003_grupos_de_roles.
"""

from django.contrib.auth.models import Group

ROL_ESTUDIANTE = "Estudiante"
ROL_PROFESOR = "Profesor"
ROL_INTERPRETE = "Interprete"
ROL_CREADOR = "CreadorDeCursos"
ROL_ADMINISTRADOR = "Administrador"
# Revisa las senas que sube el Interprete y las aprueba o rechaza. Es el UNICO
# que puede hacerlo: ni el Administrador ni un superusuario lo reemplazan.
ROL_VALIDADOR = "Validador"

# Orden en el que se devuelven en el perfil (de mayor a menor alcance).
TODOS_LOS_ROLES = (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_PROFESOR,
    ROL_VALIDADOR,
    ROL_INTERPRETE,
    ROL_ESTUDIANTE,
)

# Roles que administran el contenido de TODOS los cursos (no solo los propios).
ROLES_GESTION_GLOBAL = (ROL_ADMINISTRADOR, ROL_CREADOR)

_CACHE = "_roles_ensenarte"


def roles_de(usuario):
    """
    Lista de roles del usuario, en el orden de TODOS_LOS_ROLES.

    Un superusuario siempre tiene el rol Administrador aunque no este en el
    grupo. `is_staff` por si solo NO da ningun rol: solo habilita el admin de
    Django. El resultado se guarda en el objeto para no consultar la base de
    datos en cada permiso de la misma peticion.
    """
    if usuario is None or not usuario.is_authenticated:
        return []
    roles = getattr(usuario, _CACHE, None)
    if roles is None:
        nombres = set(
            usuario.groups.filter(name__in=TODOS_LOS_ROLES).values_list(
                "name", flat=True
            )
        )
        if usuario.is_superuser:
            nombres.add(ROL_ADMINISTRADOR)
        roles = [rol for rol in TODOS_LOS_ROLES if rol in nombres]
        setattr(usuario, _CACHE, roles)
    return roles


def tiene_rol(usuario, *roles):
    """True si el usuario tiene al menos uno de los roles indicados."""
    propios = roles_de(usuario)
    return any(rol in propios for rol in roles)


def asignar_rol(usuario, rol):
    """Agrega el usuario al grupo del rol (el grupo lo crea la migracion)."""
    if rol not in TODOS_LOS_ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    if hasattr(usuario, _CACHE):
        delattr(usuario, _CACHE)
