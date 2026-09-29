from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.usuarios.models import PerfilUsuario

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta, RecursoVisual
from .permissions import EsCreadorDeCursos, EsInterprete, EsProfesor
from .serializers import (
    CursoPanelSerializer,
    OpcionPanelSerializer,
    PalabraPanelSerializer,
    PreguntaPanelSerializer,
    RecursoVisualSerializer,
)

# Creadores y profesores administran cursos y su contenido.
PUEDE_GESTIONAR_CURSOS = EsCreadorDeCursos | EsProfesor
PUEDE_GESTIONAR_CONTENIDO = PUEDE_GESTIONAR_CURSOS
PUEDE_SUBIR_GIF = PUEDE_GESTIONAR_CONTENIDO | EsInterprete


class CursoViewSet(viewsets.ModelViewSet):
    """CRUD de cursos. /api/panel/cursos/"""

    queryset = Curso.objects.all()
    serializer_class = CursoPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CURSOS]

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)


class PreguntaViewSet(viewsets.ModelViewSet):
    """CRUD de preguntas. Filtra con ?curso=<id>."""

    serializer_class = PreguntaPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO]

    def get_queryset(self):
        queryset = Pregunta.objects.select_related("curso").prefetch_related("opciones")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return queryset


class OpcionViewSet(viewsets.ModelViewSet):
    """CRUD de opciones. Filtra con ?pregunta=<id>."""

    serializer_class = OpcionPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO]

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
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO]

    def get_queryset(self):
        queryset = PalabraDiccionario.objects.select_related("curso")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return queryset


class RecursoVisualViewSet(viewsets.ModelViewSet):
    queryset = RecursoVisual.objects.all()
    serializer_class = RecursoVisualSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        queryset = super().get_queryset()
        busqueda = self.request.query_params.get("q", "").strip()
        extension = self.request.query_params.get("extension", "").lower()
        if busqueda:
            queryset = queryset.filter(nombre__icontains=busqueda)
        if extension:
            queryset = queryset.filter(archivo__iendswith=f".{extension}")
        return queryset

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            permiso = PUEDE_GESTIONAR_CONTENIDO | EsInterprete
        else:
            permiso = EsInterprete
        return [permiso()]

    def perform_create(self, serializer):
        serializer.save(subido_por=self.request.user)

    def destroy(self, request, *args, **kwargs):
        recurso = self.get_object()
        ruta = f"/{recurso.archivo.url.lstrip('/')}"
        esta_en_uso = (
            Curso.objects.filter(
                Q(portada_curso=ruta)
                | Q(imagen_diccionario=ruta)
                | Q(imagen_evaluacion=ruta)
            ).exists()
            or PalabraDiccionario.objects.filter(
                Q(imagen_frontal=ruta) | Q(video_gif=ruta)
            ).exists()
            or Pregunta.objects.filter(video=ruta).exists()
        )
        if esta_en_uso:
            return Response(
                {"detail": "No se puede borrar: el recurso está usado en contenido."},
                status=status.HTTP_409_CONFLICT,
            )

        recurso.archivo.delete(save=False)
        recurso.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([PUEDE_GESTIONAR_CURSOS])
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


@api_view(["GET"])
@permission_classes([PUEDE_GESTIONAR_CONTENIDO])
def estrellas_estudiantes(request):
    """GET /api/panel/estudiantes/estrellas/ -> estrellas de cada estudiante."""
    perfiles = PerfilUsuario.objects.select_related("user").order_by("-estrellas")
    data = [
        {
            "usuario": perfil.user.username,
            "correo": perfil.user.email,
            "estrellas": perfil.estrellas,
        }
        for perfil in perfiles
    ]
    return Response(data)


@api_view(["POST"])
@permission_classes([PUEDE_SUBIR_GIF])
def subir_gif_palabra(request, pk):
    """POST /api/panel/diccionario/<pk>/gif/ -> sube el gif de una palabra."""
    palabra = get_object_or_404(PalabraDiccionario, pk=pk)
    archivo = request.FILES.get("gif")
    if not archivo:
        return Response(
            {"detail": "Debes adjuntar el archivo en el campo 'gif'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ruta = default_storage.save(f"diccionario_gifs/{archivo.name}", archivo)
    palabra.video_gif = default_storage.url(ruta)
    palabra.save(update_fields=["video_gif"])
    return Response(PalabraPanelSerializer(palabra).data)


@api_view(["POST"])
@permission_classes([PUEDE_SUBIR_GIF])
def subir_gif_pregunta(request, pk):
    """POST /api/panel/preguntas/<pk>/gif/ -> sube el gif de una pregunta."""
    pregunta = get_object_or_404(Pregunta, pk=pk)
    archivo = request.FILES.get("gif")
    if not archivo:
        return Response(
            {"detail": "Debes adjuntar el archivo en el campo 'gif'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ruta = default_storage.save(f"evaluacion_gifs/{archivo.name}", archivo)
    pregunta.video = default_storage.url(ruta)
    pregunta.save(update_fields=["video"])
    return Response(PreguntaPanelSerializer(pregunta).data)
