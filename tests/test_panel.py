"""Panel administrativo: CRUD, reglas de negocio, archivos, biblioteca y reportes."""

import pytest

from apps.cursos.models import Curso, OpcionPregunta, PalabraDiccionario, Pregunta, RecursoVisual

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ Cursos


def test_crud_completo_de_cursos(como, creador):
    cliente = como(creador)
    creado = cliente.post(
        "/api/panel/cursos/",
        {"nombre": "colores", "titulo": "Colores", "portada_curso": "colores.png", "preguntas_por_evaluacion": 5},
        format="json",
    )
    assert creado.status_code == 201
    assert creado.data["creado_por"] == "creador"
    pk = creado.data["id"]

    assert cliente.get("/api/panel/cursos/").data["count"] == 1
    assert cliente.get(f"/api/panel/cursos/{pk}/").data["titulo"] == "Colores"

    editado = cliente.patch(f"/api/panel/cursos/{pk}/", {"titulo": "Colores básicos"}, format="json")
    assert editado.data["titulo"] == "Colores básicos"

    reemplazado = cliente.put(
        f"/api/panel/cursos/{pk}/",
        {"nombre": "colores", "titulo": "Colores", "portada_curso": "otra.png", "activo": False},
        format="json",
    )
    assert reemplazado.status_code == 200
    assert reemplazado.data["activo"] is False

    assert cliente.delete(f"/api/panel/cursos/{pk}/").status_code == 204
    assert not Curso.objects.exists()


@pytest.mark.parametrize("datos, campo", [
    ({"titulo": "Sin slug", "portada_curso": "x.png"}, "nombre"),
    ({"nombre": "con espacios", "titulo": "X", "portada_curso": "x.png"}, "nombre"),
    ({"nombre": "abecedario", "titulo": "Duplicado", "portada_curso": "x.png"}, "nombre"),
    ({"nombre": "nuevo", "titulo": "X", "portada_curso": "x.png", "insignia_100": 999}, "insignia_100"),
])
def test_crear_curso_invalido_responde_400(como, creador, curso, datos, campo):
    respuesta = como(creador).post("/api/panel/cursos/", datos, format="json")
    assert respuesta.status_code == 400
    assert campo in respuesta.data


def test_curso_inexistente_responde_404(como, creador):
    assert como(creador).get("/api/panel/cursos/999/").status_code == 404
    assert como(creador).delete("/api/panel/cursos/999/").status_code == 404


def test_curso_con_insignia_100_muestra_nombre_y_url(como, administrador, png):
    cliente = como(administrador)
    insignia = cliente.post(
        "/api/panel/recursos/", {"nombre": "Oro", "archivo": png(), "categoria": "curso_100"}, format="multipart"
    ).data
    curso = cliente.post(
        "/api/panel/cursos/",
        {"nombre": "oro", "titulo": "Oro", "portada_curso": "x.png", "insignia_100": insignia["id"]},
        format="json",
    ).data
    assert curso["insignia_100_nombre"] == "Oro"
    assert curso["insignia_100_url"] == insignia["archivo_url"]
    publico = cliente.get("/api/cursos/oro/").data
    assert publico["insignia_100"]["imagen"] == insignia["archivo_url"]


# ------------------------------------------------------------------ Preguntas y opciones


def test_crud_de_preguntas(como, profesor, curso):
    cliente = como(profesor)
    creada = cliente.post("/api/panel/preguntas/", {"curso": curso.id, "texto": "¿Nueva?"}, format="json")
    assert creada.status_code == 201
    pk = creada.data["id"]

    listado = cliente.get(f"/api/panel/preguntas/?curso={curso.id}").data
    assert len(listado) == 4 and all("opciones" in p for p in listado)

    assert cliente.patch(f"/api/panel/preguntas/{pk}/", {"texto": "¿Editada?"}, format="json").data["texto"] == "¿Editada?"
    assert cliente.delete(f"/api/panel/preguntas/{pk}/").status_code == 204


def test_crear_pregunta_sin_curso_responde_400(como, profesor):
    respuesta = como(profesor).post("/api/panel/preguntas/", {"texto": "¿Huérfana?"}, format="json")
    assert respuesta.status_code == 400
    assert "curso" in respuesta.data


def test_quinta_opcion_de_una_pregunta_responde_400(como, profesor, curso):
    pregunta = Pregunta.objects.filter(curso=curso).first()
    assert pregunta.opciones.count() == 4
    respuesta = como(profesor).post(
        "/api/panel/opciones/", {"pregunta": pregunta.id, "texto": "E"}, format="json"
    )
    assert respuesta.status_code == 400
    assert "maximo 4 opciones" in str(respuesta.data)


def test_editar_una_opcion_existente_no_cuenta_como_quinta(como, profesor, curso):
    opcion = OpcionPregunta.objects.filter(pregunta__curso=curso).first()
    respuesta = como(profesor).patch(f"/api/panel/opciones/{opcion.id}/", {"texto": "Editada"}, format="json")
    assert respuesta.status_code == 200


def test_solo_puede_haber_una_opcion_correcta(como, profesor, curso):
    pregunta = Pregunta.objects.filter(curso=curso).first()
    otra = pregunta.opciones.filter(es_correcta=False).first()
    cliente = como(profesor)
    assert cliente.patch(f"/api/panel/opciones/{otra.id}/", {"es_correcta": True}, format="json").status_code == 200
    assert list(pregunta.opciones.filter(es_correcta=True)) == [otra]

    nueva_pregunta = Pregunta.objects.create(curso=curso, texto="¿Otra?")
    cliente.post("/api/panel/opciones/", {"pregunta": nueva_pregunta.id, "texto": "A", "es_correcta": True}, format="json")
    cliente.post("/api/panel/opciones/", {"pregunta": nueva_pregunta.id, "texto": "B", "es_correcta": True}, format="json")
    assert nueva_pregunta.opciones.filter(es_correcta=True).count() == 1
    assert cliente.get(f"/api/panel/opciones/?pregunta={nueva_pregunta.id}").data["count"] == 2


# ------------------------------------------------------------------ Diccionario


def test_crud_del_diccionario_y_orden(como, profesor, curso):
    cliente = como(profesor)
    nueva = cliente.post(
        "/api/panel/diccionario/",
        {"curso": curso.id, "titulo": "Hola", "imagen_frontal": "hola.png", "video_gif": "hola.gif"},
        format="json",
    )
    assert nueva.status_code == 201
    assert nueva.data["orden"] == 3  # queda al final

    ids = [p["id"] for p in cliente.get(f"/api/panel/diccionario/?curso={curso.id}").data]
    invertidos = list(reversed(ids))
    assert cliente.post("/api/panel/diccionario/reordenar/", {"curso": curso.id, "ids": invertidos}, format="json").status_code == 204
    assert list(PalabraDiccionario.objects.filter(curso=curso).values_list("id", flat=True)) == invertidos

    assert cliente.patch(f"/api/panel/diccionario/{nueva.data['id']}/", {"titulo": "Hola!"}, format="json").status_code == 200
    assert cliente.delete(f"/api/panel/diccionario/{nueva.data['id']}/").status_code == 204


@pytest.mark.parametrize("cuerpo", [
    {"ids": [1]},
    {"curso": 1},
    {"curso": 1, "ids": "no-es-lista"},
    {"curso": 1, "ids": ["a", "b"]},
    {"curso": 1, "ids": [1]},  # faltan palabras del curso
])
def test_reordenar_con_datos_invalidos_responde_400(como, profesor, curso, cuerpo):
    if "curso" in cuerpo:
        cuerpo = {**cuerpo, "curso": curso.id}
    assert como(profesor).post("/api/panel/diccionario/reordenar/", cuerpo, format="json").status_code == 400


def test_reordenar_curso_inexistente_responde_404(como, creador):
    respuesta = como(creador).post("/api/panel/diccionario/reordenar/", {"curso": 999, "ids": []}, format="json")
    assert respuesta.status_code == 404


# ------------------------------------------------------------------ Gifs y archivos


def test_subir_gif_de_palabra_y_de_pregunta(como, profesor, curso, gif):
    cliente = como(profesor)
    palabra = curso.diccionario.first()
    pregunta = curso.preguntas.first()
    respuesta = cliente.post(f"/api/panel/diccionario/{palabra.id}/gif/", {"gif": gif()}, format="multipart")
    assert respuesta.status_code == 200
    assert "diccionario_gifs/" in respuesta.data["video_gif"]
    respuesta = cliente.post(f"/api/panel/preguntas/{pregunta.id}/gif/", {"gif": gif()}, format="multipart")
    assert respuesta.status_code == 200
    assert "evaluacion_gifs/" in respuesta.data["video"]


@pytest.mark.parametrize("ruta", ["diccionario", "preguntas"])
def test_subir_gif_sin_archivo_responde_400(como, interprete, curso, ruta):
    objeto = curso.diccionario.first() if ruta == "diccionario" else curso.preguntas.first()
    respuesta = como(interprete).post(f"/api/panel/{ruta}/{objeto.id}/gif/", {}, format="multipart")
    assert respuesta.status_code == 400


@pytest.mark.parametrize("ruta", ["diccionario", "preguntas"])
def test_subir_gif_a_objeto_inexistente_responde_404(como, interprete, gif, ruta):
    respuesta = como(interprete).post(f"/api/panel/{ruta}/999/gif/", {"gif": gif()}, format="multipart")
    assert respuesta.status_code == 404


def test_subir_archivo_de_contenido(como, profesor, png):
    respuesta = como(profesor).post("/api/panel/archivos/", {"archivo": png()}, format="multipart")
    assert respuesta.status_code == 201
    assert respuesta.data["archivo_url"].startswith("/media/contenido/")
    assert not RecursoVisual.objects.exists()  # no entra a la biblioteca


def test_subir_archivo_invalido_responde_400(como, profesor):
    from django.core.files.uploadedfile import SimpleUploadedFile

    cliente = como(profesor)
    assert cliente.post("/api/panel/archivos/", {}, format="multipart").status_code == 400
    texto = SimpleUploadedFile("notas.txt", b"hola", content_type="text/plain")
    assert cliente.post("/api/panel/archivos/", {"archivo": texto}, format="multipart").status_code == 400
    grande = SimpleUploadedFile("enorme.png", b"0" * (10 * 1024 * 1024 + 1), content_type="image/png")
    assert cliente.post("/api/panel/archivos/", {"archivo": grande}, format="multipart").status_code == 400


# ------------------------------------------------------------------ Biblioteca visual


def test_biblioteca_crear_filtrar_editar_y_borrar(como, interprete, png, gif):
    cliente = como(interprete)
    imagen = cliente.post("/api/panel/recursos/", {"nombre": "Mano abierta", "archivo": png()}, format="multipart")
    animado = cliente.post("/api/panel/recursos/", {"nombre": "Saludo", "archivo": gif(), "categoria": "avatar"}, format="multipart")
    assert imagen.status_code == animado.status_code == 201
    assert imagen.data["extension"] == "png"

    assert [r["nombre"] for r in cliente.get("/api/panel/recursos/?q=mano").data] == ["Mano abierta"]
    assert [r["nombre"] for r in cliente.get("/api/panel/recursos/?extension=gif").data] == ["Saludo"]
    assert [r["nombre"] for r in cliente.get("/api/panel/recursos/?categoria=avatar").data] == ["Saludo"]
    paginado = cliente.get("/api/panel/recursos/?page=1").data
    assert paginado["count"] == 2

    editado = cliente.patch(f"/api/panel/recursos/{imagen.data['id']}/", {"nombre": "Mano"}, format="json")
    assert editado.data["nombre"] == "Mano"
    assert cliente.get(f"/api/panel/recursos/{imagen.data['id']}/").status_code == 200
    assert cliente.delete(f"/api/panel/recursos/{imagen.data['id']}/").status_code == 204


@pytest.mark.parametrize("datos", [
    {"nombre": "Sin archivo"},
    {"nombre": "Texto", "archivo": "texto"},
])
def test_biblioteca_datos_invalidos_responde_400(como, interprete, datos):
    from django.core.files.uploadedfile import SimpleUploadedFile

    if datos.get("archivo") == "texto":
        datos = {**datos, "archivo": SimpleUploadedFile("a.txt", b"x", content_type="text/plain")}
    assert como(interprete).post("/api/panel/recursos/", datos, format="multipart").status_code == 400


def test_biblioteca_formato_no_permitido_responde_400(como, interprete):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, format="PNG")
    disfrazado = SimpleUploadedFile("imagen.svg", buffer.getvalue(), content_type="image/svg+xml")
    respuesta = como(interprete).post("/api/panel/recursos/", {"nombre": "SVG", "archivo": disfrazado}, format="multipart")
    assert respuesta.status_code == 400
    assert "archivo" in respuesta.data


def test_no_se_borra_un_recurso_en_uso(como, interprete, curso, png):
    cliente = como(interprete)
    recurso = cliente.post("/api/panel/recursos/", {"nombre": "Portada", "archivo": png()}, format="multipart").data
    curso.portada_curso = recurso["archivo_url"]
    curso.save()
    assert cliente.delete(f"/api/panel/recursos/{recurso['id']}/").status_code == 409
    assert RecursoVisual.objects.filter(pk=recurso["id"]).exists()


def test_recurso_inexistente_responde_404(como, interprete):
    assert como(interprete).get("/api/panel/recursos/999/").status_code == 404


# ------------------------------------------------------------------ Reportes


def test_resumen_del_panel(como, creador, curso, estudiante):
    datos = como(creador).get("/api/panel/resumen/").data
    assert datos["total_cursos"] == 1
    assert datos["total_preguntas"] == 3
    assert datos["total_palabras"] == 2
    assert datos["total_usuarios"] >= 3


def test_estrellas_de_estudiantes_ordenadas(como, profesor, estudiante, crear_usuario):
    otro = crear_usuario(nombre="otro")
    otro.perfil.estrellas = 3
    otro.perfil.save()
    datos = como(profesor).get("/api/panel/estudiantes/estrellas/").data
    assert datos[0] == {"usuario": "otro", "correo": "otro@correo.com", "estrellas": 3}
