"""
Validacion de senas: el Interprete las sube, el Validador las aprueba o rechaza.

Una "sena" es un gif de la categoria "recurso" de la biblioteca visual
(RecursoVisual.es_sena). Reglas:

- Una sena nueva, o una cuyo archivo se reemplaza, queda "pendiente".
- Solo el rol Validador decide (aprobar, o rechazar con comentario). Cada
  decision y cada reemplazo quedan en RevisionSena (el historial).
- El Profesor solo ve y solo puede usar senas aprobadas (buscador de la
  biblioteca, diccionario y preguntas).
- Los estudiantes no ven en el diccionario las palabras cuya sena no esta
  aprobada.
- Lo que existia antes de este rol quedo "aprobada" (valor por defecto de la
  columna). Los demas recursos (imagenes, avatares, insignias) no se validan.
"""

from pathlib import PurePosixPath
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from .models import RecursoVisual, RevisionSena

APROBADA = RecursoVisual.EstadoValidacion.APROBADA
PENDIENTE = RecursoVisual.EstadoValidacion.PENDIENTE
RECHAZADA = RecursoVisual.EstadoValidacion.RECHAZADA

MENSAJE_SENA_NO_APROBADA = "Esa seña todavía no está aprobada por el Validador."
MENSAJE_GIF_FUERA_DE_BIBLIOTECA = (
    "Elige la seña en la biblioteca visual: solo se pueden usar señas aprobadas por el Validador."
)


def nombre_en_media(valor):
    """'/media/biblioteca/x.gif' (o la URL completa) -> 'biblioteca/x.gif'; None si no es de media/."""
    if not valor:
        return None
    ruta = urlparse(str(valor)).path
    prefijo = "/" + settings.MEDIA_URL.strip("/") + "/"
    if not ruta.startswith(prefijo):
        return None
    return ruta[len(prefijo):]


def _es_gif(nombre):
    return PurePosixPath(nombre or "").suffix.lower() == ".gif"


def es_sena(categoria, nombre_archivo):
    """Igual que RecursoVisual.es_sena, antes de guardar el recurso."""
    return categoria == RecursoVisual.Categoria.RECURSO and _es_gif(nombre_archivo)


def estado_inicial(categoria, nombre_archivo):
    """Una sena recien subida espera al Validador; cualquier otro recurso no."""
    return PENDIENTE if es_sena(categoria, nombre_archivo) else APROBADA


def senas_no_aprobadas():
    """{'biblioteca/x.gif': 'pendiente' | 'rechazada'} de las senas sin aprobar."""
    return dict(
        RecursoVisual.objects.filter(
            categoria=RecursoVisual.Categoria.RECURSO, archivo__iendswith=".gif"
        )
        .exclude(estado_validacion=APROBADA)
        .values_list("archivo", "estado_validacion")
    )


def estado_de(valor, no_aprobadas):
    """Estado de la sena que usa una palabra o pregunta ('aprobada' si no es de la biblioteca)."""
    return no_aprobadas.get(nombre_en_media(valor), APROBADA)


def palabras_visibles(queryset):
    """Diccionario de los estudiantes: sin las palabras cuya sena no esta aprobada."""
    filtro = Q()
    for nombre in senas_no_aprobadas():
        filtro |= Q(video_gif__endswith=f"/{nombre}")
    return queryset.exclude(filtro) if filtro else queryset


def exigir_sena_aprobada(valor):
    """
    Para el panel: el gif NUEVO de una palabra o pregunta debe ser una sena
    aprobada de la biblioteca. Se permiten el campo vacio, las imagenes que no
    son gif y los gifs de assets/ del frontend (versionados en git, ya revisados).
    """
    nombre = nombre_en_media(valor)
    if nombre is None or not _es_gif(nombre):
        return
    recurso = RecursoVisual.objects.filter(archivo=nombre).first()
    if recurso is None:
        raise serializers.ValidationError(MENSAJE_GIF_FUERA_DE_BIBLIOTECA)
    if recurso.es_sena and recurso.estado_validacion != APROBADA:
        raise serializers.ValidationError(MENSAJE_SENA_NO_APROBADA)


# En las dos funciones de abajo el ORDEN importa: primero la revision y despues
# el estado. En MySQL el trigger recurso_estado_con_historial (migracion 0014)
# rechaza un cambio de estado que no coincida con la ultima revision.


@transaction.atomic
def decidir(recurso, aprobar, comentario, validador):
    """Aprueba o rechaza una sena y lo deja en el historial."""
    RevisionSena.objects.create(
        recurso=recurso,
        accion=RevisionSena.Accion.APROBADA if aprobar else RevisionSena.Accion.RECHAZADA,
        comentario=comentario,
        usuario=validador,
        archivo=recurso.archivo.name,
    )
    recurso.estado_validacion = APROBADA if aprobar else RECHAZADA
    recurso.save(update_fields=["estado_validacion"])


@transaction.atomic
def volver_a_revision(recurso, usuario):
    """Se reemplazo el archivo de una sena: vuelve a pendiente y queda en el historial."""
    RevisionSena.objects.create(
        recurso=recurso,
        accion=RevisionSena.Accion.REENVIADA,
        usuario=usuario,
        archivo=recurso.archivo.name,
    )
    recurso.estado_validacion = PENDIENTE
    recurso.save(update_fields=["estado_validacion"])


def ultimo_comentario(recurso):
    """Comentario de la ultima decision del Validador ('' si no hay)."""
    for revision in recurso.revisiones.all():
        if revision.accion != RevisionSena.Accion.REENVIADA:
            return revision.comentario
    return ""
