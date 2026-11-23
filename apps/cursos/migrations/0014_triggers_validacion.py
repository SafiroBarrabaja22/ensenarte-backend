"""
Triggers de MySQL de la validacion de senas (rol Validador).

Mismas reglas de escritura que 0011/0012: sin DELIMITER, sin DEFINER,
SIGNAL SQLSTATE '45000'. Son la ultima linea de defensa: la aplicacion ya
aplica estas reglas (apps/cursos/validacion.py), pero asi tampoco se pueden
saltar editando la base a mano.

  6. El estado de una sena solo cambia con su historial ... recurso_estado_con_historial
  7. Solo un Validador decide, y rechazar exige comentario . revision_sena_reglas
  8. El historial de una sena no se reescribe ............. revision_sena_inmutable

Regla 6: la aplicacion primero escribe la revision (cursos_revisionsena) y
despues cambia el estado del recurso; el trigger comprueba que el estado nuevo
coincide con la ultima revision. Asi un UPDATE a mano a "aprobada" sin una
aprobacion registrada falla.

Regla 7: el nombre del grupo sale de apps/usuarios/roles.py (ROL_VALIDADOR).
Un superusuario no es excepcion: tambien tiene que estar en el grupo.

Regla 8: borrar si se permite (al eliminar una sena de la biblioteca, Django
borra su historial en cascada), y quitar el usuario (SET_NULL al borrar su
cuenta) tambien. Lo demas no se cambia.
"""

from django.db import migrations

from apps.cursos.operaciones_mysql import RunSQLSoloMySQL
from apps.usuarios.roles import ROL_VALIDADOR


def trigger(nombre, crear):
    return RunSQLSoloMySQL(
        sql=[f"DROP TRIGGER IF EXISTS {nombre}", crear],
        reverse_sql=[f"DROP TRIGGER IF EXISTS {nombre}"],
    )


# ---------------------------------------------------------------- Regla 6

ESTADO_CON_HISTORIAL = """
-- Regla de negocio: el estado de validacion de una sena solo cambia junto con
-- su historial. El estado nuevo debe coincidir con la ultima revision:
-- aprobada -> 'aprobada', rechazada -> 'rechazada', reenviada -> 'pendiente'.
CREATE TRIGGER recurso_estado_con_historial
BEFORE UPDATE ON cursos_recursovisual
FOR EACH ROW
BEGIN
    DECLARE v_accion VARCHAR(10) DEFAULT NULL;
    IF NOT (NEW.estado_validacion <=> OLD.estado_validacion) THEN
        -- SET con subconsulta (y no SELECT ... INTO) para que "sin revisiones"
        -- sea simplemente NULL, sin la advertencia 1329 de cero filas.
        SET v_accion = (
            SELECT accion
              FROM cursos_revisionsena
             WHERE recurso_id = NEW.id
             ORDER BY id DESC
             LIMIT 1
        );
        IF v_accion IS NULL OR NEW.estado_validacion <> (
            CASE v_accion
                WHEN 'aprobada' THEN 'aprobada'
                WHEN 'rechazada' THEN 'rechazada'
                ELSE 'pendiente'
            END
        ) THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'El estado de una sena solo cambia con su revision (cursos_revisionsena).';
        END IF;
    END IF;
END
"""

# ---------------------------------------------------------------- Regla 7

REGLAS_REVISION = """
-- Regla de negocio: solo un usuario del grupo __VALIDADOR__ aprueba o rechaza
-- una sena (ni el superusuario es excepcion), y un rechazo siempre explica que
-- hay que corregir. 'reenviada' la registra quien reemplaza el archivo.
CREATE TRIGGER revision_sena_reglas
BEFORE INSERT ON cursos_revisionsena
FOR EACH ROW
BEGIN
    IF NEW.accion NOT IN ('aprobada', 'rechazada', 'reenviada') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Accion de revision no valida.';
    END IF;
    IF NEW.accion IN ('aprobada', 'rechazada') AND (NEW.usuario_id IS NULL OR NOT EXISTS (
        SELECT 1
          FROM auth_user_groups ug
          JOIN auth_group g ON g.id = ug.group_id
         WHERE ug.user_id = NEW.usuario_id AND g.name = '__VALIDADOR__'
    )) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Solo un usuario del grupo __VALIDADOR__ puede aprobar o rechazar una sena.';
    END IF;
    IF NEW.accion = 'rechazada' AND TRIM(COALESCE(NEW.comentario, '')) = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Rechazar una sena exige un comentario.';
    END IF;
END
""".replace("__VALIDADOR__", ROL_VALIDADOR)

# ---------------------------------------------------------------- Regla 8

HISTORIAL_INMUTABLE = """
-- Regla de negocio: el historial de una sena es un registro: una decision ya
-- tomada no se cambia. Solo se permite dejar el usuario en NULL (Django lo hace
-- al borrar la cuenta del usuario, on_delete=SET_NULL).
CREATE TRIGGER revision_sena_inmutable
BEFORE UPDATE ON cursos_revisionsena
FOR EACH ROW
BEGIN
    IF NOT (NEW.recurso_id <=> OLD.recurso_id)
        OR NOT (NEW.accion <=> OLD.accion)
        OR NOT (NEW.comentario <=> OLD.comentario)
        OR NOT (NEW.archivo <=> OLD.archivo)
        OR NOT (NEW.fecha <=> OLD.fecha)
        OR NOT (NEW.usuario_id <=> OLD.usuario_id OR NEW.usuario_id IS NULL)
    THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El historial de una sena no se modifica.';
    END IF;
END
"""


class Migration(migrations.Migration):

    # El DDL de MySQL no es transaccional: no prometer una atomicidad que no hay.
    atomic = False

    dependencies = [
        ("cursos", "0013_validacion_senas"),
        ("usuarios", "0005_grupo_validador"),
    ]

    operations = [
        trigger("recurso_estado_con_historial", ESTADO_CON_HISTORIAL),
        trigger("revision_sena_reglas", REGLAS_REVISION),
        trigger("revision_sena_inmutable", HISTORIAL_INMUTABLE),
    ]
