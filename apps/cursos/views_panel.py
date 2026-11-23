from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.models import PerfilUsuario
from config.openapi import (
    ETIQUETA_PANEL,
    ETIQUETA_REPORTES,
    MENSAJE_403_CURSO_AJENO,
    ErrorDetalleSerializer,
    error_400,
    error_401,
    error_403,
    error_404,
    filtro,
    ok,
    param_id,
    respuestas,
    sin_contenido,
)

from .models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta, RecursoVisual
from apps.usuarios.roles import (
    ROL_ADMINISTRADOR,
    ROL_CREADOR,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    ROL_VALIDADOR,
    ROLES_GESTION_GLOBAL,
    tiene_rol,
)

from .permissions import (
    PUEDE_GESTIONAR_BIBLIOTECA,
    PUEDE_GESTIONAR_CONTENIDO,
    PUEDE_SUBIR_GIF,
    PUEDE_VER_REVISIONES,
    EsDuenoDelCurso,
    EsValidador,
    SoloLectura,
    exigir_curso_editable,
)
from .archivos import FORMATOS_GIF, nombre_seguro, validar_imagen
from .procedimientos import marcar_opcion_correcta, reglas_como_error_400, usuario_auditoria
from .serializers import (
    CursoPanelSerializer,
    OpcionPanelSerializer,
    PalabraPanelSerializer,
    PreguntaPanelSerializer,
    RecursoVisualSerializer,
    RevisionSenaSerializer,
)
from . import validacion
from config.limites import MAX_COMENTARIO_VALIDACION



# ==========================================================
# DOCUMENTACION OPENAPI
# ==========================================================

ROLES_CONTENIDO = (
    "Roles: **Profesor** (solo en los cursos que él creó), **CreadorDeCursos** o "
    "**Administrador** (cualquier curso)."
)
ROLES_BIBLIOTECA_ESCRITURA = "Roles: **Interprete** o **Administrador**."


def _doc_crud(singular, plural, articulo, serializer, ejemplo, ejemplo_400,
              descripcion_roles=ROLES_CONTENIDO, filtros=(), curso_propio=True):
    """extend_schema para las 6 acciones de un ModelViewSet del panel."""
    # drf-spectacular envuelve solo el ejemplo en {count, next, previous, results}
    # cuando la vista pagina; aqui va siempre la lista simple.
    listado = [ejemplo]
    e403 = error_403(
        descripcion="El rol no administra contenido" + (", o el curso es de otro profesor." if curso_propio else "."),
        extra=MENSAJE_403_CURSO_AJENO if curso_propio else None,
    )
    e403_listado = error_403(descripcion="El rol no administra contenido.")
    nota_listado = (
        " Un Profesor solo ve el contenido de sus propios cursos." if curso_propio else ""
    )
    comun = {"tags": [ETIQUETA_PANEL]}
    return {
        "list": extend_schema(
            **comun, summary=f"Listar {plural}",
            description=f"Lista {plural}.{nota_listado} {descripcion_roles}",
            parameters=list(filtros),
            responses=respuestas(ok(serializer(many=True), listado), error_401(), e403_listado),
        ),
        "create": extend_schema(
            **comun, summary=f"Crear {singular}",
            description=f"Crea {articulo} {singular}. {descripcion_roles}",
            responses=respuestas(
                ok(serializer, ejemplo, codigo=201, descripcion="Creado."),
                error_400(ejemplo_400), error_401(), e403,
            ),
        ),
        "retrieve": extend_schema(
            **comun, summary=f"Ver {singular}",
            description=f"Detalle de {articulo} {singular}. {descripcion_roles}",
            parameters=[param_id(f"{articulo} {singular}")],
            responses=respuestas(ok(serializer, ejemplo), error_401(), e403, error_404()),
        ),
        "update": extend_schema(
            **comun, summary=f"Reemplazar {singular}",
            description=f"Reemplaza todos los campos de {articulo} {singular}. {descripcion_roles}",
            parameters=[param_id(f"{articulo} {singular}")],
            responses=respuestas(ok(serializer, ejemplo), error_400(ejemplo_400), error_401(), e403, error_404()),
        ),
        "partial_update": extend_schema(
            **comun, summary=f"Editar {singular}",
            description=f"Cambia solo los campos enviados. {descripcion_roles}",
            parameters=[param_id(f"{articulo} {singular}")],
            responses=respuestas(ok(serializer, ejemplo), error_400(ejemplo_400), error_401(), e403, error_404()),
        ),
        "destroy": extend_schema(
            **comun, summary=f"Eliminar {singular}",
            description=f"Elimina {articulo} {singular}. {descripcion_roles}",
            parameters=[param_id(f"{articulo} {singular}")],
            responses=respuestas(sin_contenido("Eliminado."), error_401(), e403, error_404()),
        ),
    }


EJEMPLO_CURSO_PANEL = {
    "id": 1, "nombre": "abecedario", "titulo": "Abecedario",
    "descripcion": "Curso basico del abecedario.", "portada_curso": "portadaAbecedario.jpg",
    "icono_curso": "", "insignia": "", "insignia_100": 4, "insignia_100_nombre": "Curso 100%",
    "insignia_100_url": "/media/biblioteca/insignia.png", "preguntas_por_evaluacion": 10,
    "activo": True, "creado_por": "profesor_demo",
    "fecha_creacion": "2026-11-16T10:00:00-05:00", "fecha_modificacion": "2026-11-16T10:00:00-05:00",
}
EJEMPLO_OPCION = {"id": 28, "pregunta": 7, "texto": "A", "es_correcta": True}
EJEMPLO_PREGUNTA_PANEL = {
    "id": 7, "curso": 1, "texto": "Cual es la sena para la letra A?", "video": "abecedario/a.gif",
    "opciones": [EJEMPLO_OPCION], "estado_sena": "aprobada",
}
EJEMPLO_PALABRA = {
    "id": 1, "curso": 1, "titulo": "A", "imagen_frontal": "abecedario/a.png",
    "video_gif": "abecedario/a.gif", "orden": 1, "estado_sena": "aprobada",
}
EJEMPLO_RECURSO = {
    "id": 4, "nombre": "Insignia dorada", "archivo_url": "/media/biblioteca/3f2a9c.png",
    "extension": "png", "categoria": "curso_100", "fecha_creacion": "2026-11-16T10:00:00-05:00",
    "es_sena": False, "estado_validacion": "aprobada", "comentario_validacion": "",
    "subido_por": "interprete_demo",
}
EJEMPLO_RECURSO_SENA = {
    **EJEMPLO_RECURSO, "id": 9, "nombre": "Seña letra A", "archivo_url": "/media/biblioteca/7b1e0d.gif",
    "extension": "gif", "categoria": "recurso", "es_sena": True, "estado_validacion": "pendiente",
}
EJEMPLO_REVISION = {
    "id": 3, "accion": "rechazada", "comentario": "La mano debe quedar a la altura del pecho.",
    "usuario": "validador_demo", "archivo": "biblioteca/7b1e0d.gif", "fecha": "2026-11-23T09:30:00-05:00",
}

SubirGifSerializer = inline_serializer(
    "SubirGif", {"gif": serializers.FileField(help_text="Archivo .gif de la seña.")}
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


@extend_schema_view(**_doc_crud(
    "curso", "cursos", "un", CursoPanelSerializer, EJEMPLO_CURSO_PANEL,
    {"nombre": ["Ya existe Curso con este Nombre."], "titulo": ["Este campo es requerido."]},
))
class CursoViewSet(viewsets.ModelViewSet):
    """CRUD de cursos. /api/panel/cursos/"""

    serializer_class = CursoPanelSerializer
    permission_classes = [PUEDE_GESTIONAR_CONTENIDO, EsDuenoDelCurso]

    def get_queryset(self):
        return _solo_lo_propio(self, Curso.objects.all(), "creado_por")

    # usuario_auditoria: los triggers curso_auditoria_* registran quien hizo el cambio.
    def perform_create(self, serializer):
        with usuario_auditoria(self.request.user):
            serializer.save(creado_por=self.request.user)

    def perform_update(self, serializer):
        with usuario_auditoria(self.request.user):
            serializer.save()

    def perform_destroy(self, instance):
        with usuario_auditoria(self.request.user):
            instance.delete()


@extend_schema_view(**_doc_crud(
    "pregunta", "preguntas", "una", PreguntaPanelSerializer, EJEMPLO_PREGUNTA_PANEL,
    {"curso": ["Este campo es requerido."], "texto": ["Este campo no puede estar en blanco."]},
    filtros=[filtro("curso", "Solo las preguntas de este curso (ID).")],
))
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


@extend_schema_view(**_doc_crud(
    "opción", "opciones", "una", OpcionPanelSerializer, EJEMPLO_OPCION,
    {"non_field_errors": ["Una pregunta admite como maximo 4 opciones."]},
    filtros=[filtro("pregunta", "Solo las opciones de esta pregunta (ID).")],
))
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
        self._guardar(serializer)

    def perform_update(self, serializer):
        pregunta = serializer.validated_data.get("pregunta", serializer.instance.pregunta)
        exigir_curso_editable(self.request.user, pregunta.curso)
        self._guardar(serializer)

    @staticmethod
    def _guardar(serializer):
        """
        Solo una opcion por pregunta puede ser la correcta. En MySQL un trigger
        rechaza dos correctas a la vez, asi que la opcion se guarda como no
        correcta y luego marcar_opcion_correcta desmarca las demas y la marca.
        """
        marcar = serializer.validated_data.get("es_correcta") is True
        with transaction.atomic(), reglas_como_error_400():
            opcion = serializer.save(es_correcta=False) if marcar else serializer.save()
            if marcar:
                marcar_opcion_correcta(opcion)


@extend_schema_view(**_doc_crud(
    "palabra", "palabras del diccionario", "una", PalabraPanelSerializer, EJEMPLO_PALABRA,
    {"titulo": ["Este campo es requerido."]},
    filtros=[filtro("curso", "Solo las palabras de este curso (ID).")],
))
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

    @extend_schema(
        tags=[ETIQUETA_PANEL],
        summary="Reordenar el diccionario",
        description="Recibe todos los IDs de palabras del curso en el orden nuevo. " + ROLES_CONTENIDO,
        request=inline_serializer("ReordenarDiccionario", {
            "curso": serializers.IntegerField(),
            "ids": serializers.ListField(child=serializers.IntegerField(), help_text="Todas las palabras del curso."),
        }),
        responses=respuestas(
            sin_contenido("Orden guardado."),
            error_400({"detail": "La lista debe incluir todas las palabras del curso."}, detalle=True,
                      descripcion="Falta `curso`, falta `ids` o la lista no coincide con las palabras del curso."),
            error_401(),
            error_403(descripcion="El rol no administra contenido, o el curso es de otro profesor.",
                      extra=MENSAJE_403_CURSO_AJENO),
            error_404("El curso no existe."),
        ),
    )
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


@extend_schema_view(**{
    **_doc_crud(
        "recurso", "recursos de la biblioteca", "un", RecursoVisualSerializer, EJEMPLO_RECURSO,
        {"archivo": ["Formatos permitidos: PNG, GIF, JPG, JPEG, JFIF, WEBP, BMP, TIFF, AVIF, HEIC y HEIF."]},
        descripcion_roles=ROLES_BIBLIOTECA_ESCRITURA, curso_propio=False,
        filtros=[
            filtro("q", "Busca en el nombre.", tipo=str),
            filtro("extension", "Extensión del archivo, p. ej. `gif`.", tipo=str),
            filtro("categoria", "`recurso`, `avatar`, `insignia` o `curso_100`.", tipo=str),
            filtro("estado", "Estado de validación de las señas: `pendiente`, `aprobada` o `rechazada`. "
                   "Las señas sin aprobar solo las ven el Interprete, el Validador y el Administrador.", tipo=str),
            filtro("page", "Página (50 por página). Sin `page` devuelve la lista completa sin paginar."),
        ],
    ),
    "list": extend_schema(
        tags=[ETIQUETA_PANEL], summary="Listar la biblioteca visual",
        description="Recursos, avatares e insignias. Cualquier usuario autenticado; sin rol de "
        "contenido solo ve los `avatar` (para editar su perfil). Sin `?page=` devuelve la lista completa.",
        parameters=[
            filtro("q", "Busca en el nombre.", tipo=str),
            filtro("extension", "Extensión del archivo, p. ej. `gif`.", tipo=str),
            filtro("categoria", "`recurso`, `avatar`, `insignia` o `curso_100`.", tipo=str),
            filtro("estado", "Estado de validación de las señas: `pendiente`, `aprobada` o `rechazada`. "
                   "Las señas sin aprobar solo las ven el Interprete, el Validador y el Administrador.", tipo=str),
            filtro("page", "Página (50 por página). Sin `page` devuelve la lista completa sin paginar."),
        ],
        responses=respuestas(
            ok(RecursoVisualSerializer(many=True), [EJEMPLO_RECURSO]),
            error_401(),
        ),
    ),
    "retrieve": extend_schema(
        tags=[ETIQUETA_PANEL], summary="Ver recurso",
        description="Detalle de un recurso. Cualquier usuario autenticado (sin rol de contenido, solo avatares).",
        parameters=[param_id("el recurso")],
        responses=respuestas(ok(RecursoVisualSerializer, EJEMPLO_RECURSO), error_401(), error_404()),
    ),
    "destroy": extend_schema(
        tags=[ETIQUETA_PANEL], summary="Eliminar recurso",
        description="Elimina el recurso y su archivo. Si está en uso (curso, palabra, pregunta o "
        "avatar de un perfil) responde 409. " + ROLES_BIBLIOTECA_ESCRITURA,
        parameters=[param_id("el recurso")],
        responses=respuestas(
            sin_contenido("Eliminado."), error_401(), error_403(), error_404(),
            {409: OpenApiResponse(
                ErrorDetalleSerializer, description="El recurso está en uso.",
                examples=[OpenApiExample(
                    "En uso", value={"detail": "No se puede borrar: el recurso está usado en contenido."},
                    response_only=True, status_codes=["409"],
                )],
            )},
        ),
    ),
})
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
        queryset = super().get_queryset().select_related("subido_por").prefetch_related("revisiones")
        busqueda = self.request.query_params.get("q", "").strip()
        extension = self.request.query_params.get("extension", "").lower()
        categoria = self.request.query_params.get("categoria", "").lower()
        estado = self.request.query_params.get("estado", "").lower()
        usuario = self.request.user
        puede_ver_todo = tiene_rol(
            usuario, ROL_ADMINISTRADOR, ROL_CREADOR, ROL_PROFESOR, ROL_INTERPRETE, ROL_VALIDADOR
        )
        if not puede_ver_todo:
            queryset = queryset.filter(categoria=RecursoVisual.Categoria.AVATAR)
        # Las senas sin aprobar solo las ven quien las sube, quien las revisa y el
        # Administrador: al Profesor y al CreadorDeCursos no les llegan.
        if not tiene_rol(usuario, ROL_INTERPRETE, ROL_VALIDADOR, ROL_ADMINISTRADOR):
            queryset = queryset.exclude(
                Q(categoria=RecursoVisual.Categoria.RECURSO, archivo__iendswith=".gif")
                & ~Q(estado_validacion=validacion.APROBADA)
            )
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        if estado:
            queryset = queryset.filter(estado_validacion=estado)
        if busqueda:
            queryset = queryset.filter(nombre__icontains=busqueda)
        if extension:
            queryset = queryset.filter(archivo__iendswith=f".{extension}")
        return queryset

    def perform_create(self, serializer):
        datos = serializer.validated_data
        serializer.save(
            subido_por=self.request.user,
            estado_validacion=validacion.estado_inicial(
                datos.get("categoria", RecursoVisual.Categoria.RECURSO), datos["archivo"].name
            ),
        )

    def perform_update(self, serializer):
        """Si se reemplaza el archivo de una sena, vuelve a revision del Validador."""
        recurso = serializer.save()
        if "archivo" in serializer.validated_data and recurso.es_sena:
            validacion.volver_a_revision(recurso, self.request.user)

    @extend_schema(
        tags=[ETIQUETA_PANEL],
        summary="Aprobar o rechazar una seña",
        description="El Validador revisa un gif de seña de la biblioteca. `decision` es `aprobar` o "
        "`rechazar`; al rechazar, `comentario` es obligatorio (máximo "
        f"{MAX_COMENTARIO_VALIDACION} caracteres). Queda en el historial de la seña. "
        "Rol: **Validador** (solo él; ni el Administrador puede).",
        parameters=[param_id("el recurso")],
        request=inline_serializer("DecisionSena", {
            "decision": serializers.ChoiceField(choices=["aprobar", "rechazar"]),
            "comentario": serializers.CharField(required=False, allow_blank=True),
        }),
        responses=respuestas(
            ok(RecursoVisualSerializer, {**EJEMPLO_RECURSO_SENA, "estado_validacion": "rechazada",
                                          "comentario_validacion": "La mano debe quedar a la altura del pecho."}),
            error_400({"detail": "Para rechazar una seña escribe un comentario."}, detalle=True,
                      descripcion="Decisión inválida, falta el comentario al rechazar o el recurso no es una seña."),
            error_401(),
            error_403(descripcion="Solo el Validador puede aprobar o rechazar señas."),
            error_404(),
        ),
    )
    @action(detail=True, methods=["post"], permission_classes=[EsValidador])
    def validar(self, request, pk=None):
        """POST /api/panel/recursos/<pk>/validar/ {"decision": "aprobar"|"rechazar", "comentario"}"""
        recurso = self.get_object()
        if not recurso.es_sena:
            return Response(
                {"detail": "Solo los gifs de señas de la biblioteca pasan por validación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        decision = str(request.data.get("decision", "")).strip().lower()
        comentario = str(request.data.get("comentario", "") or "").strip()
        if decision not in ("aprobar", "rechazar"):
            return Response(
                {"detail": "La decisión debe ser 'aprobar' o 'rechazar'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if decision == "rechazar" and not comentario:
            return Response(
                {"detail": "Para rechazar una seña escribe un comentario."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(comentario) > MAX_COMENTARIO_VALIDACION:
            return Response(
                {"detail": f"El comentario admite como máximo {MAX_COMENTARIO_VALIDACION} caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        validacion.decidir(recurso, decision == "aprobar", comentario, request.user)
        recurso = self.get_queryset().get(pk=recurso.pk)
        return Response(RecursoVisualSerializer(recurso).data)

    @extend_schema(
        tags=[ETIQUETA_PANEL],
        summary="Historial de una seña",
        description="Decisiones del Validador (con su comentario) y reemplazos del archivo, del más "
        "reciente al más antiguo. Roles: **Validador**, **Interprete** o **Administrador**.",
        parameters=[param_id("el recurso")],
        responses=respuestas(
            ok(RevisionSenaSerializer(many=True), [EJEMPLO_REVISION]),
            error_401(),
            error_403(descripcion="El rol no revisa ni sube señas."),
            error_404(),
        ),
    )
    @action(detail=True, methods=["get"], permission_classes=[PUEDE_VER_REVISIONES])
    def revisiones(self, request, pk=None):
        """GET /api/panel/recursos/<pk>/revisiones/"""
        recurso = self.get_object()
        return Response(RevisionSenaSerializer(recurso.revisiones.select_related("usuario"), many=True).data)

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


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Resumen del panel",
    description="Cifras generales para el tablero del panel. " + ROLES_CONTENIDO.replace(" (solo en los cursos que él creó)", ""),
    responses=respuestas(
        ok(inline_serializer("ResumenPanel", {
            "total_cursos": serializers.IntegerField(),
            "cursos_activos": serializers.IntegerField(),
            "total_preguntas": serializers.IntegerField(),
            "total_palabras": serializers.IntegerField(),
            "total_usuarios": serializers.IntegerField(),
        }), {"total_cursos": 2, "cursos_activos": 2, "total_preguntas": 15, "total_palabras": 15, "total_usuarios": 8}),
        error_401(),
        error_403(descripcion="El rol no administra contenido."),
    ),
)
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


@extend_schema(
    tags=[ETIQUETA_REPORTES],
    summary="Estrellas de los estudiantes",
    description="Todos los usuarios ordenados por estrellas (cursos completados), de mayor a menor. "
    "Roles: Profesor, CreadorDeCursos o Administrador.",
    responses=respuestas(
        ok(inline_serializer("EstrellasEstudiante", {
            "usuario": serializers.CharField(),
            "correo": serializers.EmailField(),
            "estrellas": serializers.IntegerField(),
        }, many=True), [
            {"usuario": "carlos", "correo": "carlos@correo.com", "estrellas": 5},
            {"usuario": "ana", "correo": "ana@correo.com", "estrellas": 2},
        ]),
        error_401(),
        error_403(descripcion="El rol no administra contenido."),
    ),
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


def _subir_sena(request, objeto, campo, titulo):
    """
    Guarda el gif adjunto (campo 'gif') en la biblioteca como sena pendiente del
    Validador y lo asigna a `objeto.campo`. Devuelve un Response de error, o None.
    """
    archivo = request.FILES.get("gif")
    if not archivo:
        return Response(
            {"detail": "Debes adjuntar el archivo en el campo 'gif'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        extension = validar_imagen(archivo, FORMATOS_GIF)
    except serializers.ValidationError as error:
        return Response({"detail": error.detail[0]}, status=status.HTTP_400_BAD_REQUEST)

    # El nombre del archivo lo pone ruta_recurso_visual (UUID); aqui solo se fija la extension.
    archivo.name = f"sena.{extension}"
    recurso = RecursoVisual.objects.create(
        nombre=f"Seña: {titulo}"[:120],
        archivo=archivo,
        categoria=RecursoVisual.Categoria.RECURSO,
        subido_por=request.user,
        estado_validacion=validacion.PENDIENTE,
    )
    setattr(objeto, campo, f"/{recurso.archivo.url.lstrip('/')}")
    objeto.save(update_fields=[campo])
    return None

@extend_schema(
    tags=[ETIQUETA_PANEL],
    summary="Subir el gif de una palabra",
    description="Guarda el gif en la biblioteca visual como seña **pendiente** del Validador y lo asigna "
    "a la palabra: los estudiantes no la ven en el diccionario hasta que se apruebe. "
    "Roles: **Interprete** (cualquier curso), **Profesor** (solo sus cursos), CreadorDeCursos o Administrador.",
    parameters=[param_id("la palabra")],
    request={"multipart/form-data": SubirGifSerializer},
    responses=respuestas(
        ok(PalabraPanelSerializer, {**EJEMPLO_PALABRA, "video_gif": "/media/biblioteca/7b1e0d.gif", "estado_sena": "pendiente"}),
        error_400({"detail": "Debes adjuntar el archivo en el campo 'gif'."}, detalle=True, descripcion="Falta el archivo."),
        error_401(),
        error_403(descripcion="El rol no sube gifs, o el curso es de otro profesor.", extra=MENSAJE_403_CURSO_AJENO),
        error_404("La palabra no existe."),
    ),
)
@api_view(["POST"])
@permission_classes([PUEDE_SUBIR_GIF])
def subir_gif_palabra(request, pk):
    """POST /api/panel/diccionario/<pk>/gif/ -> sube el gif de una palabra."""
    palabra = get_object_or_404(PalabraDiccionario, pk=pk)
    # El Interprete sube gifs a cualquier curso; un Profesor solo a los suyos.
    if not tiene_rol(request.user, ROL_INTERPRETE):
        exigir_curso_editable(request.user, palabra.curso)
    error = _subir_sena(request, palabra, "video_gif", palabra.titulo)
    if error:
        return error
    return Response(PalabraPanelSerializer(palabra).data)


@extend_schema(
    tags=[ETIQUETA_PANEL],
    summary="Subir el gif de una pregunta",
    description="Guarda el gif en la biblioteca visual como seña **pendiente** del Validador y lo asigna "
    "a la pregunta. "
    "Roles: **Interprete** (cualquier curso), **Profesor** (solo sus cursos), CreadorDeCursos o Administrador.",
    parameters=[param_id("la pregunta")],
    request={"multipart/form-data": SubirGifSerializer},
    responses=respuestas(
        ok(PreguntaPanelSerializer, {**EJEMPLO_PREGUNTA_PANEL, "video": "/media/biblioteca/7b1e0d.gif", "estado_sena": "pendiente"}),
        error_400({"detail": "Debes adjuntar el archivo en el campo 'gif'."}, detalle=True, descripcion="Falta el archivo."),
        error_401(),
        error_403(descripcion="El rol no sube gifs, o el curso es de otro profesor.", extra=MENSAJE_403_CURSO_AJENO),
        error_404("La pregunta no existe."),
    ),
)
@api_view(["POST"])
@permission_classes([PUEDE_SUBIR_GIF])
def subir_gif_pregunta(request, pk):
    """POST /api/panel/preguntas/<pk>/gif/ -> sube el gif de una pregunta."""
    pregunta = get_object_or_404(Pregunta, pk=pk)
    # El Interprete sube gifs a cualquier curso; un Profesor solo a los suyos.
    if not tiene_rol(request.user, ROL_INTERPRETE):
        exigir_curso_editable(request.user, pregunta.curso)
    error = _subir_sena(request, pregunta, "video", pregunta.texto)
    if error:
        return error
    return Response(PreguntaPanelSerializer(pregunta).data)


@extend_schema(
    tags=[ETIQUETA_PANEL],
    summary="Subir una imagen de uso puntual",
    description="Guarda la imagen en `media/contenido/` **sin** registrarla en la biblioteca. "
    "Máximo 10 MB. Roles: Interprete, Profesor, CreadorDeCursos o Administrador.",
    request={"multipart/form-data": inline_serializer(
        "SubirArchivoContenido", {"archivo": serializers.ImageField()}
    )},
    responses=respuestas(
        ok(inline_serializer("ArchivoSubido", {"archivo_url": serializers.CharField()}),
           {"archivo_url": "/media/contenido/7b1e0c.png"}, codigo=201, descripcion="Archivo guardado."),
        error_400({"detail": "Formato de imagen no permitido."}, detalle=True,
                  descripcion="Falta el archivo, el formato no es una imagen permitida o supera 10 MB."),
        error_401(),
        error_403(descripcion="El rol no puede subir archivos de contenido."),
    ),
)
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
    try:
        extension = validar_imagen(archivo)
    except serializers.ValidationError as error:
        return Response({"detail": error.detail[0]}, status=status.HTTP_400_BAD_REQUEST)

    ruta = default_storage.save(f"contenido/{nombre_seguro(extension)}", archivo)
    url = f"/{default_storage.url(ruta).lstrip('/')}"
    return Response({"archivo_url": url}, status=status.HTTP_201_CREATED)
