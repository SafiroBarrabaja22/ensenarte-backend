import uuid
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.models import PerfilUsuario

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta, RecursoVisual
from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    ROLES_GESTION_GLOBAL,
    tiene_rol,
)

from .permissions import (
    PUEDE_GESTIONAR_BIBLIOTECA,
    PUEDE_GESTIONAR_CONTENIDO,
    PUEDE_SUBIR_GIF,
    EsDuenoDelCurso,
    SoloLectura,
    exigir_curso_editable,
)
from .serializers import (
    CursoPanelSerializer,
    OpcionPanelSerializer,
    PalabraPanelSerializer,
    PreguntaPanelSerializer,
    FORMATOS_IMAGEN_PERMITIDOS,
    RecursoVisualSerializer,
)



def _es_gestor_global(usuario):
    return tiene_rol(usuario, *ROLES_GESTION_GLOBAL)


def _solo_lo_propio(vista, queryset, campo_dueno):
    """
    En el listado, un Profesor solo ve el contenido de sus cursos. En detalle,
    edicion y borrado no se filtra: EsDuenoDelCurso responde 403 si el curso
    es de otro, en vez de un 404 que esconde el motivo.
    """
    usuario = vista.request.user
    if vista.action == "list" and not _es_gestor_global(usuario):
        return queryset.filter(**{campo_dueno: usuario})
    return queryset


class CursoViewSet(viewsets.ModelViewSet):
    """CRUD de cursos. /api/panel/cursos/"""

    serializer_class = CursoPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO, EsDuenoDelCurso]

    def get_queryset(self):
        return _solo_lo_propio(self, Curso.objects.all(), "creado_por")

    # usuario_auditoria: los triggers curso_auditoria_* registran quien hizo el cambio.
    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)


class PreguntaViewSet(viewsets.ModelViewSet):
    """CRUD de preguntas. Filtra con ?curso=<id>."""

    serializer_class = PreguntaPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO, EsDuenoDelCurso]
    # Sin paginar: el panel muestra y cuenta todas las preguntas del curso.
    pagination_class = None

    def get_queryset(self):
        queryset = Pregunta.objects.select_related("curso").prefetch_related("opciones")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return _solo_lo_propio(self, queryset, "curso__creado_por")

    def perform_create(self, serializer):
        exigir_curso_editable(self.request.user, serializer.validated_data["curso"])
        serializer.save()

    def perform_update(self, serializer):
        curso = serializer.validated_data.get("curso", serializer.instance.curso)
        exigir_curso_editable(self.request.user, curso)
        serializer.save()


class OpcionViewSet(viewsets.ModelViewSet):
    """CRUD de opciones. Filtra con ?pregunta=<id>."""

    serializer_class = OpcionPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO, EsDuenoDelCurso]

    def get_queryset(self):
        queryset = OpcionPregunta.objects.select_related("pregunta__curso")
        pregunta_id = self.request.query_params.get("pregunta")
        if pregunta_id:
            queryset = queryset.filter(pregunta_id=pregunta_id)
        return _solo_lo_propio(self, queryset, "pregunta__curso__creado_por")

    def perform_create(self, serializer):
        pregunta = serializer.validated_data["pregunta"]
        exigir_curso_editable(self.request.user, pregunta.curso)
        opcion = serializer.save()
        self._forzar_unica_correcta(opcion)

    def perform_update(self, serializer):
        pregunta = serializer.validated_data.get("pregunta", serializer.instance.pregunta)
        exigir_curso_editable(self.request.user, pregunta.curso)
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
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO, EsDuenoDelCurso]
    # Sin paginar: para reordenar hace falta la lista completa del curso.
    pagination_class = None

    def get_queryset(self):
        queryset = PalabraDiccionario.objects.select_related("curso")
        curso_id = self.request.query_params.get("curso")
        if curso_id:
            queryset = queryset.filter(curso_id=curso_id)
        return _solo_lo_propio(self, queryset, "curso__creado_por")

    def perform_update(self, serializer):
        curso = serializer.validated_data.get("curso", serializer.instance.curso)
        exigir_curso_editable(self.request.user, curso)
        serializer.save()

    def perform_create(self, serializer):
        """Las palabras nuevas quedan al final del diccionario."""
        curso = serializer.validated_data["curso"]
        exigir_curso_editable(self.request.user, curso)
        ultimo = PalabraDiccionario.objects.filter(curso=curso).aggregate(
            maximo=Max("orden")
        )["maximo"]
        serializer.save(orden=(ultimo or 0) + 1)

    @action(detail=False, methods=["post"])
    def reordenar(self, request):
        """POST /api/panel/diccionario/reordenar/ {"curso": id, "ids": [...]}"""
        curso_id = request.data.get("curso")
        ids = request.data.get("ids")
        if not curso_id or not isinstance(ids, list):
            return Response(
                {"detail": "Debes enviar 'curso' y la lista 'ids'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        exigir_curso_editable(request.user, get_object_or_404(Curso, pk=curso_id))
        palabras = {
            palabra.id: palabra
            for palabra in PalabraDiccionario.objects.filter(curso_id=curso_id)
        }
        try:
            ids = [int(valor) for valor in ids]
        except (TypeError, ValueError):
            ids = []
        if sorted(ids) != sorted(palabras):
            return Response(
                {"detail": "La lista debe incluir todas las palabras del curso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            for posicion, palabra_id in enumerate(ids, start=1):
                palabra = palabras[palabra_id]
                if palabra.orden != posicion:
                    palabra.orden = posicion
                    palabra.save(update_fields=["orden"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecursoVisualViewSet(viewsets.ModelViewSet):
    """
    Biblioteca visual (recursos, avatares e insignias). /api/panel/recursos/

    Leer: cualquier usuario autenticado (sin rol de contenido solo ve avatares,
    que necesita para editar su perfil). Crear, editar y borrar: Interprete o
    Administrador.
    """

    queryset = RecursoVisual.objects.all()
    serializer_class = RecursoVisualSerializer
    permission_classes = [IsAuthenticated & (SoloLectura | PUEDE_GESTIONAR_BIBLIOTECA)]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def paginate_queryset(self, queryset):
        """Pagina (50 por pagina) solo si se pide ?page=N, como hace la biblioteca.

        Los selectores de imagenes y avatares no envian page y reciben la lista completa.
        """
        if "page" not in self.request.query_params:
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        queryset = super().get_queryset()
        busqueda = self.request.query_params.get("q", "").strip()
        extension = self.request.query_params.get("extension", "").lower()
        categoria = self.request.query_params.get("categoria", "").lower()
        usuario = self.request.user
        puede_ver_todo = tiene_rol(
            usuario, ROL_ADMINISTRADOR, ROL_CREADOR, ROL_PROFESOR, ROL_INTERPRETE
        )
        if not puede_ver_todo:
            queryset = queryset.filter(categoria=RecursoVisual.Categoria.AVATAR)
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        if busqueda:
            queryset = queryset.filter(nombre__icontains=busqueda)
        if extension:
            queryset = queryset.filter(archivo__iendswith=f".{extension}")
        return queryset

    def perform_create(self, serializer):
        serializer.save(subido_por=self.request.user)

    def destroy(self, request, *args, **kwargs):
        recurso = self.get_object()
        ruta = f"/{recurso.archivo.url.lstrip('/')}"
        esta_en_uso = (
            Curso.objects.filter(
                Q(portada_curso=ruta)
                | Q(icono_curso=ruta)
                | Q(insignia=ruta)
            ).exists()
            or Curso.objects.filter(insignia_100=recurso).exists()
            or PalabraDiccionario.objects.filter(
                Q(imagen_frontal=ruta) | Q(video_gif=ruta)
            ).exists()
            or Pregunta.objects.filter(video=ruta).exists()
            or PerfilUsuario.objects.filter(avatar=ruta).exists()
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
@permission_classes([PUEDE_GESTIONAR_CONTENIDO])
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
    # El Interprete sube gifs a cualquier curso; un Profesor solo a los suyos.
    if not tiene_rol(request.user, ROL_INTERPRETE):
        exigir_curso_editable(request.user, palabra.curso)
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
    # El Interprete sube gifs a cualquier curso; un Profesor solo a los suyos.
    if not tiene_rol(request.user, ROL_INTERPRETE):
        exigir_curso_editable(request.user, pregunta.curso)
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


@api_view(["POST"])
@permission_classes([PUEDE_SUBIR_GIF])
def subir_archivo_contenido(request):
    """POST /api/panel/archivos/ -> sube una imagen de uso puntual.

    El archivo queda en media/contenido/ y NO se registra en la biblioteca,
    asi que no aparece como recurso para otros cursos.
    """
    archivo = request.FILES.get("archivo")
    if not archivo:
        return Response(
            {"detail": "Debes adjuntar el archivo en el campo 'archivo'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    extension = Path(archivo.name or "").suffix.lower()
    if extension not in FORMATOS_IMAGEN_PERMITIDOS:
        return Response(
            {"detail": "Formato de imagen no permitido."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if archivo.size > 10 * 1024 * 1024:
        return Response(
            {"detail": "El archivo no puede superar 10 MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ruta = default_storage.save(f"contenido/{uuid.uuid4().hex}{extension}", archivo)
    url = f"/{default_storage.url(ruta).lstrip('/')}"
    return Response({"archivo_url": url}, status=status.HTTP_201_CREATED)
