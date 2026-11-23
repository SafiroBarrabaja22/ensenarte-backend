import random

from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.correos.servicio import al_confirmar, avisar_curso_completado, enviar_resultados
from apps.usuarios.models import PerfilUsuario
from config.openapi import (
    EJEMPLO_CURSO,
    EJEMPLO_INTENTO,
    EJEMPLO_RESULTADO,
    ETIQUETA_CURSOS,
    ETIQUETA_EVALUACION,
    MENSAJE_403,
    PARAM_SLUG,
    error_400,
    error_401,
    error_403,
    error_404,
    ok,
    respuestas,
)

from .models import (
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    Pregunta,
    ProgresoUsuario,
)
from .permissions import PUEDE_APRENDER
from .validacion import palabras_visibles
from .serializers import (
    CursoSerializer,
    InsigniaSerializer,
    IntentoSerializer,
    PalabraDiccionarioSerializer,
    ProgresoSerializer,
)


# ==========================================================
# ESQUEMAS DE RESPUESTA (solo documentacion OpenAPI)
# ==========================================================

DiccionarioCursoSerializer = inline_serializer(
    "DiccionarioCurso",
    {"curso": CursoSerializer(), "palabras": PalabraDiccionarioSerializer(many=True)},
)

DetallePreguntaSerializer = inline_serializer(
    "DetallePreguntaResultado",
    {
        "etiqueta": serializers.CharField(),
        "texto": serializers.CharField(),
        "video": serializers.CharField(),
        "acierto": serializers.BooleanField(),
        "detalle": serializers.CharField(),
        "opciones": inline_serializer(
            "OpcionResultado",
            {"id": serializers.IntegerField(), "texto": serializers.CharField(), "es_correcta": serializers.BooleanField()},
            many=True,
        ),
        "elegidas": serializers.ListField(child=serializers.IntegerField()),
    },
    many=True,
)

class ResultadoEvaluacionSerializer(serializers.Serializer):
    """Esquema de `_resultado()`. Se usa solo y anidado en RespuestaEvaluacion."""

    curso = serializers.CharField()
    curso_titulo = serializers.CharField()
    aciertos = serializers.IntegerField()
    errores = serializers.IntegerField()
    total = serializers.IntegerField()
    porcentaje = serializers.IntegerField()
    detalle_preguntas = DetallePreguntaSerializer
    mensaje = serializers.CharField()
    insignia_100_ganada = serializers.BooleanField()
    insignia_100_nueva = serializers.BooleanField()
    insignia_100 = InsigniaSerializer(allow_null=True)

RespuestaEvaluacionSerializer = inline_serializer(
    "RespuestaEvaluacion",
    {
        "correcta": serializers.BooleanField(required=False),
        "mensaje": serializers.CharField(required=False),
        "finalizado": serializers.BooleanField(),
        "siguiente": IntentoSerializer(required=False, help_text="Si acertó y quedan preguntas."),
        "estado": IntentoSerializer(required=False, help_text="Si falló: la misma pregunta sigue activa."),
        "resultado": ResultadoEvaluacionSerializer(required=False, help_text="Si fue la última pregunta."),
    },
)

HistorialItemSerializer = inline_serializer(
    "IntentoHistorial",
    {
        "id": serializers.IntegerField(),
        "aciertos": serializers.IntegerField(),
        "errores": serializers.IntegerField(),
        "total": serializers.IntegerField(),
        "fecha": serializers.DateTimeField(),
    },
    many=True,
)

ROLES_APRENDIZAJE = "Cualquier rol (Estudiante, Profesor, Interprete, Validador, CreadorDeCursos, Administrador)."


# ==========================================================
# CATALOGO PUBLICO
# ==========================================================

@extend_schema(
    tags=[ETIQUETA_CURSOS],
    summary="Catálogo de cursos",
    auth=[],  # publico: sin candado en Swagger UI
    operation_id="cursos_listar",
    description="Cursos activos. Público, sin token.",
    responses=respuestas(ok(CursoSerializer(many=True), [EJEMPLO_CURSO])),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def lista_cursos(request):
    """GET /api/cursos/ -> catalogo visible sin iniciar sesion."""
    cursos = Curso.objects.filter(activo=True)
    return Response(CursoSerializer(cursos, many=True).data)


@extend_schema(
    tags=[ETIQUETA_CURSOS],
    summary="Detalle de un curso",
    auth=[],  # publico: sin candado en Swagger UI
    operation_id="cursos_detalle",
    description="Un curso activo por su slug. Público, sin token.",
    parameters=[PARAM_SLUG],
    responses=respuestas(ok(CursoSerializer, EJEMPLO_CURSO), error_404()),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def detalle_curso(request, slug):
    """GET /api/cursos/<slug>/"""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    return Response(CursoSerializer(curso).data)


@extend_schema(
    tags=[ETIQUETA_CURSOS],
    summary="Diccionario visual de un curso",
    description="Palabras del curso en el orden definido por el profesor, con imagen y gif. "
    "No incluye las palabras cuya seña todavía no aprueba el Validador. "
    + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    responses=respuestas(
        ok(DiccionarioCursoSerializer, {
            "curso": EJEMPLO_CURSO,
            "palabras": [{"id": 1, "titulo": "A", "imagen_frontal": "abecedario/a.png", "video_gif": "abecedario/a.gif"}],
        }),
        error_401(),
        error_403(detalle=MENSAJE_403, descripcion="El usuario no tiene ningún rol asignado."),
        error_404(),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
def diccionario_curso(request, slug):
    """GET /api/cursos/<slug>/diccionario/"""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    # Sin las palabras cuya seña aún no aprueba el Validador (apps/cursos/validacion.py).
    palabras = palabras_visibles(curso.diccionario.all())
    return Response(
        {
            "curso": CursoSerializer(curso).data,
            "palabras": PalabraDiccionarioSerializer(palabras, many=True).data,
        }
    )


@extend_schema(
    tags=[ETIQUETA_CURSOS],
    summary="Mi progreso",
    description="Resultado consolidado del usuario en cada curso que ha evaluado. " + ROLES_APRENDIZAJE,
    responses=respuestas(
        ok(ProgresoSerializer(many=True), [{
            "curso": "abecedario", "curso_titulo": "Abecedario",
            "curso_insignia": "/media/biblioteca/insignia.png", "curso_insignia_tipo": "curso_completado",
            "curso_insignia_nombre": "Curso completado", "insignia_100_ganada": False,
            "aciertos": 9, "errores": 1, "completado": True,
            "fecha_ultima_actividad": "2026-11-16T15:30:00-05:00",
        }]),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
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


@extend_schema(
    tags=[ETIQUETA_EVALUACION],
    summary="Iniciar evaluación",
    description="Crea un intento con las preguntas del curso en orden aleatorio (limitadas por "
    "`preguntas_por_evaluacion` si el curso lo define). Si había un intento abierto, se descarta. "
    "Devuelve la primera pregunta; las opciones **no** indican cuál es la correcta. " + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    request=None,
    responses=respuestas(
        ok(IntentoSerializer, EJEMPLO_INTENTO, codigo=201, descripcion="Intento creado."),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404(
            "El curso no existe, no está activo o no tiene preguntas con opciones.",
            detalle="No hay preguntas registradas para este curso.",
        ),
    ),
)
@api_view(["POST"])
@permission_classes([PUEDE_APRENDER])
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


@extend_schema(
    tags=[ETIQUETA_EVALUACION],
    summary="Pregunta actual",
    description="Estado del intento abierto y la pregunta que toca responder. " + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    responses=respuestas(
        ok(IntentoSerializer, EJEMPLO_INTENTO),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404("No hay un intento abierto en este curso.", detalle="No hay una evaluacion en curso. Inicia una nueva."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
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
    estaba_completado = progreso.completado
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
    if not estaba_completado:
        # Primera vez que completa el curso: avisar a su profesor (tras el commit).
        al_confirmar(avisar_curso_completado, intento.curso, intento.usuario)
    return progreso, insignia_100_nueva


def _finalizar(intento):
    """Cierra el intento, arma el resultado y programa el correo de resultados."""
    _, insignia_100_nueva = _cerrar_intento(intento)
    resultado = _resultado(intento, insignia_100_nueva)
    al_confirmar(enviar_resultados, intento.usuario, intento.curso, resultado)
    return resultado


@extend_schema(
    tags=[ETIQUETA_EVALUACION],
    summary="Responder la pregunta actual",
    description="Solo se avanza al acertar; cada fallo suma un error y un acierto solo puntúa si "
    "esa pregunta no se había fallado antes. Al responder la última, el intento se cierra, se "
    "actualiza el progreso y llega `resultado`. " + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    request=inline_serializer("ResponderEvaluacion", {"opcion_id": serializers.IntegerField(help_text="ID de la opción elegida.")}),
    responses=respuestas(
        ok(RespuestaEvaluacionSerializer, {
            "correcta": True, "mensaje": "Correcto.", "finalizado": False,
            "siguiente": {**EJEMPLO_INTENTO, "actual": 2, "aciertos": 1},
        }),
        error_400({"detail": "La opcion enviada no pertenece a la pregunta actual."}, detalle=True,
                  descripcion="La opción no existe o no es de la pregunta actual."),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404("No hay un intento abierto en este curso.", detalle="No hay una evaluacion en curso."),
    ),
)
@api_view(["POST"])
@permission_classes([PUEDE_APRENDER])
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
        return Response({"finalizado": True, "resultado": _finalizar(intento)})

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
            return Response(
                {
                    "correcta": True,
                    "mensaje": "Correcto.",
                    "finalizado": True,
                    "resultado": _finalizar(intento),
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


@extend_schema(
    tags=[ETIQUETA_EVALUACION],
    summary="Resultado del último intento",
    description="Resultado del último intento terminado, con el detalle de cada pregunta "
    "(ya se muestra cuál era la opción correcta). " + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    responses=respuestas(
        ok(ResultadoEvaluacionSerializer, EJEMPLO_RESULTADO),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404("El usuario aún no termina ninguna evaluación de este curso.",
                  detalle="Todavia no has terminado una evaluacion de este curso."),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
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


@extend_schema(
    tags=[ETIQUETA_EVALUACION],
    summary="Historial de intentos",
    description="Los últimos 5 intentos terminados del usuario en el curso, del más antiguo al "
    "más reciente. " + ROLES_APRENDIZAJE,
    parameters=[PARAM_SLUG],
    responses=respuestas(
        ok(HistorialItemSerializer, [{"id": 15, "aciertos": 9, "errores": 1, "total": 10, "fecha": "2026-11-16T15:30:00-05:00"}]),
        error_401(),
        error_403(descripcion="El usuario no tiene ningún rol asignado."),
        error_404(),
    ),
)
@api_view(["GET"])
@permission_classes([PUEDE_APRENDER])
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
