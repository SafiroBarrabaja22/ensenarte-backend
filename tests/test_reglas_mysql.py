"""
Reglas que protege la base de datos MySQL (migraciones 0011, 0012 y 0014).

Cada prueba intenta violar una regla DESDE EL ORM (create, save, update,
bulk_create) y comprueba que el rechazo viene de la base: un SIGNAL
SQLSTATE '45000' (codigo 1644), no una validacion de Python.

Solo corren contra MySQL:
    PRUEBAS_DATABASE_URL=mysql://.../proyecto_pruebas pytest tests/test_reglas_mysql.py
(Django crea y borra la base test_proyecto_pruebas). En SQLite y en la CI
(PostgreSQL) se saltan.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import OperationalError, connection, transaction
from django.utils import timezone

from apps.cursos import procedimientos as proc
from apps.cursos.models import (
    MAXIMO_OPCIONES_POR_PREGUNTA,
    AuditoriaCurso,
    Curso,
    IntentoEvaluacion,
    OpcionPregunta,
    PalabraDiccionario,
    Pregunta,
    ProgresoUsuario,
    RecursoVisual,
    RevisionSena,
)
from apps.cursos import validacion
from apps.evaluacion_camara.models import EvaluacionCamara, IntentoCamara
from apps.usuarios.roles import ROL_ESTUDIANTE

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "mysql", reason="Triggers y procedimientos solo existen en MySQL."),
]


@contextmanager
def la_base_rechaza(fragmento):
    """El bloque debe fallar con un SIGNAL cuyo mensaje contenga `fragmento`."""
    with pytest.raises(OperationalError) as error:
        with transaction.atomic():
            yield
    assert proc.es_violacion_de_regla(error.value), error.value
    assert fragmento in error.value.args[1]


def hace_dias(dias):
    return timezone.now() - timedelta(days=dias)


@pytest.fixture
def pregunta_con_una_correcta(crear_curso):
    curso = crear_curso("reglas", preguntas=0, palabras=0)
    pregunta = Pregunta.objects.create(curso=curso, texto="¿Regla?")
    correcta = OpcionPregunta.objects.create(pregunta=pregunta, texto="A", es_correcta=True)
    otra = OpcionPregunta.objects.create(pregunta=pregunta, texto="B", es_correcta=False)
    return pregunta, correcta, otra


# =================================================================== TRIGGERS

# ----------------------------------------- Regla 1: una sola opcion correcta


def test_trigger_rechaza_crear_una_segunda_correcta(pregunta_con_una_correcta):
    pregunta, _, _ = pregunta_con_una_correcta
    with la_base_rechaza("ya tiene una opcion correcta"):
        OpcionPregunta.objects.create(pregunta=pregunta, texto="C", es_correcta=True)


def test_trigger_rechaza_marcar_otra_como_correcta_con_save(pregunta_con_una_correcta):
    _, _, otra = pregunta_con_una_correcta
    otra.es_correcta = True
    with la_base_rechaza("ya tiene una opcion correcta"):
        otra.save()


def test_trigger_rechaza_marcar_todas_con_update(pregunta_con_una_correcta):
    pregunta, _, _ = pregunta_con_una_correcta
    with la_base_rechaza("ya tiene una opcion correcta"):
        pregunta.opciones.update(es_correcta=True)


def test_procedimiento_marcar_opcion_correcta_cambia_la_correcta(pregunta_con_una_correcta):
    pregunta, correcta, otra = pregunta_con_una_correcta
    proc.marcar_opcion_correcta(otra)
    assert list(pregunta.opciones.filter(es_correcta=True)) == [otra]
    correcta.refresh_from_db()
    assert correcta.es_correcta is False


def test_procedimiento_marcar_opcion_inexistente(db):
    with la_base_rechaza("La opcion no existe"):
        proc._llamar("marcar_opcion_correcta", 999999)


def test_el_panel_sigue_cambiando_la_correcta_en_mysql(como, profesor, crear_curso):
    curso = crear_curso("panel", creado_por=profesor, preguntas=1, palabras=0)
    otra = OpcionPregunta.objects.filter(pregunta__curso=curso, es_correcta=False).first()
    respuesta = como(profesor).patch(f"/api/panel/opciones/{otra.id}/", {"es_correcta": True}, format="json")
    assert respuesta.status_code == 200
    assert respuesta.data["es_correcta"] is True
    assert OpcionPregunta.objects.filter(pregunta=otra.pregunta, es_correcta=True).count() == 1


# ----------------------------------------- Regla 2: maximo de opciones


def test_trigger_bloquea_la_quinta_opcion(crear_curso):
    curso = crear_curso("llena", preguntas=1, palabras=0)
    pregunta = curso.preguntas.get()
    assert pregunta.opciones.count() == MAXIMO_OPCIONES_POR_PREGUNTA
    with la_base_rechaza(f"maximo {MAXIMO_OPCIONES_POR_PREGUNTA} opciones"):
        OpcionPregunta.objects.create(pregunta=pregunta, texto="E")


def test_trigger_bloquea_la_quinta_opcion_con_bulk_create(crear_curso):
    pregunta = Pregunta.objects.create(curso=crear_curso("masiva", preguntas=0, palabras=0), texto="¿Masiva?")
    opciones = [OpcionPregunta(pregunta=pregunta, texto=str(n)) for n in range(MAXIMO_OPCIONES_POR_PREGUNTA + 1)]
    with la_base_rechaza("opciones"):
        OpcionPregunta.objects.bulk_create(opciones)
    assert pregunta.opciones.count() == 0  # la transaccion se revirtio entera


def test_trigger_bloquea_mover_una_opcion_a_una_pregunta_llena(crear_curso, pregunta_con_una_correcta):
    llena = crear_curso("llena2", preguntas=1, palabras=0).preguntas.get()
    _, _, otra = pregunta_con_una_correcta
    otra.pregunta = llena
    with la_base_rechaza("opciones"):
        otra.save()


# ----------------------------------------- Regla 3: auditoria de cursos


def test_auditoria_registra_alta_cambio_y_baja(profesor, estudiante):
    curso = Curso.objects.create(nombre="auditado", titulo="Auditado", portada_curso="a.png", creado_por=profesor)
    alta = AuditoriaCurso.objects.get(curso_id=curso.id, operacion="alta")
    assert alta.usuario == profesor  # sin variable de sesion, toma creado_por
    assert alta.valores_anteriores is None
    assert alta.valores_nuevos["nombre"] == "auditado"
    assert alta.valores_nuevos["activo"] is True
    assert alta.usuario_bd  # usuario de MySQL

    with proc.usuario_auditoria(estudiante):
        curso.titulo = "Cambiado"
        curso.save()
    cambio = AuditoriaCurso.objects.get(curso_id=curso.id, operacion="cambio")
    assert cambio.usuario == estudiante
    assert (cambio.valores_anteriores["titulo"], cambio.valores_nuevos["titulo"]) == ("Auditado", "Cambiado")

    curso_id = curso.id
    curso.delete()
    baja = AuditoriaCurso.objects.get(curso_id=curso_id, operacion="baja")
    assert baja.usuario is None  # borrado sin indicar usuario de la aplicacion
    assert baja.valores_anteriores["titulo"] == "Cambiado"
    assert baja.valores_nuevos is None


def test_auditoria_registra_cambios_masivos_con_update(crear_curso):
    crear_curso("uno", preguntas=0, palabras=0)
    crear_curso("dos", preguntas=0, palabras=0)
    Curso.objects.update(activo=False)
    cambios = AuditoriaCurso.objects.filter(operacion="cambio")
    assert cambios.count() == 2
    assert all(c.valores_nuevos["activo"] is False for c in cambios)


def test_auditoria_toma_el_usuario_del_panel(como, creador):
    respuesta = como(creador).post(
        "/api/panel/cursos/", {"nombre": "desde-panel", "titulo": "X", "portada_curso": "x.png"}, format="json"
    )
    curso_id = respuesta.data["id"]
    como(creador).delete(f"/api/panel/cursos/{curso_id}/")
    registros = AuditoriaCurso.objects.filter(curso_id=curso_id).order_by("id")
    assert [(r.operacion, r.usuario) for r in registros] == [("alta", creador), ("baja", creador)]


def test_la_variable_de_auditoria_no_queda_pegada(estudiante, crear_curso):
    curso = crear_curso("limpio", preguntas=0, palabras=0)
    with proc.usuario_auditoria(estudiante):
        pass
    curso.titulo = "Sin usuario"
    curso.save()
    assert AuditoriaCurso.objects.get(curso_id=curso.id, operacion="cambio").usuario is None


# ----------------------------------------- Regla 4: estrellas


def test_trigger_recalcula_estrellas_al_completar(estudiante, crear_curso):
    uno = crear_curso("uno", preguntas=0, palabras=0)
    dos = crear_curso("dos", preguntas=0, palabras=0)

    ProgresoUsuario.objects.create(usuario=estudiante, curso=uno, completado=True)
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 1

    progreso = ProgresoUsuario.objects.create(usuario=estudiante, curso=dos, completado=False)
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 1

    ProgresoUsuario.objects.filter(pk=progreso.pk).update(completado=True)
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 2

    ProgresoUsuario.objects.filter(pk=progreso.pk).update(completado=False)
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 1


def test_trigger_de_estrellas_solo_actua_si_cambia_completado(estudiante, crear_curso):
    progreso = ProgresoUsuario.objects.create(usuario=estudiante, curso=crear_curso("x", preguntas=0, palabras=0), completado=True)
    estudiante.perfil.__class__.objects.filter(pk=estudiante.perfil.pk).update(estrellas=99)
    ProgresoUsuario.objects.filter(pk=progreso.pk).update(aciertos=7)
    estudiante.perfil.refresh_from_db()
    assert estudiante.perfil.estrellas == 99


# ----------------------------------------- Regla 5: intento finalizado inmutable


@pytest.fixture
def intento_finalizado(estudiante, crear_curso):
    curso = crear_curso("cerrado", preguntas=1, palabras=0)
    return IntentoEvaluacion.objects.create(
        usuario=estudiante, curso=curso, orden=[curso.preguntas.get().id],
        indice_actual=1, aciertos=1, finalizado=True,
    )


def test_trigger_rechaza_responder_un_intento_finalizado(intento_finalizado):
    intento_finalizado.respuestas = {"1": [99]}
    with la_base_rechaza("ya finalizo"):
        intento_finalizado.save()


@pytest.mark.parametrize("cambio", [{"aciertos": 5}, {"errores": 3}, {"indice_actual": 0}, {"falladas": [1]}, {"finalizado": False}])
def test_trigger_rechaza_cualquier_cambio_de_respuesta(intento_finalizado, cambio):
    with la_base_rechaza("ya finalizo"):
        IntentoEvaluacion.objects.filter(pk=intento_finalizado.pk).update(**cambio)


def test_guardar_un_intento_finalizado_sin_cambios_se_permite(intento_finalizado):
    intento_finalizado.save()  # solo cambia fecha_actualizacion


def test_un_intento_abierto_si_acepta_respuestas(estudiante, crear_curso):
    curso = crear_curso("abierto", preguntas=1, palabras=0)
    intento = IntentoEvaluacion.objects.create(usuario=estudiante, curso=curso, orden=[curso.preguntas.get().id])
    intento.respuestas = {"1": [1]}
    intento.errores = 1
    intento.save()
    intento.finalizado = True
    intento.save()


# ----------------------------------------- Reglas 6 a 8: validacion de senas (migracion 0014)


@pytest.fixture
def sena(interprete):
    return RecursoVisual.objects.create(
        nombre="Seña A", archivo="biblioteca/sena-prueba.gif", categoria=RecursoVisual.Categoria.RECURSO,
        subido_por=interprete, estado_validacion=RecursoVisual.EstadoValidacion.PENDIENTE,
    )


def test_trigger_rechaza_aprobar_una_sena_sin_revision(sena):
    with la_base_rechaza("solo cambia con su revision"):
        RecursoVisual.objects.filter(pk=sena.pk).update(estado_validacion="aprobada")


def test_trigger_rechaza_un_estado_distinto_a_la_ultima_revision(sena, validador):
    validacion.decidir(sena, False, "Corregir la mano.", validador)
    with la_base_rechaza("solo cambia con su revision"):
        RecursoVisual.objects.filter(pk=sena.pk).update(estado_validacion="aprobada")


def test_la_aplicacion_cambia_el_estado_con_su_revision(sena, validador, interprete):
    validacion.decidir(sena, False, "Corregir la mano.", validador)
    validacion.volver_a_revision(sena, interprete)
    validacion.decidir(sena, True, "", validador)
    sena.refresh_from_db()
    assert sena.estado_validacion == "aprobada"
    assert list(sena.revisiones.values_list("accion", flat=True)) == ["aprobada", "reenviada", "rechazada"]


@pytest.mark.parametrize("quien", ["interprete", "administrador", "superusuario"])
def test_trigger_solo_un_validador_aprueba(request, sena, crear_usuario, quien):
    usuario = (crear_usuario(None, "root", is_superuser=True, is_staff=True)
               if quien == "superusuario" else request.getfixturevalue(quien))
    with la_base_rechaza("Solo un usuario del grupo"):
        RevisionSena.objects.create(recurso=sena, accion="aprobada", usuario=usuario, archivo=sena.archivo.name)


def test_trigger_rechazar_exige_comentario(sena, validador):
    with la_base_rechaza("exige un comentario"):
        RevisionSena.objects.create(
            recurso=sena, accion="rechazada", comentario="   ", usuario=validador, archivo=sena.archivo.name
        )


def test_trigger_rechaza_una_accion_desconocida(sena, validador):
    with la_base_rechaza("Accion de revision no valida"):
        RevisionSena.objects.create(recurso=sena, accion="borrada", usuario=validador, archivo=sena.archivo.name)


def test_trigger_el_historial_no_se_modifica(sena, validador):
    validacion.decidir(sena, False, "Corregir la mano.", validador)
    revision = sena.revisiones.get()
    for cambio in ({"accion": "aprobada"}, {"comentario": "Otro comentario"}):
        with la_base_rechaza("no se modifica"):
            RevisionSena.objects.filter(pk=revision.pk).update(**cambio)


def test_borrar_la_cuenta_del_validador_o_la_sena_se_permite(sena, validador):
    validacion.decidir(sena, True, "", validador)
    validador.delete()   # SET_NULL en el historial
    assert sena.revisiones.get().usuario_id is None
    sena.delete()        # CASCADE del historial
    assert not RevisionSena.objects.exists()


# =================================================================== PROCEDIMIENTOS


# ----------------------------------------- 1. cerrar_intento_evaluacion


def _intento(usuario, curso, aciertos, errores=0, total=3, finalizado=False):
    ids = list(curso.preguntas.values_list("id", flat=True))[:total]
    return IntentoEvaluacion.objects.create(
        usuario=usuario, curso=curso, orden=ids, indice_actual=total,
        aciertos=aciertos, errores=errores, finalizado=finalizado,
    )


def test_cerrar_intento_consolida_progreso_estrellas_e_insignia(estudiante, crear_curso):
    curso = crear_curso("cierre", preguntas=3, palabras=0)
    resultado = proc.cerrar_intento_evaluacion(_intento(estudiante, curso, aciertos=3).id)
    assert resultado == {"aciertos": 3, "errores": 0, "total": 3, "completado": 1, "insignia_100_ganada": 1, "estrellas": 1}
    assert IntentoEvaluacion.objects.get(usuario=estudiante).finalizado is True

    # Un intento peor no quita la insignia ya ganada.
    resultado = proc.cerrar_intento_evaluacion(_intento(estudiante, curso, aciertos=1, errores=4).id)
    assert (resultado["aciertos"], resultado["insignia_100_ganada"], resultado["estrellas"]) == (1, 1, 1)


def test_cerrar_intento_ya_cerrado_o_inexistente_es_rechazado(estudiante, crear_curso):
    curso = crear_curso("cierre2", preguntas=1, palabras=0)
    intento = _intento(estudiante, curso, aciertos=1, total=1)
    proc.cerrar_intento_evaluacion(intento.id)
    with la_base_rechaza("ya estaba cerrado"):
        proc.cerrar_intento_evaluacion(intento.id)
    with la_base_rechaza("no existe"):
        proc.cerrar_intento_evaluacion(999999)


def test_cerrar_intento_conserva_solo_los_cinco_mas_recientes(estudiante, crear_curso):
    curso = crear_curso("retencion", preguntas=1, palabras=0)
    for _ in range(6):
        _intento(estudiante, curso, aciertos=1, total=1, finalizado=True)
    proc.cerrar_intento_evaluacion(_intento(estudiante, curso, aciertos=1, total=1).id)
    assert IntentoEvaluacion.objects.filter(usuario=estudiante, finalizado=True).count() == 5


# ----------------------------------------- 2. estadisticas_curso


def test_estadisticas_de_un_curso(estudiante, crear_usuario, crear_curso):
    curso = crear_curso("estadistico", preguntas=3, palabras=0)
    otro = crear_usuario(ROL_ESTUDIANTE)
    _intento(estudiante, curso, aciertos=3, errores=0, finalizado=True)   # 100 %: aprueba
    _intento(otro, curso, aciertos=1, errores=4, finalizado=True)         # 33 %: no aprueba
    _intento(otro, curso, aciertos=0)                                     # abierto: no cuenta
    ProgresoUsuario.objects.create(usuario=estudiante, curso=curso, completado=True)

    datos = proc.estadisticas_curso(curso.id, umbral=70)
    assert datos["intentos_finalizados"] == 2
    assert datos["promedio_aciertos"] == Decimal("2.00")
    assert datos["promedio_errores"] == Decimal("2.00")
    assert datos["estudiantes_completaron"] == 1
    assert datos["tasa_aprobacion"] == Decimal("50.00")


def test_estadisticas_de_curso_sin_intentos(crear_curso):
    datos = proc.estadisticas_curso(crear_curso("vacio", preguntas=0, palabras=0).id)
    assert (datos["intentos_finalizados"], datos["tasa_aprobacion"]) == (0, 0)


@pytest.mark.parametrize("curso_id, umbral, mensaje", [(999999, 70, "El curso no existe"), (None, 101, "entre 0 y 100")])
def test_estadisticas_con_parametros_invalidos(crear_curso, curso_id, umbral, mensaje):
    curso_id = curso_id or crear_curso("x", preguntas=0, palabras=0).id
    with la_base_rechaza(mensaje):
        proc.estadisticas_curso(curso_id, umbral=umbral)


# ----------------------------------------- 3. ranking_estudiantes


def test_ranking_ordena_por_completados_y_aciertos(crear_usuario, crear_curso, profesor):
    cursos = [crear_curso(f"c{n}", preguntas=0, palabras=0) for n in range(3)]
    ana, beto, carla = (crear_usuario(ROL_ESTUDIANTE, nombre) for nombre in ("ana", "beto", "carla"))
    for usuario, completados, aciertos in ((ana, 2, 10), (beto, 2, 15), (carla, 1, 30), (profesor, 3, 50)):
        for n in range(completados):
            ProgresoUsuario.objects.create(usuario=usuario, curso=cursos[n], completado=True, aciertos=aciertos // completados)

    ranking = proc.ranking_estudiantes(limite=2)
    assert [(f["usuario"], f["cursos_completados"], f["aciertos"]) for f in ranking] == [("beto", 2, 14), ("ana", 2, 10)]
    todos = [f["usuario"] for f in proc.ranking_estudiantes(limite=50)]
    assert "profesor" not in todos  # solo rol Estudiante


def test_ranking_con_limite_invalido(db):
    with la_base_rechaza("al menos 1"):
        proc.ranking_estudiantes(limite=0)


# ----------------------------------------- 4. clonar_curso


def test_clonar_curso_copia_contenido_y_comparte_recursos(crear_curso, profesor, creador):
    original = crear_curso("original", creado_por=profesor, preguntas=2, palabras=3)
    original.insignia_100 = RecursoVisual.objects.create(
        nombre="Oro", archivo="biblioteca/oro.png", categoria=RecursoVisual.Categoria.CURSO_100
    )
    original.save()
    PalabraDiccionario.objects.filter(curso=original, titulo="Palabra 1").update(orden=9)
    recursos_antes = RecursoVisual.objects.count()

    nuevo = Curso.objects.get(pk=proc.clonar_curso(original.id, "copia-original", usuario=creador))

    assert (nuevo.nombre, nuevo.titulo, nuevo.activo) == ("copia-original", "Original (copia)", False)
    assert nuevo.creado_por == creador
    assert nuevo.insignia_100_id == original.insignia_100_id
    assert RecursoVisual.objects.count() == recursos_antes
    for vieja, copia in zip(original.preguntas.order_by("id"), nuevo.preguntas.order_by("id")):
        assert copia.texto == vieja.texto
        assert list(copia.opciones.values_list("texto", "es_correcta")) == list(vieja.opciones.values_list("texto", "es_correcta"))
    assert list(nuevo.diccionario.values_list("titulo", "orden")) == list(original.diccionario.values_list("titulo", "orden"))
    assert AuditoriaCurso.objects.get(curso_id=nuevo.id, operacion="alta").usuario == creador


@pytest.mark.parametrize("slug, mensaje", [
    ("original", "Ya existe un curso con ese slug"),
    ("con espacios", "solo admite letras"),
    ("", "solo admite letras"),
])
def test_clonar_con_slug_invalido_es_rechazado(crear_curso, slug, mensaje):
    original = crear_curso("original", preguntas=1, palabras=0)
    with la_base_rechaza(mensaje):
        proc.clonar_curso(original.id, slug)


def test_clonar_curso_inexistente(db):
    with la_base_rechaza("no existe"):
        proc.clonar_curso(999999, "lo-que-sea")


# ----------------------------------------- 5. purgar_intentos_abandonados


def _sesion(usuario, curso, total, letras, dias):
    sesion = EvaluacionCamara.objects.create(
        usuario=usuario, curso=curso, total=total, correctas=0, porcentaje=0, aprobado=False, umbral_aplicado=70
    )
    for n in range(letras):
        IntentoCamara.objects.create(evaluacion=sesion, orden=n, letra_objetivo="A", acerto=False, tiempo_ms=1000)
    EvaluacionCamara.objects.filter(pk=sesion.pk).update(fecha=hace_dias(dias))
    return sesion


def test_purgar_solo_borra_lo_abandonado_y_viejo(estudiante, crear_curso):
    curso = crear_curso("purga", preguntas=1, palabras=0)
    viejo_abierto = _intento(estudiante, curso, aciertos=0, total=1)
    reciente_abierto = _intento(estudiante, curso, aciertos=0, total=1)
    viejo_cerrado = _intento(estudiante, curso, aciertos=1, total=1, finalizado=True)
    IntentoEvaluacion.objects.filter(pk__in=[viejo_abierto.pk, viejo_cerrado.pk]).update(fecha_actualizacion=hace_dias(40))

    incompleta_vieja = _sesion(estudiante, curso, total=3, letras=1, dias=40)
    completa_vieja = _sesion(estudiante, curso, total=1, letras=1, dias=40)
    incompleta_reciente = _sesion(estudiante, curso, total=3, letras=1, dias=1)

    assert proc.purgar_intentos_abandonados(30) == {"intentos_borrados": 1, "sesiones_camara_borradas": 1}
    assert set(IntentoEvaluacion.objects.values_list("pk", flat=True)) == {reciente_abierto.pk, viejo_cerrado.pk}
    assert set(EvaluacionCamara.objects.values_list("pk", flat=True)) == {completa_vieja.pk, incompleta_reciente.pk}
    assert not IntentoCamara.objects.filter(evaluacion_id=incompleta_vieja.pk).exists()


def test_purgar_con_dias_invalidos(db):
    with la_base_rechaza("al menos 1"):
        proc.purgar_intentos_abandonados(0)
