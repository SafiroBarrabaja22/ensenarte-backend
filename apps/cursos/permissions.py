from rest_framework.permissions import BasePermission

GRUPO_CREADOR = "CreadorDeCursos"


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
