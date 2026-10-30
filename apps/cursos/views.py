import random

from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.models import PerfilUsuario

from .models import (
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    Pregunta,
    ProgresoUsuario,
)
from .serializers import (
    CursoSerializer,
    IntentoSerializer,
    PalabraDiccionarioSerializer,
    ProgresoSerializer,
)


# ==========================================================
# CATALOGO PUBLICO
# ==========================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def lista_cursos(request):
    """GET /api/cursos/ -> catalogo visible sin iniciar sesion."""
    cursos = Curso.objects.filter(activo=True)
    return Response(CursoSerializer(cursos, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def detalle_curso(request, slug):
    """GET /api/cursos/<slug>/"""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    return Response(CursoSerializer(curso).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def diccionario_curso(request, slug):
    """GET /api/cursos/<slug>/diccionario/"""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    palabras = curso.diccionario.all()
    return Response(
        {
            "curso": CursoSerializer(curso).data,
            "palabras": PalabraDiccionarioSerializer(palabras, many=True).data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mi_progreso(request):
    """GET /api/progreso/ -> progreso del usuario en todos los cursos."""
    progresos = ProgresoUsuario.objects.filter(usuario=request.user).select_related(
        "curso", "curso__insignia_100"
    )
    return Response(ProgresoSerializer(progresos, many=True).data)


# ==========================================================
# EVALUACION
# ==========================================================
# Reglas heredadas del monolito:
#   - Las preguntas se presentan en orden aleatorio.
#   - Solo se avanza a la siguiente pregunta cuando se acierta.
#   - Cada intento fallido suma un error.
#   - Un acierto solo puntua si esa pregunta no se habia fallado antes.

def _intento_activo(user, curso):
    intento = IntentoEvaluacion.objects.filter(
        usuario=user, curso=curso, finalizado=False
    ).first()
    if intento is None:
        return None
    # Si se borraron preguntas del curso despues de iniciar el intento, este ya
    # no se puede continuar: se descarta para que el usuario empiece de nuevo.
    existentes = set(
        Pregunta.objects.filter(curso=curso, id__in=intento.orden).values_list(
            "id", flat=True
        )
    )
    if not intento.orden or any(
        pregunta_id not in existentes for pregunta_id in intento.orden
    ):
        intento.delete()
        return None
    return intento


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def iniciar_evaluacion(request, slug):
    """POST /api/cursos/<slug>/evaluacion/iniciar/ -> crea un intento nuevo."""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)

    ids = list(
        Pregunta.objects.filter(curso=curso)
        .exclude(opciones__isnull=True)
        .distinct()
        .values_list("id", flat=True)
    )
    if not ids:
        return Response(
            {"detail": "No hay preguntas registradas para este curso."},
            status=status.HTTP_404_NOT_FOUND,
        )

    random.shuffle(ids)
    if curso.preguntas_por_evaluacion:
        ids = ids[: curso.preguntas_por_evaluacion]

    # Un intento abierto por usuario y curso: el anterior se descarta.
    IntentoEvaluacion.objects.filter(
        usuario=request.user, curso=curso, finalizado=False
    ).delete()

    intento = IntentoEvaluacion.objects.create(
        usuario=request.user, curso=curso, orden=ids
    )
    return Response(
        IntentoSerializer(intento).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def evaluacion_actual(request, slug):
    """GET /api/cursos/<slug>/evaluacion/actual/ -> pregunta en curso."""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    intento = _intento_activo(request.user, curso)
    if intento is None:
        return Response(
            {"detail": "No hay una evaluacion en curso. Inicia una nueva."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(IntentoSerializer(intento).data)


@transaction.atomic
def _cerrar_intento(intento):
    """Consolida el intento en ProgresoUsuario y otorga estrellas."""
    intento.finalizado = True
    intento.save()

    antiguos = list(
        IntentoEvaluacion.objects.filter(
            usuario=intento.usuario, curso=intento.curso, finalizado=True
        )
        .order_by("-fecha_inicio", "-id")
        .values_list("id", flat=True)[5:]
    )
    if antiguos:
        IntentoEvaluacion.objects.filter(id__in=antiguos).delete()

    progreso, _ = ProgresoUsuario.objects.get_or_create(
        usuario=intento.usuario, curso=intento.curso
    )
    progreso.aciertos = intento.aciertos
    progreso.errores = intento.errores
    progreso.completado = True
    insignia_100_nueva = (
        intento.total_preguntas > 0
        and intento.aciertos == intento.total_preguntas
        and not progreso.insignia_100_ganada
    )
    if intento.total_preguntas > 0 and intento.aciertos == intento.total_preguntas:
        progreso.insignia_100_ganada = True
    progreso.save()

    perfil, _ = PerfilUsuario.objects.get_or_create(user=intento.usuario)
    perfil.estrellas = (
        ProgresoUsuario.objects.filter(
            usuario=intento.usuario, completado=True
        ).count()
    )
    perfil.save()
    return progreso, insignia_100_nueva


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def responder_evaluacion(request, slug):
    """
    POST /api/cursos/<slug>/evaluacion/responder/

    Cuerpo: {"opcion_id": <int>}
    """
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    intento = _intento_activo(request.user, curso)
    if intento is None:
        return Response(
            {"detail": "No hay una evaluacion en curso."},
            status=status.HTTP_404_NOT_FOUND,
        )

    pregunta_id = intento.pregunta_actual_id()
    if pregunta_id is None:
        _, insignia_100_nueva = _cerrar_intento(intento)
        return Response(
            {"finalizado": True, "resultado": _resultado(intento, insignia_100_nueva)},
        )

    opcion_id = request.data.get("opcion_id")
    opcion = OpcionPregunta.objects.filter(
        pk=opcion_id, pregunta_id=pregunta_id
    ).first()
    if opcion is None:
        return Response(
            {"detail": "La opcion enviada no pertenece a la pregunta actual."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    falladas = set(intento.falladas or [])
    respuestas = intento.respuestas or {}
    respuestas.setdefault(str(pregunta_id), []).append(opcion.id)
    intento.respuestas = respuestas

    if opcion.es_correcta:
        if pregunta_id not in falladas:
            intento.aciertos += 1
        intento.indice_actual += 1
        finalizado = intento.indice_actual >= intento.total_preguntas
        intento.save()

        if finalizado:
            _, insignia_100_nueva = _cerrar_intento(intento)
            return Response(
                {
                    "correcta": True,
                    "mensaje": "Correcto.",
                    "finalizado": True,
                    "resultado": _resultado(intento, insignia_100_nueva),
                }
            )

        return Response(
            {
                "correcta": True,
                "mensaje": "Correcto.",
                "finalizado": False,
                "siguiente": IntentoSerializer(intento).data,
            }
        )

    intento.errores += 1
    falladas.add(pregunta_id)
    intento.falladas = sorted(falladas)
    intento.save()

    return Response(
        {
            "correcta": False,
            "mensaje": "Incorrecto, intenta de nuevo.",
            "finalizado": False,
            "estado": IntentoSerializer(intento).data,
        }
    )


def _resultado(intento, insignia_100_nueva=False):
    progreso = ProgresoUsuario.objects.filter(
        usuario=intento.usuario, curso=intento.curso
    ).select_related("curso__insignia_100").first()
    recurso = progreso.curso.insignia_100 if progreso and progreso.insignia_100_ganada else None
    imagen = f"/{recurso.archivo.url.lstrip('/')}" if recurso and recurso.archivo else ""
    falladas = set(intento.falladas or [])
    respuestas = intento.respuestas or {}
    preguntas = Pregunta.objects.prefetch_related("opciones").in_bulk(
        intento.orden or []
    )
    detalle_preguntas = [
        {
            "etiqueta": str(indice + 1),
            "texto": preguntas[pregunta_id].texto,
            "video": preguntas[pregunta_id].video or "",
            "acierto": pregunta_id not in falladas,
            "detalle": "Correcta" if pregunta_id not in falladas else "Incorrecta",
            # El intento ya esta cerrado: se puede mostrar cual era la correcta.
            "opciones": [
                {"id": opcion.id, "texto": opcion.texto, "es_correcta": opcion.es_correcta}
                for opcion in preguntas[pregunta_id].opciones.all()
            ],
            "elegidas": respuestas.get(str(pregunta_id), []),
        }
        for indice, pregunta_id in enumerate(intento.orden or [])
        if pregunta_id in preguntas
    ]
    return {
        "curso": intento.curso.nombre,
        "curso_titulo": intento.curso.titulo,
        "aciertos": intento.aciertos,
        "errores": intento.errores,
        "total": intento.total_preguntas,
        "porcentaje": round(intento.aciertos * 100 / intento.total_preguntas) if intento.total_preguntas else 0,
        "detalle_preguntas": detalle_preguntas,
        "mensaje": intento.mensaje_retroalimentacion(),
        "insignia_100_ganada": bool(progreso and progreso.insignia_100_ganada),
        "insignia_100_nueva": bool(insignia_100_nueva and imagen),
        "insignia_100": {"nombre": "Curso 100%", "imagen": imagen} if imagen else None,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def resultado_evaluacion(request, slug):
    """GET /api/cursos/<slug>/evaluacion/resultado/ -> ultimo intento cerrado."""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    intento = (
        IntentoEvaluacion.objects.filter(
            usuario=request.user, curso=curso, finalizado=True
        )
        .order_by("-fecha_actualizacion")
        .first()
    )
    if intento is None:
        return Response(
            {"detail": "Todavia no has terminado una evaluacion de este curso."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(_resultado(intento))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def historial_evaluacion(request, slug):
    """GET /cursos/<slug>/evaluacion/historial/ -> intentos finalizados del usuario."""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    intentos = IntentoEvaluacion.objects.filter(
        usuario=request.user, curso=curso, finalizado=True
    ).order_by("-fecha_inicio", "-id")[:5]
    return Response([
        {
            "id": intento.id,
            "aciertos": intento.aciertos,
            "errores": intento.errores,
            "total": intento.total_preguntas,
            "fecha": intento.fecha_inicio,
        }
        for intento in reversed(list(intentos))
    ])
