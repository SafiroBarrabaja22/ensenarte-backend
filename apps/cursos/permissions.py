from rest_framework.permissions import BasePermission

GRUPO_CREADOR = "CreadorDeCursos"
GRUPO_PROFESOR = "Profesor"
GRUPO_INTERPRETE = "Interprete"


class EsCreadorDeCursos(BasePermission):
    """
    Equivalente en DRF del decorador `permitir_creador` del monolito.

    Autoriza a superusuarios, staff y miembros del grupo CreadorDeCursos.
    """

    message = "Necesitas permisos de creador de cursos para esta operacion."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=GRUPO_CREADOR).exists()
        )


class EsProfesor(BasePermission):
    """
    Rol de contenido: crea diccionarios (palabras + significado) y evaluaciones,
    y puede consultar las estrellas de los estudiantes. No administra cursos.
    """

    message = "Necesitas permisos de profesor para esta operacion."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=GRUPO_PROFESOR).exists()
        )


class EsInterprete(BasePermission):
    """
    Rol restringido a subir los gifs de las senas (diccionario y evaluaciones).
    No puede crear ni editar el resto del contenido.
    """

    message = "Necesitas permisos de interprete para esta operacion."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=GRUPO_INTERPRETE).exists()
        )
