from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta
from .permissions import EsCreadorDeCursos
from .serializers import (
    CursoPanelSerializer,
    OpcionPanelSerializer,
    PalabraPanelSerializer,
    PreguntaPanelSerializer,
)


class CursoViewSet(viewsets.ModelViewSet):
    """CRUD de cursos. /api/panel/cursos/"""

    queryset = Curso.objects.all()
    serializer_class = CursoPanelSerializer
    permission_classes = [EsCreadorDeCursos]

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)


class PreguntaViewSet(viewsets.ModelViewSet):
    """CRUD de preguntas. Filtra con ?curso=<id>."""

    serializer_class = PreguntaPanelSerializer
    permission_classes = [EsCreadorDeCursos]

    def get_queryset(self):
        queryset = Pregunta.objects.select_related("curso").prefetch_related("opciones")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return queryset


class OpcionViewSet(viewsets.ModelViewSet):
    """CRUD de opciones. Filtra con ?pregunta=<id>."""

    serializer_class = OpcionPanelSerializer
    permission_classes = [EsCreadorDeCursos]

    def get_queryset(self):
        queryset = OpcionPregunta.objects.select_related("pregunta")
        pregunta_id = self.request.query_params.get("pregunta")
        if pregunta_id:
            queryset = queryset.filter(pregunta_id=pregunta_id)
        return queryset

    def perform_create(self, serializer):
        opcion = serializer.save()
        self._forzar_unica_correcta(opcion)

    def perform_update(self, serializer):
        opcion = serializer.save()
        self._forzar_unica_correcta(opcion)

    @staticmethod
    def _forzar_unica_correcta(opcion):
        """Solo una opcion por pregunta puede ser la correcta."""
        if opcion.es_correcta:
            OpcionPregunta.objects.filter(pregunta=opcion.pregunta).exclude(
                pk=opcion.pk
            ).update(es_correcta=False)


class PalabraViewSet(viewsets.ModelViewSet):
    """CRUD del diccionario. Filtra con ?curso=<id>."""

    serializer_class = PalabraPanelSerializer
    permission_classes = [EsCreadorDeCursos]

    def get_queryset(self):
        queryset = PalabraDiccionario.objects.select_related("curso")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return queryset


@api_view(["GET"])
@permission_classes([EsCreadorDeCursos])
def resumen_panel(request):
    """GET /api/panel/resumen/ -> cifras del dashboard."""
    return Response(
        {
            "total_cursos": Curso.objects.count(),
            "cursos_activos": Curso.objects.filter(activo=True).count(),
            "total_preguntas": Pregunta.objects.count(),
            "total_palabras": PalabraDiccionario.objects.count(),
            "total_usuarios": User.objects.count(),
        }
    )
