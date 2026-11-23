from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics

from apps.cursos.permissions import PUEDE_APRENDER
from config.openapi import (
    ETIQUETA_EVALUACION,
    error_400,
    error_401,
    error_403,
    ok,
    respuestas,
)

from .models import EvaluacionCamara
from .serializers import EvaluacionCamaraSerializer

EJEMPLO_SESION = {
    "id": 12,
    "fecha": "2026-11-16T15:30:00-05:00",
    "curso": "abecedario",
    "total": 10,
    "correctas": 7,
    "porcentaje": 70,
    "aprobado": True,
    "umbral_aplicado": 70,
    "intentos": [
        {"letra_objetivo": "A", "acerto": True, "tiempo_ms": 2300, "confianza": 0.82},
        {"letra_objetivo": "B", "acerto": False, "tiempo_ms": 5000, "confianza": 0.41},
    ],
    "insignia_100_ganada": False,
    "insignia_100_nueva": False,
    "insignia_100": None,
}

ROLES = "Cualquier rol (Estudiante, Profesor, Interprete, Validador, CreadorDeCursos, Administrador)."
ERROR_SIN_ROL = error_403(descripcion="El usuario no tiene ningún rol asignado.")


@extend_schema_view(
    get=extend_schema(
        tags=[ETIQUETA_EVALUACION],
        summary="Historial de evaluaciones con cámara",
        description="Las 5 sesiones más recientes del usuario, de la más nueva a la más antigua. " + ROLES,
        parameters=[OpenApiParameter(
            "curso", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
            description="Filtra por slug del curso, p. ej. `abecedario`.",
        )],
        responses=respuestas(
            ok(EvaluacionCamaraSerializer(many=True), [EJEMPLO_SESION]),
            error_401(),
            ERROR_SIN_ROL,
        ),
    ),
    post=extend_schema(
        tags=[ETIQUETA_EVALUACION],
        summary="Guardar una evaluación con cámara",
        description="El reconocimiento de las letras ocurre en el navegador; el video nunca llega "
        "al servidor. El cliente envía solo los `intentos` (máximo 50) y el servidor calcula "
        "`porcentaje` y `aprobado` con el umbral vigente (70 %). Si el cliente envía esos campos, "
        "se ignoran. " + ROLES,
        responses=respuestas(
            ok(EvaluacionCamaraSerializer, EJEMPLO_SESION, codigo=201, descripcion="Sesión guardada con su resultado."),
            error_400({"intentos": ["Una sesion admite como maximo 50 intentos."]}),
            error_401(),
            ERROR_SIN_ROL,
        ),
    ),
)
class EvaluacionCamaraListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/evaluacion-camara/ -> historial del usuario autenticado.
    POST /api/evaluacion-camara/ -> guarda una sesion y devuelve el resultado.

    Cuerpo del POST: {"intentos": [{"letra_objetivo": "A", "acerto": true,
                                    "tiempo_ms": 2300, "confianza": 0.8}, ...]}
    """

    serializer_class = EvaluacionCamaraSerializer
    permission_classes = [PUEDE_APRENDER]

    def get_queryset(self):
        queryset = EvaluacionCamara.objects.filter(
            usuario=self.request.user
        ).select_related("curso").prefetch_related("intentos").order_by("-fecha", "-id")
        curso = self.request.query_params.get("curso")
        if curso:
            queryset = queryset.filter(curso__nombre=curso)
        return queryset[:5]

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)
