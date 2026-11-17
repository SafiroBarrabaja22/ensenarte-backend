"""
Datos de cada reporte. Devuelven un Reporte (modelo.py) listo para dibujar.
"""

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.cursos import procedimientos
from apps.cursos.models import Curso, IntentoEvaluacion, ProgresoUsuario

from .modelo import (
    DECIMAL,
    ENTERO,
    FECHA,
    PORCENTAJE,
    SI_NO,
    TEXTO,
    Reporte,
    Tabla,
    fecha_larga,
    tabla_resumen,
)


def _nombre(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else "-"


def _cantidad(numero, singular, plural):
    return f"{numero} {singular if numero == 1 else plural}"


def _sello():
    return timezone.localdate().strftime("%Y%m%d")


# ------------------------------------------------------------------ 1. Constancia


def constancia(usuario, slug):
    """Constancia de curso completado del propio usuario."""
    curso = get_object_or_404(Curso.objects.select_related("creado_por"), nombre=slug)
    progreso = ProgresoUsuario.objects.filter(usuario=usuario, curso=curso, completado=True).first()
    if progreso is None:
        raise NotFound("Todavía no has completado este curso.")

    if progreso.aciertos or progreso.errores:
        resultado = (
            f"{_cantidad(progreso.aciertos, 'acierto', 'aciertos')} y "
            f"{_cantidad(progreso.errores, 'error', 'errores')} en su última evaluación"
        )
    else:
        resultado = "Evaluación con cámara aprobada"

    pares = [
        ("Estudiante", _nombre(usuario)),
        ("Curso", curso.titulo),
        ("Fecha de finalización", fecha_larga(progreso.fecha_ultima_actividad)),
        ("Resultado", resultado),
        ("Insignia Curso 100 %", "Sí" if progreso.insignia_100_ganada else "No"),
        ("Profesor del curso", _nombre(curso.creado_por)),
    ]
    return Reporte(
        titulo="Constancia de curso completado",
        subtitulo=f"{curso.titulo} · {_nombre(usuario)}",
        nombre_archivo=f"constancia-{curso.nombre}",
        tablas=[tabla_resumen(pares, hoja="Constancia", titulo="Detalle")],
        horizontal=True,
        certificado={
            "estudiante": _nombre(usuario),
            "curso": curso.titulo,
            "fecha": fecha_larga(progreso.fecha_ultima_actividad),
            "insignia_100": progreso.insignia_100_ganada,
        },
    )


# ------------------------------------------------------------------ 2. Progreso del curso


def progreso_curso(curso):
    """Progreso de cada estudiante con actividad en el curso."""
    filas = []
    progresos = (
        ProgresoUsuario.objects.filter(curso=curso)
        .select_related("usuario")
        .order_by("-completado", "usuario__username")
    )
    con_progreso = set()
    for progreso in progresos:
        con_progreso.add(progreso.usuario_id)
        filas.append([
            progreso.usuario.username, progreso.usuario.email,
            "Completado" if progreso.completado else "En progreso",
            progreso.aciertos, progreso.errores, progreso.insignia_100_ganada,
            progreso.fecha_ultima_actividad,
        ])
    # Estudiantes con una evaluacion abierta que aun no tienen progreso.
    abiertos = (
        IntentoEvaluacion.objects.filter(curso=curso, finalizado=False)
        .exclude(usuario_id__in=con_progreso)
        .select_related("usuario")
        .order_by("usuario__username")
    )
    for intento in abiertos:
        filas.append([
            intento.usuario.username, intento.usuario.email, "Evaluación en curso",
            intento.aciertos, intento.errores, False, intento.fecha_actualizacion,
        ])

    completaron = sum(1 for fila in filas if fila[2] == "Completado")
    aciertos_completados = [fila[3] for fila in filas if fila[2] == "Completado"]
    promedio = sum(aciertos_completados) / len(aciertos_completados) if aciertos_completados else 0
    pares = [
        ("Curso", f"{curso.titulo} ({curso.nombre})"),
        ("Profesor", _nombre(curso.creado_por)),
        ("Estudiantes con actividad", str(len(filas))),
        ("Completaron el curso", str(completaron)),
        ("Tasa de finalización", f"{(completaron * 100 / len(filas)) if filas else 0:.1f} %".replace(".", ",")),
        ("Promedio de aciertos de quienes completaron", f"{promedio:.2f}".replace(".", ",")),
    ]
    detalle = Tabla(
        hoja="Estudiantes", titulo="Estudiantes",
        encabezados=["Estudiante", "Correo", "Estado", "Aciertos", "Errores", "Insignia 100 %", "Última actividad"],
        filas=filas,
        formatos=[TEXTO, TEXTO, TEXTO, ENTERO, ENTERO, SI_NO, FECHA],
        anchos=[20, 30, 20, 10, 10, 14, 18],
        vacio="Ningún estudiante ha trabajado todavía en este curso.",
    )
    return Reporte(
        titulo="Progreso de los estudiantes",
        subtitulo=curso.titulo,
        nombre_archivo=f"progreso-{curso.nombre}-{_sello()}",
        tablas=[tabla_resumen(pares), detalle],
        horizontal=True,
    )


# ------------------------------------------------------------------ 3. Plataforma


def plataforma(limite_ranking=10):
    """
    Estadisticas generales. Las cifras salen de los procedimientos almacenados
    estadisticas_curso y ranking_estudiantes (migracion cursos/0011), no del ORM.
    Fuera de MySQL lanza procedimientos.ProcedimientoNoDisponible.
    """
    umbral = settings.EVALUACION_CAMARA_UMBRAL_APROBACION
    cursos = list(Curso.objects.order_by("titulo").values("id", "titulo", "nombre", "activo"))
    filas_cursos = []
    for curso in cursos:
        datos = procedimientos.estadisticas_curso(curso["id"], umbral=umbral)
        filas_cursos.append([
            curso["titulo"], curso["nombre"], curso["activo"],
            datos["intentos_finalizados"], datos["promedio_aciertos"], datos["promedio_errores"],
            datos["estudiantes_completaron"], datos["tasa_aprobacion"],
        ])
    ranking = procedimientos.ranking_estudiantes(limite=limite_ranking)

    pares = [
        ("Cursos", f"{len(cursos)} ({sum(1 for c in cursos if c['activo'])} activos)"),
        ("Intentos de evaluación terminados", str(sum(f[3] for f in filas_cursos))),
        ("Cursos completados (todos los estudiantes)", str(sum(f[6] for f in filas_cursos))),
        ("Umbral de aprobación", f"{umbral} %"),
        ("Fuente de las cifras", "Procedimientos almacenados estadisticas_curso y ranking_estudiantes"),
    ]
    tabla_cursos = Tabla(
        hoja="Cursos", titulo="Estadísticas por curso",
        encabezados=["Curso", "Slug", "Activo", "Intentos terminados", "Promedio de aciertos",
                     "Promedio de errores", "Completaron", "Tasa de aprobación"],
        filas=filas_cursos,
        formatos=[TEXTO, TEXTO, SI_NO, ENTERO, DECIMAL, DECIMAL, ENTERO, PORCENTAJE],
        anchos=[24, 16, 9, 12, 12, 12, 12, 13],
        vacio="No hay cursos registrados.",
    )
    tabla_ranking = Tabla(
        hoja="Ranking", titulo=f"Ranking de estudiantes (los {limite_ranking} primeros)",
        encabezados=["Puesto", "Estudiante", "Cursos completados", "Aciertos acumulados"],
        filas=[[n, fila["usuario"], fila["cursos_completados"], fila["aciertos"]] for n, fila in enumerate(ranking, start=1)],
        formatos=[ENTERO, TEXTO, ENTERO, ENTERO],
        anchos=[9, 30, 18, 20],
        vacio="Todavía no hay estudiantes con cursos completados.",
    )
    return Reporte(
        titulo="Estadísticas de la plataforma",
        subtitulo="Resumen general de cursos, evaluaciones y estudiantes",
        nombre_archivo=f"estadisticas-plataforma-{_sello()}",
        tablas=[tabla_resumen(pares), tabla_cursos, tabla_ranking],
        horizontal=True,
    )
