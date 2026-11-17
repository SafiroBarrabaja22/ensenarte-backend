"""
Piezas compartidas de la documentacion OpenAPI (drf-spectacular).

Las vistas usan estas etiquetas, parametros y respuestas de error para que toda
la API se documente igual. Los mensajes de error son los que devuelve la API
(DRF traducido al espanol por LANGUAGE_CODE = "es-co", o los nuestros).
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import serializers

# Etiquetas: definidas en config/etiquetas_api.py (las importa tambien settings).
from config.etiquetas_api import (  # noqa: E402,F401
    ETIQUETA_AUTENTICACION,
    ETIQUETA_CURSOS,
    ETIQUETA_EVALUACION,
    ETIQUETA_PANEL,
    ETIQUETA_REPORTES,
)

# ---------------------------------------------------------------- Parametros

PARAM_SLUG = OpenApiParameter(
    "slug", OpenApiTypes.STR, OpenApiParameter.PATH,
    description="Identificador del curso en la URL (campo `nombre`), p. ej. `abecedario`.",
    examples=[OpenApiExample("Abecedario", value="abecedario")],
)


def param_id(entidad):
    return OpenApiParameter(
        "id", OpenApiTypes.INT, OpenApiParameter.PATH, description=f"ID de {entidad}."
    )


def filtro(nombre, descripcion, tipo=OpenApiTypes.INT):
    return OpenApiParameter(nombre, tipo, OpenApiParameter.QUERY, required=False, description=descripcion)


# ----------------------------------------------------------- Esquemas de error


class ErrorDetalleSerializer(serializers.Serializer):
    detail = serializers.CharField(help_text="Mensaje legible del error.")


# {campo: ["mensaje", ...]} — formato de errores de validacion de DRF
ESQUEMA_ERRORES_VALIDACION = {
    "type": "object",
    "description": "Cada campo con error trae su lista de mensajes. "
    "`non_field_errors` agrupa los errores que no son de un campo.",
    "additionalProperties": {"type": "array", "items": {"type": "string"}},
}

MENSAJE_401 = "Las credenciales de autenticación no se proveyeron."
MENSAJE_403 = "Usted no tiene permiso para realizar esta acción."
MENSAJE_403_CURSO_AJENO = "Solo puedes modificar los cursos que tu creaste."
MENSAJE_404 = "No encontrado."


def _ejemplo(nombre, valor, codigo):
    return OpenApiExample(nombre, value=valor, response_only=True, status_codes=[str(codigo)])


# ----------------------------------------------------- Constructores de respuesta


def ok(esquema, ejemplo, codigo=200, descripcion="Operación exitosa."):
    """Respuesta exitosa con su ejemplo."""
    ejemplos = [_ejemplo("Éxito", ejemplo, codigo)] if ejemplo is not None else []
    return {codigo: OpenApiResponse(esquema, description=descripcion, examples=ejemplos)}


def sin_contenido(descripcion="Operación exitosa, sin cuerpo de respuesta."):
    return {204: OpenApiResponse(None, description=descripcion)}


def error_400(ejemplo, descripcion="Datos inválidos. La respuesta indica qué campo falló.", detalle=False):
    """400 de validacion. Con detalle=True el cuerpo es {"detail": "..."}."""
    esquema = ErrorDetalleSerializer if detalle else ESQUEMA_ERRORES_VALIDACION
    return {400: OpenApiResponse(esquema, description=descripcion, examples=[_ejemplo("Datos inválidos", ejemplo, 400)])}


def error_401(
    descripcion="Falta el token JWT, es inválido o venció. Renueva con /api/auth/refresh/.",
    ejemplo=None,
):
    return {401: OpenApiResponse(
        ErrorDetalleSerializer, description=descripcion,
        examples=[_ejemplo("Sin autenticación", ejemplo or {"detail": MENSAJE_401}, 401)],
    )}


def error_403(descripcion="El rol del usuario no permite esta acción.", detalle=MENSAJE_403, extra=None):
    ejemplos = [_ejemplo("Permiso denegado", {"detail": detalle}, 403)]
    if extra:
        ejemplos.append(_ejemplo("Curso de otro profesor", {"detail": extra}, 403))
    return {403: OpenApiResponse(ErrorDetalleSerializer, description=descripcion, examples=ejemplos)}


def error_404(descripcion="El recurso no existe o el curso no está activo.", detalle=MENSAJE_404):
    return {404: OpenApiResponse(
        ErrorDetalleSerializer, description=descripcion,
        examples=[_ejemplo("No encontrado", {"detail": detalle}, 404)],
    )}


def respuestas(*bloques):
    """Une los dicts de respuesta: respuestas(ok(...), error_401(), error_404())."""
    unidas = {}
    for bloque in bloques:
        unidas.update(bloque)
    return unidas


# --------------------------------------------------------- Ejemplos de datos

EJEMPLO_CURSO = {
    "id": 1,
    "nombre": "abecedario",
    "titulo": "Abecedario",
    "descripcion": "Curso basico del abecedario en lengua de senas colombiana.",
    "portada_curso": "portadaAbecedario.jpg",
    "icono_curso": "",
    "insignia": "",
    "insignia_100": {"id": 4, "nombre": "Curso 100%", "imagen": "/media/biblioteca/insignia.png"},
    "activo": True,
    "total_preguntas": 10,
    "total_palabras": 10,
}

EJEMPLO_PREGUNTA_PUBLICA = {
    "id": 7,
    "texto": "Cual es la sena para la letra A?",
    "video": "abecedario/a.gif",
    "opciones": [{"id": 30, "texto": "C"}, {"id": 28, "texto": "A"}, {"id": 29, "texto": "B"}, {"id": 31, "texto": "D"}],
}

EJEMPLO_INTENTO = {
    "id": 15, "total": 10, "actual": 1, "aciertos": 0, "errores": 0,
    "finalizado": False, "pregunta": EJEMPLO_PREGUNTA_PUBLICA,
}

EJEMPLO_RESULTADO = {
    "curso": "abecedario",
    "curso_titulo": "Abecedario",
    "aciertos": 9,
    "errores": 1,
    "total": 10,
    "porcentaje": 90,
    "detalle_preguntas": [{
        "etiqueta": "1", "texto": "Cual es la sena para la letra A?", "video": "abecedario/a.gif",
        "acierto": True, "detalle": "Correcta",
        "opciones": [{"id": 28, "texto": "A", "es_correcta": True}, {"id": 29, "texto": "B", "es_correcta": False}],
        "elegidas": [28],
    }],
    "mensaje": "Sigue practicando, vas muy bien.",
    "insignia_100_ganada": False,
    "insignia_100_nueva": False,
    "insignia_100": None,
}

EJEMPLO_PERFIL = {
    "nombre": "estudiante_demo",
    "correo": "estudiante_demo@ensenarte.local",
    "avatar": "imgPredeterminadaUsuario.png",
    "foto_perfil_url": None,
    "estrellas": 2,
    "roles": ["Estudiante"],
}

TOKEN_EJEMPLO = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIn0.firma"
