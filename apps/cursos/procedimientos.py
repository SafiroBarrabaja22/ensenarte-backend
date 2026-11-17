"""
Acceso desde Python a los procedimientos almacenados de MySQL (migracion 0011)
y utilidades para convivir con los triggers (migracion 0012).

- Los procedimientos solo existen en MySQL. Fuera de MySQL (SQLite en las
  pruebas locales, PostgreSQL en la CI) lanzan ProcedimientoNoDisponible,
  salvo marcar_opcion_correcta, que el panel usa siempre y tiene una version ORM.
- Los procedimientos NO abren su propia transaccion (un START TRANSACTION
  confirmaria la del llamador). Estos envoltorios los ejecutan dentro de
  transaction.atomic().
- Los triggers rechazan con SIGNAL SQLSTATE '45000', que MySQL reporta con el
  codigo 1644. es_violacion_de_regla() lo reconoce.
"""

from contextlib import contextmanager

from django.conf import settings
from django.db import OperationalError, connection, transaction
from rest_framework.exceptions import ValidationError

from .models import OpcionPregunta

# Codigo de MySQL para un error lanzado con SIGNAL (ER_SIGNAL_EXCEPTION).
CODIGO_SIGNAL = 1644


class ProcedimientoNoDisponible(RuntimeError):
    """El procedimiento almacenado solo existe en MySQL."""


def es_mysql():
    return connection.vendor == "mysql"


def es_violacion_de_regla(error):
    """True si el error viene de un SIGNAL de un trigger o procedimiento."""
    return isinstance(error, OperationalError) and bool(error.args) and error.args[0] == CODIGO_SIGNAL


@contextmanager
def reglas_como_error_400():
    """Convierte un rechazo de la base (SIGNAL) en un 400 legible para la API."""
    try:
        yield
    except OperationalError as error:
        if es_violacion_de_regla(error):
            raise ValidationError({"non_field_errors": [error.args[1]]}) from error
        raise


@contextmanager
def usuario_auditoria(usuario):
    """
    Indica a los triggers curso_auditoria_* que usuario de la aplicacion hace
    el cambio (variable de sesion @ensenarte_usuario_id). Se limpia al salir
    para que no quede pegada a la conexion.
    """
    if not es_mysql():
        yield
        return
    usuario_id = getattr(usuario, "pk", None) if usuario is not None and usuario.is_authenticated else None
    with connection.cursor() as cursor:
        cursor.execute("SET @ensenarte_usuario_id = %s", [usuario_id])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET @ensenarte_usuario_id = NULL")


def _llamar(nombre, *parametros):
    """CALL nombre(...) y devuelve la primera tabla de resultados como lista de dicts."""
    if not es_mysql():
        raise ProcedimientoNoDisponible(f"{nombre} solo existe en MySQL.")
    marcadores = ", ".join(["%s"] * len(parametros))
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"CALL {nombre}({marcadores})", list(parametros))
        filas = []
        if cursor.description:
            columnas = [columna[0] for columna in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        # Un CALL devuelve un resultado extra (el estado); hay que consumirlo.
        while cursor.nextset():
            pass
    return filas


def cerrar_intento_evaluacion(intento_id):
    """Procedimiento 1. Devuelve el progreso consolidado y las estrellas."""
    return _llamar("cerrar_intento_evaluacion", intento_id)[0]


def estadisticas_curso(curso_id, umbral=None):
    """Procedimiento 2. umbral: porcentaje minimo de aciertos para aprobar."""
    if umbral is None:
        umbral = settings.EVALUACION_CAMARA_UMBRAL_APROBACION
    return _llamar("estadisticas_curso", curso_id, umbral)[0]


def ranking_estudiantes(limite=10):
    """Procedimiento 3. Los `limite` primeros por cursos completados y aciertos."""
    return _llamar("ranking_estudiantes", limite)


def clonar_curso(curso_id, slug_nuevo, usuario=None):
    """Procedimiento 4. Devuelve el id del curso nuevo (queda inactivo)."""
    usuario_id = getattr(usuario, "pk", None)
    with usuario_auditoria(usuario):
        return _llamar("clonar_curso", curso_id, slug_nuevo, usuario_id)[0]["curso_id"]


def purgar_intentos_abandonados(dias):
    """Procedimiento 5. Devuelve cuantos intentos y sesiones de camara borro."""
    return _llamar("purgar_intentos_abandonados", dias)[0]


def marcar_opcion_correcta(opcion):
    """
    Procedimiento 6. Deja `opcion` como la unica correcta de su pregunta.

    En MySQL lo hace el procedimiento (los triggers impiden dos correctas a la
    vez). En otros motores hace lo mismo con el ORM, en el mismo orden:
    primero desmarca las demas y despues marca esta.
    """
    if es_mysql():
        _llamar("marcar_opcion_correcta", opcion.pk)
    else:
        with transaction.atomic():
            OpcionPregunta.objects.filter(pregunta_id=opcion.pregunta_id).exclude(
                pk=opcion.pk
            ).update(es_correcta=False)
            OpcionPregunta.objects.filter(pk=opcion.pk).update(es_correcta=True)
    opcion.refresh_from_db()
    return opcion
