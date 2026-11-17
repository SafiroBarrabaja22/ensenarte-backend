"""
Triggers de MySQL.

SOLO triggers: los procedimientos van en 0011 (ver alli las reglas de escritura:
sin DELIMITER, sin DEFINER, SIGNAL SQLSTATE '45000', UTC_TIMESTAMP(6)).

Cinco reglas de negocio. Un trigger de MySQL atiende un solo evento (INSERT,
UPDATE o DELETE), asi que algunas reglas necesitan mas de uno:

  1. Una sola opcion correcta por pregunta ...... opcion_una_correcta_insert / _update
  2. Maximo de opciones por pregunta ............ opcion_maximo_insert / _update
  3. Auditoria de cursos ........................ curso_auditoria_insert / _update / _delete
  4. Estrellas segun cursos completados ......... progreso_estrellas_insert / _update
  5. Un intento finalizado no admite respuestas . intento_finalizado_inmutable

Regla 1: el pedido original era "al marcar una correcta, desmarcar las demas",
pero MySQL prohibe que un trigger modifique la tabla que lo disparo (error 1442).
El trigger rechaza la segunda correcta y el cambio de correcta se hace con el
procedimiento marcar_opcion_correcta (migracion 0011).
"""

from django.db import migrations

from apps.cursos.models import MAXIMO_OPCIONES_POR_PREGUNTA
from apps.cursos.operaciones_mysql import RunSQLSoloMySQL

CAMPOS_CURSO = (
    "nombre", "titulo", "descripcion", "portada_curso", "icono_curso", "insignia",
    "insignia_100_id", "preguntas_por_evaluacion", "creado_por_id", "activo",
    "fecha_creacion", "fecha_modificacion",
)


def json_curso(fila):
    """JSON_OBJECT con las columnas del curso de OLD o NEW."""
    pares = []
    for campo in CAMPOS_CURSO:
        valor = f"{fila}.{campo}"
        if campo == "activo":
            valor = f"IF({valor}, CAST('true' AS JSON), CAST('false' AS JSON))"
        pares.append(f"'{campo}', {valor}")
    return "JSON_OBJECT(" + ", ".join(pares) + ")"


def trigger(nombre, crear):
    return RunSQLSoloMySQL(
        sql=[f"DROP TRIGGER IF EXISTS {nombre}", crear],
        reverse_sql=[f"DROP TRIGGER IF EXISTS {nombre}"],
    )


# ---------------------------------------------------------------- Regla 1

UNA_CORRECTA_INSERT = """
-- Regla de negocio: una pregunta tiene una sola opcion correcta. Impide crear
-- una opcion correcta si la pregunta ya tiene otra. Para cambiar cual es la
-- correcta se usa el procedimiento marcar_opcion_correcta().
CREATE TRIGGER opcion_una_correcta_insert
BEFORE INSERT ON cursos_opcionpregunta
FOR EACH ROW
BEGIN
    IF NEW.es_correcta = 1 AND EXISTS (
        SELECT 1 FROM cursos_opcionpregunta
         WHERE pregunta_id = NEW.pregunta_id AND es_correcta = 1
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La pregunta ya tiene una opcion correcta. Usa marcar_opcion_correcta().';
    END IF;
END
"""

UNA_CORRECTA_UPDATE = """
-- Regla de negocio: una pregunta tiene una sola opcion correcta. Impide marcar
-- como correcta una opcion (o moverla a otra pregunta siendo correcta) si su
-- pregunta ya tiene otra correcta.
CREATE TRIGGER opcion_una_correcta_update
BEFORE UPDATE ON cursos_opcionpregunta
FOR EACH ROW
BEGIN
    IF NEW.es_correcta = 1 AND EXISTS (
        SELECT 1 FROM cursos_opcionpregunta
         WHERE pregunta_id = NEW.pregunta_id AND es_correcta = 1 AND id <> NEW.id
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'La pregunta ya tiene una opcion correcta. Usa marcar_opcion_correcta().';
    END IF;
END
"""

# ---------------------------------------------------------------- Regla 2

MAXIMO_INSERT = """
-- Regla de negocio: una pregunta admite como maximo __MAXIMO__ opciones.
-- Bloquea la siguiente aunque se cree por fuera del panel (admin, scripts, SQL).
CREATE TRIGGER opcion_maximo_insert
BEFORE INSERT ON cursos_opcionpregunta
FOR EACH ROW
BEGIN
    IF (SELECT COUNT(*) FROM cursos_opcionpregunta
         WHERE pregunta_id = NEW.pregunta_id) >= __MAXIMO__ THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Una pregunta admite como maximo __MAXIMO__ opciones.';
    END IF;
END
""".replace("__MAXIMO__", str(MAXIMO_OPCIONES_POR_PREGUNTA))

MAXIMO_UPDATE = """
-- Regla de negocio: una pregunta admite como maximo __MAXIMO__ opciones.
-- Impide mover una opcion a una pregunta que ya esta llena.
CREATE TRIGGER opcion_maximo_update
BEFORE UPDATE ON cursos_opcionpregunta
FOR EACH ROW
BEGIN
    IF NEW.pregunta_id <> OLD.pregunta_id AND (
        SELECT COUNT(*) FROM cursos_opcionpregunta WHERE pregunta_id = NEW.pregunta_id
    ) >= __MAXIMO__ THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Una pregunta admite como maximo __MAXIMO__ opciones.';
    END IF;
END
""".replace("__MAXIMO__", str(MAXIMO_OPCIONES_POR_PREGUNTA))

# ---------------------------------------------------------------- Regla 3

AUDITORIA_INSERT = """
-- Regla de negocio: todo curso nuevo queda registrado en la auditoria, con
-- quien lo creo (usuario de la aplicacion: @ensenarte_usuario_id o, si no se
-- indico, creado_por) y su contenido inicial en JSON.
CREATE TRIGGER curso_auditoria_insert
AFTER INSERT ON cursos_curso
FOR EACH ROW
BEGIN
    INSERT INTO cursos_auditoriacurso
        (curso_id, operacion, usuario_id, usuario_bd, fecha, valores_anteriores, valores_nuevos)
    VALUES
        (NEW.id, 'alta', COALESCE(@ensenarte_usuario_id, NEW.creado_por_id), USER(),
         UTC_TIMESTAMP(6), NULL, __NEW__);
END
""".replace("__NEW__", json_curso("NEW"))

AUDITORIA_UPDATE = """
-- Regla de negocio: todo cambio de un curso queda registrado con los valores
-- anteriores y nuevos en JSON, quien lo hizo y cuando.
CREATE TRIGGER curso_auditoria_update
AFTER UPDATE ON cursos_curso
FOR EACH ROW
BEGIN
    INSERT INTO cursos_auditoriacurso
        (curso_id, operacion, usuario_id, usuario_bd, fecha, valores_anteriores, valores_nuevos)
    VALUES
        (NEW.id, 'cambio', @ensenarte_usuario_id, USER(), UTC_TIMESTAMP(6), __OLD__, __NEW__);
END
""".replace("__OLD__", json_curso("OLD")).replace("__NEW__", json_curso("NEW"))

AUDITORIA_DELETE = """
-- Regla de negocio: borrar un curso no borra su rastro. Queda registrado quien
-- lo borro, cuando y el contenido que tenia.
CREATE TRIGGER curso_auditoria_delete
AFTER DELETE ON cursos_curso
FOR EACH ROW
BEGIN
    INSERT INTO cursos_auditoriacurso
        (curso_id, operacion, usuario_id, usuario_bd, fecha, valores_anteriores, valores_nuevos)
    VALUES
        (OLD.id, 'baja', @ensenarte_usuario_id, USER(), UTC_TIMESTAMP(6), __OLD__, NULL);
END
""".replace("__OLD__", json_curso("OLD"))

# ---------------------------------------------------------------- Regla 4

RECALCULAR_ESTRELLAS = """
        UPDATE usuarios_perfilusuario
           SET estrellas = (SELECT COUNT(*) FROM cursos_progresousuario
                             WHERE usuario_id = NEW.usuario_id AND completado = 1)
         WHERE user_id = NEW.usuario_id;"""

ESTRELLAS_INSERT = """
-- Regla de negocio: las estrellas del perfil son la cantidad de cursos
-- completados. Un progreso que nace completado las recalcula.
CREATE TRIGGER progreso_estrellas_insert
AFTER INSERT ON cursos_progresousuario
FOR EACH ROW
BEGIN
    IF NEW.completado = 1 THEN__RECALCULAR__
    END IF;
END
""".replace("__RECALCULAR__", RECALCULAR_ESTRELLAS)

ESTRELLAS_UPDATE = """
-- Regla de negocio: las estrellas del perfil son la cantidad de cursos
-- completados. Al marcar (o desmarcar) un progreso como completado se
-- recalculan, aunque el cambio no venga de la aplicacion.
CREATE TRIGGER progreso_estrellas_update
AFTER UPDATE ON cursos_progresousuario
FOR EACH ROW
BEGIN
    IF NEW.completado <> OLD.completado THEN__RECALCULAR__
    END IF;
END
""".replace("__RECALCULAR__", RECALCULAR_ESTRELLAS)

# ---------------------------------------------------------------- Regla 5

INTENTO_FINALIZADO = """
-- Regla de negocio: un intento de evaluacion finalizado es definitivo. Rechaza
-- registrar respuestas (respuestas, aciertos, errores, preguntas falladas o
-- avanzar de pregunta) y reabrirlo una vez cerrado.
CREATE TRIGGER intento_finalizado_inmutable
BEFORE UPDATE ON cursos_intentoevaluacion
FOR EACH ROW
BEGIN
    IF OLD.finalizado = 1 AND (
           NEW.finalizado = 0
        OR NOT (NEW.respuestas <=> OLD.respuestas)
        OR NOT (NEW.falladas <=> OLD.falladas)
        OR NEW.aciertos <> OLD.aciertos
        OR NEW.errores <> OLD.errores
        OR NEW.indice_actual <> OLD.indice_actual
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El intento ya finalizo: no admite mas respuestas.';
    END IF;
END
"""


class Migration(migrations.Migration):

    # El DDL de MySQL no es transaccional: no prometer una atomicidad que no hay.
    atomic = False

    dependencies = [
        ("cursos", "0011_procedimientos_mysql"),
        ("usuarios", "0003_grupos_de_roles"),
    ]

    operations = [
        trigger("opcion_una_correcta_insert", UNA_CORRECTA_INSERT),
        trigger("opcion_una_correcta_update", UNA_CORRECTA_UPDATE),
        trigger("opcion_maximo_insert", MAXIMO_INSERT),
        trigger("opcion_maximo_update", MAXIMO_UPDATE),
        trigger("curso_auditoria_insert", AUDITORIA_INSERT),
        trigger("curso_auditoria_update", AUDITORIA_UPDATE),
        trigger("curso_auditoria_delete", AUDITORIA_DELETE),
        trigger("progreso_estrellas_insert", ESTRELLAS_INSERT),
        trigger("progreso_estrellas_update", ESTRELLAS_UPDATE),
        trigger("intento_finalizado_inmutable", INTENTO_FINALIZADO),
    ]
