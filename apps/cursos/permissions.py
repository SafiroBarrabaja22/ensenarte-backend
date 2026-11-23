"""
Permisos de DRF por rol.

Hay una clase por rol (EsEstudiante, EsProfesor, EsInterprete,
EsCreadorDeCursos, EsAdministrador) y, al final, las combinaciones que usan las
vistas. Los nombres de los grupos vienen de apps/usuarios/roles.py.

Alcance de cada rol (cada uno ve SOLO su seccion; todos conservan su perfil):
- Estudiante: el UNICO que hace cursos (diccionario, evaluaciones, progreso).
- Profesor: crea cursos y administra el contenido SOLO de los cursos que el
  creo (permiso a nivel de objeto), con vista previa en el panel.
- Interprete: biblioteca visual y gifs de cualquier curso.
- CreadorDeCursos: contenido de TODOS los cursos.
- Validador: aprueba o rechaza las senas (gifs de la biblioteca). Es el UNICO
  que puede hacerlo.
- Administrador (grupo o superusuario): panel de cursos y biblioteca; no hace
  cursos ni valida senas.
Un rol de trabajo anula el grupo Estudiante (roles.ROLES_DE_TRABAJO).
"""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_ESTUDIANTE,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    ROL_VALIDADOR,
    ROLES_GESTION_GLOBAL,
    tiene_rol,
)

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta

MENSAJE_CURSO_AJENO = "Solo puedes modificar los cursos que tu creaste."


class PermisoPorRol(BasePermission):
    """Base: autoriza si el usuario autenticado pertenece al rol `rol`."""

    rol = None

    def has_permission(self, request, view):
        return tiene_rol(request.user, self.rol)


class EsEstudiante(PermisoPorRol):
    rol = ROL_ESTUDIANTE
    message = "Solo los estudiantes pueden hacer los cursos."


class EsProfesor(PermisoPorRol):
    rol = ROL_PROFESOR
    message = "Esta accion requiere el rol Profesor."


class EsInterprete(PermisoPorRol):
    rol = ROL_INTERPRETE
    message = "Esta accion requiere el rol Interprete."


class EsCreadorDeCursos(PermisoPorRol):
    rol = ROL_CREADOR
    message = "Esta accion requiere el rol Creador de cursos."


class EsAdministrador(PermisoPorRol):
    rol = ROL_ADMINISTRADOR
    message = "Esta accion requiere el rol Administrador."


class EsValidador(PermisoPorRol):
    rol = ROL_VALIDADOR
    message = "Solo el Validador puede aprobar o rechazar senas."


class SoloLectura(BasePermission):
    """Autoriza solo metodos de lectura (GET, HEAD, OPTIONS)."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


# ----------------------------------------------------------------------
# Permiso a nivel de objeto: dueno del curso
# ----------------------------------------------------------------------

def curso_de(objeto):
    """Devuelve el Curso al que pertenece un Curso, Pregunta, Opcion o Palabra."""
    if isinstance(objeto, Curso):
        return objeto
    if isinstance(objeto, (Pregunta, PalabraDiccionario)):
        return objeto.curso
    if isinstance(objeto, OpcionPregunta):
        return objeto.pregunta.curso
    return None


def puede_editar_curso(usuario, curso):
    """Administrador y CreadorDeCursos: cualquier curso. Profesor: solo los suyos."""
    if tiene_rol(usuario, *ROLES_GESTION_GLOBAL):
        return True
    return (
        curso is not None
        and tiene_rol(usuario, ROL_PROFESOR)
        and curso.creado_por_id == usuario.id
    )


def exigir_curso_editable(usuario, curso):
    """Lanza 403 si el usuario no puede modificar el curso."""
    if not puede_editar_curso(usuario, curso):
        raise PermissionDenied(MENSAJE_CURSO_AJENO)


class EsDuenoDelCurso(BasePermission):
    """
    Nivel de objeto. Se combina con PUEDE_GESTIONAR_CONTENIDO (que decide si
    entra a la vista); aqui se decide si puede tocar ESTE curso o su contenido.
    """

    message = MENSAJE_CURSO_AJENO

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return puede_editar_curso(request.user, curso_de(obj))


# ----------------------------------------------------------------------
# Combinaciones que usan las vistas
# ----------------------------------------------------------------------

# Solo el Estudiante hace cursos (diccionario, evaluaciones, progreso, constancia).
# Ningun rol de trabajo entra, aunque conserve el grupo Estudiante: roles_de() lo
# descarta (apps/usuarios/roles.py, ROLES_DE_TRABAJO). El Profesor revisa sus
# cursos con la vista previa del panel, no como alumno.
PUEDE_APRENDER = EsEstudiante

# Ver el estado de las senas y su historial de revisiones: quien las sube,
# quien las revisa y el Administrador.
PUEDE_VER_REVISIONES = EsValidador | EsInterprete | EsAdministrador

# Panel de cursos, preguntas, opciones y diccionario.
PUEDE_GESTIONAR_CONTENIDO = EsProfesor | EsCreadorDeCursos | EsAdministrador

# Escritura en la biblioteca visual (recursos, avatares e insignias).
PUEDE_GESTIONAR_BIBLIOTECA = EsInterprete | EsAdministrador

# Subir gifs de senas y archivos sueltos de contenido.
PUEDE_SUBIR_GIF = EsInterprete | EsProfesor | EsCreadorDeCursos | EsAdministrador
