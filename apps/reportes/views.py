"""
Endpoints de reportes. Devuelven el archivo (PDF o Excel) como adjunto.

El frontend los descarga con fetch + cabecera Authorization y convierte la
respuesta en blob: un enlace <a href> directo no lleva el token JWT y la API
respondería 401.
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.cursos.models import Curso
from apps.cursos.permissions import (
    PUEDE_APRENDER,
    PUEDE_GESTIONAR_CONTENIDO,
    EsAdministrador,
    exigir_curso_editable,
)
from apps.cursos.procedimientos import ProcedimientoNoDisponible
from config.openapi import (
    ETIQUETA_REPORTES,
    MENSAJE_403_CURSO_AJENO,
    PARAM_SLUG,
    ErrorDetalleSerializer,
    error_400,
    error_401,
    error_403,
    error_404,
    param_id,
    respuestas,
)

from . import datos, excel, historial, pdf

TIPO_PDF = "application/pdf"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMATOS = {"pdf": (TIPO_PDF, pdf.construir), "xlsx": (TIPO_XLSX, excel.construir)}
MENSAJE_FORMATO = "Formato no válido. Usa formato=pdf o formato=xlsx."


def _formato(request):
    return request.query_params.get("formato", "pdf").lower()


def _archivo(reporte, formato):
    tipo, construir = FORMATOS[formato]
    respuesta = HttpResponse(construir(reporte), content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="{reporte.nombre_archivo}.{formato}"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def _formato_invalido():
    return Response({"detail": MENSAJE_FORMATO}, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------------ Documentacion

PARAM_FORMATO = OpenApiParameter(
    "formato", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
    enum=list(FORMATOS), default="pdf",
    description="`pdf` (por defecto) o `xlsx` (Excel).",
)
ARCHIVOS = {
    (200, TIPO_PDF): OpenApiResponse(OpenApiTypes.BINARY, description="Reporte en PDF (`formato=pdf`)."),
    (200, TIPO_XLSX): OpenApiResponse(OpenApiTypes.BINARY, description="Reporte en Excel (`formato=xlsx`)."),
}
ERROR_FORMATO = error_400({"detail": MENSAJE_FORMATO}, detalle=True, descripcion="`formato` no es `pdf` ni `xlsx`.")
NOTA_DESCARGA = (
    " La descarga debe hacerse con fetch y la cabecera `Authorization: Bearer`: "
    "un enlace directo no lleva el token y responde 401. El nombre del archivo "
    "llega en `Content-Disposition`."
)


# ------------------------------------------------------------------ 1. Constancia


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Constancia de curso completado",
    description="Constancia del usuario autenticado para un curso que ya completó (PDF horizontal "
    "con marco, o Excel). Solo **Estudiante**." + NOTA_DESCARGA,
    parameters=[PARAM_SLUG, PARAM_FORMATO],
    responses=respuestas(
        ARCHIVOS, ERROR_FORMATO, error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404("El curso no existe o el usuario todavía no lo completa.",
                  detalle="Todavía no has completado este curso."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
def constancia(request, slug):
    formato = _formato(request)
    if formato not in FORMATOS:
        return _formato_invalido()
    return _archivo(datos.constancia(request.user, slug), formato)


# ------------------------------------------------------------------ 2. Progreso del curso


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Progreso de los estudiantes de un curso",
    description="Estado, aciertos, errores, insignia y última actividad de cada estudiante con "
    "actividad en el curso, más un resumen. Roles: Profesor (solo sus cursos), CreadorDeCursos "
    "o Administrador." + NOTA_DESCARGA,
    parameters=[param_id("el curso"), PARAM_FORMATO],
    responses=respuestas(
        ARCHIVOS, ERROR_FORMATO, error_401(),
        error_403(descripcion="El rol no administra contenido, o el curso es de otro profesor.",
                  extra=MENSAJE_403_CURSO_AJENO),
        error_404("El curso no existe."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_GESTIONAR_CONTENIDO])
def progreso_curso(request, pk):
    formato = _formato(request)
    if formato not in FORMATOS:
        return _formato_invalido()
    curso = get_object_or_404(Curso.objects.select_related("creado_por"), pk=pk)
    exigir_curso_editable(request.user, curso)
    return _archivo(datos.progreso_curso(curso), formato)


# ------------------------------------------------------------------ 3. Plataforma


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Estadísticas de la plataforma",
    description="Estadísticas por curso y ranking de estudiantes. Las cifras salen de los "
    "procedimientos almacenados `estadisticas_curso` y `ranking_estudiantes` (MySQL); con otra "
    "base de datos responde 503. Rol: **Administrador**." + NOTA_DESCARGA,
    parameters=[PARAM_FORMATO],
    responses=respuestas(
        ARCHIVOS, ERROR_FORMATO, error_401(),
        error_403(descripcion="Solo el Administrador.", detalle="Esta accion requiere el rol Administrador."),
        {503: OpenApiResponse(ErrorDetalleSerializer, description="La base no es MySQL: no hay procedimientos almacenados.")},
    ),
)
@api_view(["GET"])
@permission_classes([EsAdministrador])
def plataforma(request):
    formato = _formato(request)
    if formato not in FORMATOS:
        return _formato_invalido()
    try:
        reporte = datos.plataforma()
    except ProcedimientoNoDisponible:
        return Response(
            {"detail": "Este reporte usa los procedimientos almacenados de MySQL y no está "
                       "disponible con la base de datos actual."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return _archivo(reporte, formato)


# ------------------------------------------------------------------ 4. Historial de intentos


PARAM_TIPO_HISTORIAL = OpenApiParameter(
    "tipo", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
    enum=sorted(historial.TIPOS), default="preguntas",
    description="`preguntas` (evaluación por preguntas, por defecto) o `camara` (evaluación con cámara).",
)


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Historial de intentos de una evaluación (PDF)",
    description="PDF con las últimas 5 sesiones **del usuario autenticado** en la evaluación del "
    "curso, con el mismo diseño de la tarjeta \"Tu progreso\" de la página: anillo con la "
    "última sesión, comparación con la anterior, gráfica \"Tus últimos intentos\", tarjetas "
    "por sesión y tabla de detalle. Nunca incluye datos de otros usuarios. Solo "
    "**Estudiante**." + NOTA_DESCARGA,
    parameters=[PARAM_SLUG, PARAM_TIPO_HISTORIAL],
    responses=respuestas(
        {(200, TIPO_PDF): OpenApiResponse(OpenApiTypes.BINARY, description="Historial en PDF.")},
        error_400({"detail": "Tipo no válido. Usa tipo=preguntas o tipo=camara."}, detalle=True,
                  descripcion="`tipo` no es `preguntas` ni `camara`."),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404("El curso no existe o no está activo."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
def historial_intentos(request, slug):
    tipo = request.query_params.get("tipo", "preguntas").lower()
    if tipo not in historial.TIPOS:
        return Response({"detail": "Tipo no válido. Usa tipo=preguntas o tipo=camara."},
                        status=status.HTTP_400_BAD_REQUEST)
    contenido, nombre = historial.construir(request.user, slug, tipo)
    respuesta = HttpResponse(contenido, content_type=TIPO_PDF)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta
