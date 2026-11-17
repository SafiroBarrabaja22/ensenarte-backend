"""
apps/cursos/procedimientos.py fuera de MySQL (SQLite local, PostgreSQL en la CI).

Los procedimientos almacenados no existen alli: los envoltorios deben avisarlo
con un error claro, y marcar_opcion_correcta (que usa el panel) debe funcionar
igual con el ORM.
"""

import pytest
from django.db import OperationalError, connection

from apps.cursos import procedimientos as proc
from apps.cursos.models import OpcionPregunta, Pregunta

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor == "mysql", reason="En MySQL se prueba en test_reglas_mysql.py."),
]


@pytest.mark.parametrize("llamada", [
    lambda: proc.cerrar_intento_evaluacion(1),
    lambda: proc.estadisticas_curso(1),
    lambda: proc.ranking_estudiantes(5),
    lambda: proc.clonar_curso(1, "copia"),
    lambda: proc.purgar_intentos_abandonados(30),
])
def test_procedimientos_avisan_que_solo_existen_en_mysql(llamada):
    with pytest.raises(proc.ProcedimientoNoDisponible):
        llamada()


def test_marcar_opcion_correcta_con_el_orm(crear_curso):
    pregunta = Pregunta.objects.filter(curso=crear_curso("orm", preguntas=1, palabras=0)).get()
    otra = pregunta.opciones.filter(es_correcta=False).first()
    proc.marcar_opcion_correcta(otra)
    assert list(OpcionPregunta.objects.filter(pregunta=pregunta, es_correcta=True)) == [otra]


def test_usuario_auditoria_no_hace_nada_fuera_de_mysql(estudiante):
    with proc.usuario_auditoria(estudiante):
        pass


def test_reconoce_errores_de_signal():
    assert proc.es_violacion_de_regla(OperationalError(1644, "regla"))
    assert not proc.es_violacion_de_regla(OperationalError(1205, "lock"))
    assert not proc.es_violacion_de_regla(ValueError("otro"))


def test_reglas_como_error_400_traduce_solo_los_signal():
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError) as error:
        with proc.reglas_como_error_400():
            raise OperationalError(1644, "Una pregunta admite como maximo 4 opciones.")
    assert "maximo 4" in str(error.value.detail)
    with pytest.raises(OperationalError):
        with proc.reglas_como_error_400():
            raise OperationalError(2006, "server has gone away")
