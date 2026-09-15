import random

from django.shortcuts import get_object_or_404
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
    progresos = ProgresoUsuario.objects.filter(usuario=request.user)
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
    return IntentoEvaluacion.objects.filter(
        usuario=user, curso=curso, finalizado=False
    ).first()


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


def _cerrar_intento(intento):
    """Consolida el intento en ProgresoUsuario y otorga estrellas."""
    intento.finalizado = True
    intento.save()

    progreso, _ = ProgresoUsuario.objects.get_or_create(
        usuario=intento.usuario, curso=intento.curso
    )
    progreso.aciertos = intento.aciertos
    progreso.errores = intento.errores
    progreso.completado = True
    progreso.save()

    perfil, _ = PerfilUsuario.objects.get_or_create(user=intento.usuario)
    perfil.estrellas = (
        ProgresoUsuario.objects.filter(
            usuario=intento.usuario, completado=True
        ).count()
    )
    perfil.save()
    return progreso


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
        _cerrar_intento(intento)
        return Response(
            {"finalizado": True, "resultado": _resultado(intento)},
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

    if opcion.es_correcta:
        if pregunta_id not in falladas:
            intento.aciertos += 1
        intento.indice_actual += 1
        finalizado = intento.indice_actual >= intento.total_preguntas
        intento.save()

        if finalizado:
            _cerrar_intento(intento)
            return Response(
                {
                    "correcta": True,
                    "mensaje": "Correcto.",
                    "finalizado": True,
                    "resultado": _resultado(intento),
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


def _resultado(intento):
    return {
        "curso": intento.curso.nombre,
        "curso_titulo": intento.curso.titulo,
        "aciertos": intento.aciertos,
        "errores": intento.errores,
        "mensaje": intento.mensaje_retroalimentacion(),
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
