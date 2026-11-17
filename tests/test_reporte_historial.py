"""
PDF del historial de intentos (apps/reportes/historial.py):
GET /api/reportes/historial/<slug>/?tipo=preguntas|camara
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cursos.models import IntentoEvaluacion
from apps.evaluacion_camara.models import EvaluacionCamara
from apps.reportes.historial import _redondear, sesiones_de

from .test_reportes import es_pdf_valido

pytestmark = pytest.mark.django_db

URL = "/api/reportes/historial/{}/"


def intento(usuario, curso, aciertos, total=10, dias_atras=0, finalizado=True):
    registro = IntentoEvaluacion.objects.create(
        usuario=usuario, curso=curso, orden=list(range(total)), finalizado=finalizado,
        aciertos=aciertos, errores=total - aciertos,
    )
    IntentoEvaluacion.objects.filter(pk=registro.pk).update(fecha_inicio=timezone.now() - timedelta(days=dias_atras))
    return registro


def sesion_camara(usuario, curso, correctas, total=27, dias_atras=0):
    registro = EvaluacionCamara.objects.create(
        usuario=usuario, curso=curso, total=total, correctas=correctas,
        porcentaje=correctas * 100 // total, aprobado=correctas * 100 >= 70 * total, umbral_aplicado=70,
    )
    EvaluacionCamara.objects.filter(pk=registro.pk).update(fecha=timezone.now() - timedelta(days=dias_atras))
    return registro


def nombre_esperado(curso, tipo):
    return f"historial-{curso.nombre}-{tipo}-{timezone.localdate():%Y%m%d}.pdf"


def test_pdf_del_historial_por_preguntas(como, estudiante, curso):
    for dias, aciertos in zip([8, 6, 4, 2, 0], [4, 6, 5, 8, 9]):
        intento(estudiante, curso, aciertos, dias_atras=dias)
    respuesta = como(estudiante).get(URL.format(curso.nombre))
    texto = es_pdf_valido(respuesta, nombre_esperado(curso, "preguntas"))
    for fragmento in ["Abecedario", "Evaluaci", "Tu progreso", "ltimos intentos", "Detalle de las sesiones",
                      "90%", "+10 puntos frente a tu sesi", "Hoy", "Intento 1", "estudiante"]:
        assert fragmento in texto, fragmento
    assert respuesta["Cache-Control"] == "no-store"


def test_pdf_del_historial_con_camara(como, estudiante, curso):
    for dias, correctas in zip([4, 2, 0], [12, 19, 22]):
        sesion_camara(estudiante, curso, correctas, dias_atras=dias)
    respuesta = como(estudiante).get(URL.format(curso.nombre), {"tipo": "camara"})
    texto = es_pdf_valido(respuesta, nombre_esperado(curso, "camara"))
    for fragmento in ["Tu progreso con c", "con c", "81%", "Correctas", "Umbral", "Aprobada"]:
        assert fragmento in texto, fragmento


def test_solo_las_ultimas_cinco_y_de_la_mas_antigua_a_la_mas_reciente(estudiante, curso):
    for dias, aciertos in zip([10, 8, 6, 4, 2, 0], [1, 2, 3, 4, 5, 6]):
        intento(estudiante, curso, aciertos, dias_atras=dias)
    intento(estudiante, curso, 10, finalizado=False)     # un intento abierto no cuenta
    assert [s.puntos for s in sesiones_de(estudiante, curso, "preguntas")] == [20, 30, 40, 50, 60]


def test_nunca_incluye_intentos_de_otro_usuario(como, estudiante, profesor, curso):
    intento(estudiante, curso, 3)
    intento(profesor, curso, 7)
    assert [s.puntos for s in sesiones_de(estudiante, curso, "preguntas")] == [30]
    texto = es_pdf_valido(como(estudiante).get(URL.format(curso.nombre)), nombre_esperado(curso, "preguntas"))
    assert "70%" not in texto


def test_el_puntaje_se_redondea_como_en_la_pagina(estudiante, curso):
    """Math.round de JavaScript: 2/8 = 25 %, 5/8 = 62,5 % -> 63 (no 62 como round() de Python)."""
    intento(estudiante, curso, 5, total=8)
    assert sesiones_de(estudiante, curso, "preguntas")[0].puntos == 63
    assert _redondear(62.5) == 63 and _redondear(0.5) == 1


def test_sin_intentos_genera_el_pdf_con_el_aviso(como, estudiante, curso):
    texto = es_pdf_valido(como(estudiante).get(URL.format(curso.nombre)), nombre_esperado(curso, "preguntas"))
    assert "intentos en esta evaluaci" in texto


def test_tipo_invalido_responde_400(como, estudiante, curso):
    respuesta = como(estudiante).get(URL.format(curso.nombre), {"tipo": "otro"})
    assert respuesta.status_code == 400


def test_curso_inexistente_o_inactivo_responde_404(como, estudiante, crear_curso):
    crear_curso("oculto", activo=False)
    assert como(estudiante).get(URL.format("no-existe")).status_code == 404
    assert como(estudiante).get(URL.format("oculto")).status_code == 404


def test_sin_sesion_401_y_sin_rol_403(api, como, sin_rol, curso):
    assert api.get(URL.format(curso.nombre)).status_code == 401
    assert como(sin_rol).get(URL.format(curso.nombre)).status_code == 403
