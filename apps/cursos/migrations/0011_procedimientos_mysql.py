"""
Procedimientos almacenados de MySQL.

SOLO procedimientos: los triggers van en 0012. El DDL de MySQL no es
transaccional; separarlos evita que un fallo en un tipo de objeto deje a medias
al otro.

Reglas de escritura (MySQL):
- Cada sentencia va como un elemento de la lista `sql`: Django la envia tal
  cual al servidor, sin DELIMITER (eso es del cliente `mysql`).
- Sin clausula DEFINER: el servidor asigna el usuario que migra.
- Errores con SIGNAL SQLSTATE '45000'.
- Ningun procedimiento abre una transaccion: START TRANSACTION confirmaria la
  del llamador. Se invocan dentro de transaction.atomic() (apps/cursos/procedimientos.py).
- Las fechas se escriben con UTC_TIMESTAMP(6) porque Django guarda en UTC (USE_TZ).
- Antes de cada CREATE hay un DROP ... IF EXISTS: si la migracion se corta a la
  mitad, se puede volver a correr sin tocar la base a mano.
"""

from django.db import migrations

from apps.cursos.operaciones_mysql import RunSQLSoloMySQL
from apps.usuarios.roles import ROL_ESTUDIANTE


def procedimiento(nombre, crear):
    return RunSQLSoloMySQL(
        sql=[f"DROP PROCEDURE IF EXISTS {nombre}", crear],
        reverse_sql=[f"DROP PROCEDURE IF EXISTS {nombre}"],
    )


CERRAR_INTENTO = """
-- Regla de negocio: cerrar un intento consolida su resultado en el progreso del
-- estudiante (aciertos, errores, completado), conserva la insignia Curso 100
-- si ya la tenia y la otorga si acerto todo, deja solo los 5 intentos cerrados
-- mas recientes por curso y recalcula las estrellas del perfil.
-- Rechaza intentos inexistentes o ya cerrados.
CREATE PROCEDURE cerrar_intento_evaluacion(IN p_intento_id BIGINT)
COMMENT 'Cierra un intento: consolida progreso, insignia 100 y estrellas'
BEGIN
    DECLARE v_usuario INT DEFAULT NULL;
    DECLARE v_curso BIGINT DEFAULT NULL;
    DECLARE v_aciertos INT DEFAULT 0;
    DECLARE v_errores INT DEFAULT 0;
    DECLARE v_total INT DEFAULT 0;
    DECLARE v_finalizado TINYINT DEFAULT 0;

    SELECT usuario_id, curso_id, aciertos, errores, COALESCE(JSON_LENGTH(orden), 0), finalizado
      INTO v_usuario, v_curso, v_aciertos, v_errores, v_total, v_finalizado
      FROM cursos_intentoevaluacion
     WHERE id = p_intento_id
       FOR UPDATE;

    IF v_usuario IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El intento de evaluacion no existe.';
    END IF;
    IF v_finalizado = 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El intento de evaluacion ya estaba cerrado.';
    END IF;

    UPDATE cursos_intentoevaluacion
       SET finalizado = 1, fecha_actualizacion = UTC_TIMESTAMP(6)
     WHERE id = p_intento_id;

    -- Solo se conservan los 5 intentos cerrados mas recientes por usuario y curso.
    DELETE FROM cursos_intentoevaluacion
     WHERE usuario_id = v_usuario AND curso_id = v_curso AND finalizado = 1
       AND id NOT IN (
           SELECT id FROM (
               SELECT id FROM cursos_intentoevaluacion
                WHERE usuario_id = v_usuario AND curso_id = v_curso AND finalizado = 1
                ORDER BY fecha_inicio DESC, id DESC
                LIMIT 5
           ) AS recientes
       );

    INSERT INTO cursos_progresousuario
        (usuario_id, curso_id, aciertos, errores, completado, insignia_100_ganada, fecha_ultima_actividad)
    VALUES
        (v_usuario, v_curso, v_aciertos, v_errores, 1,
         (v_total > 0 AND v_aciertos = v_total), UTC_TIMESTAMP(6))
    AS nuevo
    ON DUPLICATE KEY UPDATE
        aciertos = nuevo.aciertos,
        errores = nuevo.errores,
        completado = 1,
        insignia_100_ganada = (cursos_progresousuario.insignia_100_ganada OR nuevo.insignia_100_ganada),
        fecha_ultima_actividad = nuevo.fecha_ultima_actividad;

    UPDATE usuarios_perfilusuario
       SET estrellas = (SELECT COUNT(*) FROM cursos_progresousuario
                         WHERE usuario_id = v_usuario AND completado = 1)
     WHERE user_id = v_usuario;

    SELECT p.aciertos, p.errores, v_total AS total, p.completado, p.insignia_100_ganada,
           (SELECT estrellas FROM usuarios_perfilusuario WHERE user_id = v_usuario) AS estrellas
      FROM cursos_progresousuario p
     WHERE p.usuario_id = v_usuario AND p.curso_id = v_curso;
END
"""

ESTADISTICAS_CURSO = """
-- Regla de negocio: las cifras de un curso se calculan siempre igual para el
-- panel y los reportes: promedio de aciertos y errores de los intentos cerrados,
-- estudiantes que lo completaron y tasa de aprobacion (porcentaje de intentos
-- cuyo porcentaje de aciertos alcanza p_umbral). Rechaza cursos inexistentes y
-- umbrales fuera de 0..100.
CREATE PROCEDURE estadisticas_curso(IN p_curso_id BIGINT, IN p_umbral INT)
COMMENT 'Promedios, estudiantes que completaron y tasa de aprobacion de un curso'
BEGIN
    IF NOT EXISTS (SELECT 1 FROM cursos_curso WHERE id = p_curso_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El curso no existe.';
    END IF;
    IF p_umbral IS NULL OR p_umbral < 0 OR p_umbral > 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El umbral de aprobacion debe estar entre 0 y 100.';
    END IF;

    SELECT
        p_curso_id AS curso_id,
        COUNT(*) AS intentos_finalizados,
        COALESCE(ROUND(AVG(i.aciertos), 2), 0) AS promedio_aciertos,
        COALESCE(ROUND(AVG(i.errores), 2), 0) AS promedio_errores,
        (SELECT COUNT(*) FROM cursos_progresousuario p
          WHERE p.curso_id = p_curso_id AND p.completado = 1) AS estudiantes_completaron,
        COALESCE(ROUND(
            100 * SUM(JSON_LENGTH(i.orden) > 0 AND i.aciertos * 100 >= p_umbral * JSON_LENGTH(i.orden))
            / NULLIF(COUNT(*), 0), 2), 0) AS tasa_aprobacion
      FROM cursos_intentoevaluacion i
     WHERE i.curso_id = p_curso_id AND i.finalizado = 1;
END
"""

RANKING_ESTUDIANTES = """
-- Regla de negocio: el ranking incluye solo cuentas activas con rol Estudiante,
-- ordenadas por cursos completados, luego por aciertos acumulados y, en empate,
-- por nombre (orden estable). Rechaza limites menores que 1.
CREATE PROCEDURE ranking_estudiantes(IN p_limite INT)
COMMENT 'Los N primeros estudiantes por cursos completados y aciertos'
BEGIN
    IF p_limite IS NULL OR p_limite < 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El limite del ranking debe ser al menos 1.';
    END IF;

    SELECT u.id AS usuario_id,
           u.username AS usuario,
           CAST(COALESCE(SUM(p.completado), 0) AS UNSIGNED) AS cursos_completados,
           CAST(COALESCE(SUM(p.aciertos), 0) AS UNSIGNED) AS aciertos
      FROM auth_user u
      JOIN auth_user_groups ug ON ug.user_id = u.id
      JOIN auth_group g ON g.id = ug.group_id AND g.name = '__ROL_ESTUDIANTE__'
      LEFT JOIN cursos_progresousuario p ON p.usuario_id = u.id
     WHERE u.is_active = 1
     GROUP BY u.id, u.username
     ORDER BY cursos_completados DESC, aciertos DESC, u.username ASC
     LIMIT p_limite;
END
""".replace("__ROL_ESTUDIANTE__", ROL_ESTUDIANTE)

CLONAR_CURSO = """
-- Regla de negocio: clonar copia el curso con sus preguntas, opciones (con la
-- misma correcta) y palabras del diccionario en el mismo orden, bajo un slug
-- nuevo y valido. Los recursos de la biblioteca (portada, icono, insignias,
-- gifs) se COMPARTEN: duplicar sus filas haria que borrar uno dejara al otro
-- sin archivo. El clon queda inactivo para revisarlo antes de publicarlo.
CREATE PROCEDURE clonar_curso(IN p_curso_id BIGINT, IN p_slug VARCHAR(50), IN p_usuario_id INT)
COMMENT 'Clona un curso con preguntas, opciones y palabras bajo un slug nuevo'
BEGIN
    DECLARE v_nuevo BIGINT DEFAULT NULL;
    DECLARE v_pregunta_vieja BIGINT DEFAULT NULL;
    DECLARE v_pregunta_nueva BIGINT DEFAULT NULL;
    DECLARE v_fin TINYINT DEFAULT 0;
    DECLARE c_preguntas CURSOR FOR
        SELECT id FROM cursos_pregunta WHERE curso_id = p_curso_id ORDER BY id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fin = 1;

    IF NOT EXISTS (SELECT 1 FROM cursos_curso WHERE id = p_curso_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El curso a clonar no existe.';
    END IF;
    IF p_slug IS NULL OR p_slug NOT REGEXP '^[-a-zA-Z0-9_]+$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El slug nuevo solo admite letras, numeros, guiones y guion bajo.';
    END IF;
    IF EXISTS (SELECT 1 FROM cursos_curso WHERE nombre = p_slug) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ya existe un curso con ese slug.';
    END IF;

    INSERT INTO cursos_curso
        (nombre, titulo, portada_curso, icono_curso, insignia, insignia_100_id, descripcion,
         preguntas_por_evaluacion, creado_por_id, fecha_creacion, fecha_modificacion, activo)
    SELECT p_slug, LEFT(CONCAT(titulo, ' (copia)'), 100), portada_curso, icono_curso, insignia,
           insignia_100_id, descripcion, preguntas_por_evaluacion,
           COALESCE(p_usuario_id, creado_por_id), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6), 0
      FROM cursos_curso
     WHERE id = p_curso_id;
    -- LAST_INSERT_ID no se altera por el insert que hace el trigger de auditoria.
    SET v_nuevo = LAST_INSERT_ID();

    OPEN c_preguntas;
    copiar_preguntas: LOOP
        FETCH c_preguntas INTO v_pregunta_vieja;
        IF v_fin = 1 THEN
            LEAVE copiar_preguntas;
        END IF;
        INSERT INTO cursos_pregunta (curso_id, texto, video)
             SELECT v_nuevo, texto, video FROM cursos_pregunta WHERE id = v_pregunta_vieja;
        SET v_pregunta_nueva = LAST_INSERT_ID();
        INSERT INTO cursos_opcionpregunta (pregunta_id, texto, es_correcta)
             SELECT v_pregunta_nueva, texto, es_correcta
               FROM cursos_opcionpregunta
              WHERE pregunta_id = v_pregunta_vieja
              ORDER BY id;
    END LOOP;
    CLOSE c_preguntas;

    INSERT INTO cursos_palabradiccionario (curso_id, titulo, imagen_frontal, video_gif, orden)
         SELECT v_nuevo, titulo, imagen_frontal, video_gif, orden
           FROM cursos_palabradiccionario
          WHERE curso_id = p_curso_id
          ORDER BY orden, id;

    SELECT v_nuevo AS curso_id;
END
"""

PURGAR_INTENTOS = """
-- Regla de negocio: los intentos abandonados no se acumulan para siempre.
-- Borra los intentos de evaluacion sin terminar sin actividad hace mas de
-- p_dias dias y las sesiones de camara incompletas (con menos letras
-- registradas que su total) de esa misma antiguedad, junto con sus letras.
-- Nunca toca intentos ni sesiones completos. Rechaza p_dias menor que 1.
CREATE PROCEDURE purgar_intentos_abandonados(IN p_dias INT)
COMMENT 'Borra intentos sin terminar y sesiones de camara incompletas viejas'
BEGIN
    DECLARE v_corte DATETIME(6);
    DECLARE v_intentos INT DEFAULT 0;
    DECLARE v_sesiones INT DEFAULT 0;

    IF p_dias IS NULL OR p_dias < 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Los dias para purgar deben ser al menos 1.';
    END IF;
    SET v_corte = UTC_TIMESTAMP(6) - INTERVAL p_dias DAY;

    DELETE FROM cursos_intentoevaluacion
     WHERE finalizado = 0 AND fecha_actualizacion < v_corte;
    SET v_intentos = ROW_COUNT();

    -- Primero las letras de las sesiones incompletas (no hay ON DELETE CASCADE).
    DELETE FROM evaluacion_camara_intentocamara
     WHERE evaluacion_id IN (
         SELECT id FROM (
             SELECT e.id
               FROM evaluacion_camara_evaluacioncamara e
               LEFT JOIN evaluacion_camara_intentocamara i ON i.evaluacion_id = e.id
              WHERE e.fecha < v_corte
              GROUP BY e.id, e.total
             HAVING COUNT(i.id) <> e.total
         ) AS incompletas
     );

    DELETE FROM evaluacion_camara_evaluacioncamara
     WHERE fecha < v_corte
       AND id IN (
         SELECT id FROM (
             SELECT e.id
               FROM evaluacion_camara_evaluacioncamara e
               LEFT JOIN evaluacion_camara_intentocamara i ON i.evaluacion_id = e.id
              WHERE e.fecha < v_corte
              GROUP BY e.id, e.total
             HAVING COUNT(i.id) <> e.total
         ) AS incompletas
     );
    SET v_sesiones = ROW_COUNT();

    SELECT v_intentos AS intentos_borrados, v_sesiones AS sesiones_camara_borradas;
END
"""

MARCAR_OPCION_CORRECTA = """
-- Regla de negocio: una pregunta tiene exactamente una opcion correcta.
-- MySQL no permite que un trigger modifique la tabla que lo disparo, asi que
-- "marcar una y desmarcar las demas" se hace aqui, en orden: primero desmarca
-- las otras y despues marca esta. Los triggers opcion_una_correcta_* rechazan
-- cualquier otra forma de dejar dos correctas.
CREATE PROCEDURE marcar_opcion_correcta(IN p_opcion_id BIGINT)
COMMENT 'Deja una opcion como la unica correcta de su pregunta'
BEGIN
    DECLARE v_pregunta BIGINT DEFAULT NULL;

    SELECT pregunta_id INTO v_pregunta
      FROM cursos_opcionpregunta
     WHERE id = p_opcion_id
       FOR UPDATE;

    IF v_pregunta IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La opcion no existe.';
    END IF;

    UPDATE cursos_opcionpregunta
       SET es_correcta = 0
     WHERE pregunta_id = v_pregunta AND id <> p_opcion_id AND es_correcta = 1;

    UPDATE cursos_opcionpregunta
       SET es_correcta = 1
     WHERE id = p_opcion_id;
END
"""


class Migration(migrations.Migration):

    # El DDL de MySQL no es transaccional: no prometer una atomicidad que no hay.
    atomic = False

    dependencies = [
        ("cursos", "0010_auditoria_curso"),
        ("usuarios", "0003_grupos_de_roles"),
        ("evaluacion_camara", "0003_evaluacioncamara_curso"),
    ]

    operations = [
        procedimiento("cerrar_intento_evaluacion", CERRAR_INTENTO),
        procedimiento("estadisticas_curso", ESTADISTICAS_CURSO),
        procedimiento("ranking_estudiantes", RANKING_ESTUDIANTES),
        procedimiento("clonar_curso", CLONAR_CURSO),
        procedimiento("purgar_intentos_abandonados", PURGAR_INTENTOS),
        procedimiento("marcar_opcion_correcta", MARCAR_OPCION_CORRECTA),
    ]
