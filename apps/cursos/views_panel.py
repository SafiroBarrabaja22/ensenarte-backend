import time
import uuid

import cloudinary.api
import cloudinary.exceptions
import cloudinary.uploader
import cloudinary.utils
from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.models import PerfilUsuario

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta, RecursoVisual
from .permissions import EsCreadorDeCursos, EsInterprete, EsProfesor
from .media_utils import extension_archivo, url_archivo
from .serializers import (
    CursoPanelSerializer,
    FORMATOS_IMAGEN_PERMITIDOS,
    OpcionPanelSerializer,
    PalabraPanelSerializer,
    PreguntaPanelSerializer,
    RecursoVisualSerializer,
)

# Creadores y profesores administran cursos y su contenido.
PUEDE_GESTIONAR_CURSOS = EsCreadorDeCursos | EsProfesor
PUEDE_GESTIONAR_CONTENIDO = PUEDE_GESTIONAR_CURSOS
PUEDE_SUBIR_GIF = PUEDE_GESTIONAR_CONTENIDO | EsInterprete
TAMANO_MAXIMO_RECURSO = 10 * 1024 * 1024


class RecursoVisualPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 60


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


class RecursoVisualPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 60


class RecursoVisualViewSet(viewsets.ModelViewSet):
    queryset = RecursoVisual.objects.all()
    serializer_class = RecursoVisualSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    pagination_class = RecursoVisualPagination
    pagination_class = RecursoVisualPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        busqueda = self.request.query_params.get("q", "").strip()
        extension = self.request.query_params.get("extension", "").lower()
        categoria = self.request.query_params.get("categoria", "").lower()
        usuario = self.request.user
        puede_ver_todo = bool(
            usuario.is_superuser
            or usuario.is_staff
            or usuario.groups.filter(
                name__in=("CreadorDeCursos", "Profesor", "Interprete")
            ).exists()
        )
        if not puede_ver_todo:
            queryset = queryset.filter(categoria=RecursoVisual.Categoria.AVATAR)
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        if busqueda:
            queryset = queryset.filter(nombre__icontains=busqueda)
        if extension:
            queryset = queryset.filter(extension=extension)
        return queryset

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        else:
            return [EsInterprete()]

    def perform_create(self, serializer):
        serializer.save(subido_por=self.request.user)

    @action(detail=False, methods=("post",), url_path="firmar-subida")
    def firmar_subida(self, request):
        nombre = str(request.data.get("nombre", "")).strip()
        categoria = str(request.data.get("categoria", "")).strip()
        extension = str(request.data.get("extension", "")).lower().lstrip(".")
        try:
            tamano = int(request.data.get("tamano", 0))
        except (TypeError, ValueError):
            tamano = 0

        categorias = {valor for valor, _ in RecursoVisual.Categoria.choices}
        if not nombre or len(nombre) > 120:
            return Response(
                {"nombre": "El nombre es obligatorio y no debe superar 120 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if categoria not in categorias:
            return Response(
                {"categoria": "Selecciona una categoría válida."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if f".{extension}" not in FORMATOS_IMAGEN_PERMITIDOS:
            return Response(
                {"archivo": "El formato de imagen no está permitido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tamano <= 0 or tamano > 10 * 1024 * 1024:
            return Response(
                {"archivo": "La imagen debe pesar como máximo 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parametros = {
            "folder": "media/biblioteca",
            "public_id": uuid.uuid4().hex,
            "timestamp": int(time.time()),
        }
        firma = cloudinary.utils.api_sign_request(
            parametros, settings.CLOUDINARY_CREDENTIALS["API_SECRET"]
        )
        cloud_name = settings.CLOUDINARY_CREDENTIALS["CLOUD_NAME"]
        return Response(
            {
                **parametros,
                "signature": firma,
                "api_key": settings.CLOUDINARY_CREDENTIALS["API_KEY"],
                "cloud_name": cloud_name,
                "upload_url": (
                    f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
                ),
            }
        )

    @action(detail=False, methods=("post",), url_path="finalizar-subida")
    def finalizar_subida(self, request):
        nombre = str(request.data.get("nombre", "")).strip()
        categoria = str(request.data.get("categoria", "")).strip()
        public_id = str(request.data.get("public_id", "")).strip()
        categorias = {valor for valor, _ in RecursoVisual.Categoria.choices}
        if not nombre or len(nombre) > 120 or categoria not in categorias:
            return Response(
                {"detail": "El nombre o la categoría no son válidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not public_id.startswith("media/biblioteca/"):
            return Response(
                {"detail": "El identificador del archivo no es válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            archivo = cloudinary.api.resource(public_id, resource_type="image")
        except cloudinary.exceptions.Error:
            return Response(
                {"detail": "Cloudinary no confirmó la imagen subida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        formato = str(archivo.get("format", "")).lower()
        if (
            archivo.get("bytes", 0) > 10 * 1024 * 1024
            or f".{formato}" not in FORMATOS_IMAGEN_PERMITIDOS
        ):
            cloudinary.uploader.destroy(
                public_id, invalidate=True, resource_type="image"
            )
            return Response(
                {"detail": "La imagen supera el tamaño o formato permitido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recurso, creado = RecursoVisual.objects.get_or_create(
            archivo=public_id,
            defaults={
                "nombre": nombre,
                "archivo_url": archivo["secure_url"],
                "extension": formato,
                "categoria": categoria,
                "subido_por": request.user,
            },
        )
        if not creado and recurso.categoria != categoria:
            return Response(
                {"detail": "El archivo ya está registrado en otra categoría."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            self.get_serializer(recurso).data,
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK,
        )

    @action(detail=False, methods=("post",), url_path="firmar-subida")
    def firmar_subida(self, request):
        nombre = str(request.data.get("nombre", "")).strip()
        categoria = str(request.data.get("categoria", "")).strip()
        extension = str(request.data.get("extension", "")).lower().lstrip(".")
        try:
            tamano = int(request.data.get("tamano", 0))
        except (TypeError, ValueError):
            tamano = 0

        categorias = {valor for valor, _ in RecursoVisual.Categoria.choices}
        if not nombre or len(nombre) > 120:
            return Response(
                {"nombre": "El nombre es obligatorio y no debe superar 120 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if categoria not in categorias:
            return Response(
                {"categoria": "Selecciona una categoría válida."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if f".{extension}" not in FORMATOS_IMAGEN_PERMITIDOS:
            return Response(
                {"archivo": "El formato de imagen no está permitido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tamano <= 0 or tamano > TAMANO_MAXIMO_RECURSO:
            return Response(
                {"archivo": "La imagen debe pesar como máximo 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parametros = {
            "folder": "media/biblioteca",
            "public_id": uuid.uuid4().hex,
            "timestamp": int(time.time()),
        }
        firma = cloudinary.utils.api_sign_request(
            parametros, settings.CLOUDINARY_CREDENTIALS["API_SECRET"]
        )
        cloud_name = settings.CLOUDINARY_CREDENTIALS["CLOUD_NAME"]
        return Response(
            {
                **parametros,
                "signature": firma,
                "api_key": settings.CLOUDINARY_CREDENTIALS["API_KEY"],
                "cloud_name": cloud_name,
                "upload_url": (
                    f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
                ),
            }
        )

    @action(detail=False, methods=("post",), url_path="finalizar-subida")
    def finalizar_subida(self, request):
        nombre = str(request.data.get("nombre", "")).strip()
        categoria = str(request.data.get("categoria", "")).strip()
        public_id = str(request.data.get("public_id", "")).strip()
        categorias = {valor for valor, _ in RecursoVisual.Categoria.choices}
        if not nombre or len(nombre) > 120 or categoria not in categorias:
            return Response(
                {"detail": "El nombre o la categoría no son válidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not public_id.startswith("media/biblioteca/"):
            return Response(
                {"detail": "El identificador del archivo no es válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            archivo = cloudinary.api.resource(public_id, resource_type="image")
        except cloudinary.exceptions.Error:
            return Response(
                {"detail": "Cloudinary no confirmó la imagen subida."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        formato = str(archivo.get("format", "")).lower()
        if (
            archivo.get("bytes", 0) > TAMANO_MAXIMO_RECURSO
            or f".{formato}" not in FORMATOS_IMAGEN_PERMITIDOS
        ):
            cloudinary.uploader.destroy(
                public_id, invalidate=True, resource_type="image"
            )
            return Response(
                {"detail": "La imagen supera el tamaño o formato permitido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recurso, creado = RecursoVisual.objects.get_or_create(
            archivo=public_id,
            defaults={
                "nombre": nombre,
                "archivo_url": archivo["secure_url"],
                "extension": formato,
                "categoria": categoria,
                "subido_por": request.user,
            },
        )
        if not creado and recurso.categoria != categoria:
            return Response(
                {"detail": "El archivo ya está registrado en otra categoría."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            self.get_serializer(recurso).data,
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        recurso = self.get_object()
        ruta = url_archivo(recurso.archivo)
        nombre_archivo = (recurso.archivo.name or "").lstrip("/")
        rutas = {
            ruta,
            recurso.archivo_url,
            nombre_archivo,
            f"/{nombre_archivo}",
            f"/media/{nombre_archivo}",
            f"media/{nombre_archivo}",
        }
        esta_en_uso = (
            Curso.objects.filter(
                Q(portada_curso__in=rutas)
                | Q(imagen_diccionario__in=rutas)
                | Q(imagen_evaluacion__in=rutas)
                | Q(insignia__in=rutas)
            ).exists()
            or Curso.objects.filter(insignia_100=recurso).exists()
            or PalabraDiccionario.objects.filter(
                Q(imagen_frontal__in=rutas) | Q(video_gif__in=rutas)
            ).exists()
            or Pregunta.objects.filter(video__in=rutas).exists()
            or PerfilUsuario.objects.filter(avatar__in=rutas).exists()
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
