"""
Subida de imagenes (apps/cursos/archivos.py; docs/SEGURIDAD.md, seccion 9).

Cada endpoint que recibe archivos rechaza lo que no es una imagen de verdad,
aunque se haya renombrado, y guarda con un nombre generado por el servidor.
"""

import io
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

pytestmark = pytest.mark.django_db

HTML_MALICIOSO = b"<html><script>fetch('/admin/')</script></html>"
SVG_MALICIOSO = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def archivo(nombre, contenido, tipo="image/png"):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


def imagen(formato, nombre, relleno=0):
    """Imagen real; `relleno` agrega bytes al final (la imagen sigue siendo valida)."""
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="teal").save(buffer, format=formato)
    return archivo(nombre, buffer.getvalue() + b"\x00" * relleno)


@pytest.fixture
def subir(como, interprete, administrador, curso):
    """subir(destino, archivo) -> respuesta del endpoint correspondiente."""
    palabra = curso.diccionario.first()
    pregunta = curso.preguntas.first()

    def _subir(destino, adjunto):
        if destino == "gif_palabra":
            return como(interprete).post(f"/api/panel/diccionario/{palabra.id}/gif/", {"gif": adjunto}, format="multipart")
        if destino == "gif_pregunta":
            return como(interprete).post(f"/api/panel/preguntas/{pregunta.id}/gif/", {"gif": adjunto}, format="multipart")
        if destino == "contenido":
            return como(interprete).post("/api/panel/archivos/", {"archivo": adjunto}, format="multipart")
        if destino == "biblioteca":
            return como(interprete).post("/api/panel/recursos/", {"nombre": "x", "archivo": adjunto}, format="multipart")
        if destino == "foto_perfil":
            return como(administrador).patch("/api/auth/perfil/", {"foto_perfil": adjunto}, format="multipart")
        raise AssertionError(destino)
    return _subir


TODOS = ["gif_palabra", "gif_pregunta", "contenido", "biblioteca", "foto_perfil"]


@pytest.mark.parametrize("destino", TODOS)
@pytest.mark.parametrize("nombre, contenido", [
    ("ataque.html", HTML_MALICIOSO),
    ("dibujo.svg", SVG_MALICIOSO),
    ("programa.exe", b"MZ\x90\x00" + b"\x00" * 64),
])
def test_rechaza_extensiones_que_no_son_imagen(subir, destino, nombre, contenido):
    assert subir(destino, archivo(nombre, contenido)).status_code == 400


@pytest.mark.parametrize("destino", TODOS)
def test_rechaza_html_renombrado_como_imagen(subir, destino):
    """La extension miente: el contenido se revisa con Pillow."""
    nombre = "sena.gif" if destino.startswith("gif") else "foto.png"
    respuesta = subir(destino, archivo(nombre, HTML_MALICIOSO))
    assert respuesta.status_code == 400
    # Nuestro mensaje, o el de ImageField de Django, que revisa primero en biblioteca y perfil.
    assert "imagen válida" in str(respuesta.data)


@pytest.mark.parametrize("destino", TODOS)
def test_rechaza_imagen_truncada(subir, destino):
    nombre = "sena.gif" if destino.startswith("gif") else "foto.png"
    completa = imagen("GIF" if destino.startswith("gif") else "PNG", nombre).read()
    assert subir(destino, archivo(nombre, completa[: len(completa) // 2])).status_code == 400


@pytest.mark.parametrize("destino", ["gif_palabra", "gif_pregunta"])
def test_los_gifs_solo_aceptan_gif(subir, destino):
    assert subir(destino, imagen("PNG", "sena.png")).status_code == 400


@pytest.mark.parametrize("destino", ["contenido", "biblioteca"])
def test_rechaza_contenido_que_no_corresponde_a_la_extension(subir, destino):
    respuesta = subir(destino, imagen("PNG", "foto.jpg"))
    assert respuesta.status_code == 400
    assert "no corresponde a su extensión" in str(respuesta.data)


@pytest.mark.parametrize("destino", ["gif_palabra", "contenido", "biblioteca"])
def test_rechaza_archivos_de_mas_de_10_mb(subir, destino):
    formato, nombre = ("GIF", "sena.gif") if destino.startswith("gif") else ("PNG", "foto.png")
    respuesta = subir(destino, imagen(formato, nombre, relleno=10 * 1024 * 1024))
    assert respuesta.status_code == 400
    assert "10 MB" in str(respuesta.data)


def test_foto_de_perfil_maximo_5_mb(subir):
    respuesta = subir("foto_perfil", imagen("PNG", "yo.png", relleno=5 * 1024 * 1024))
    assert respuesta.status_code == 400
    assert "5 MB" in str(respuesta.data)


@pytest.mark.parametrize("destino, campo", [
    ("gif_palabra", "video_gif"),
    ("gif_pregunta", "video"),
    ("contenido", "archivo_url"),
    ("biblioteca", "archivo_url"),
    ("foto_perfil", "foto_perfil_url"),
])
def test_imagen_valida_se_guarda_con_nombre_del_servidor(subir, destino, campo):
    """El nombre original (que el usuario controla) nunca llega al disco."""
    formato, nombre = ("GIF", "../../config/mi sena.gif") if destino.startswith("gif") else ("PNG", "../../config/mi foto.png")
    respuesta = subir(destino, imagen(formato, nombre))
    assert respuesta.status_code in (200, 201), respuesta.data
    guardado = Path(respuesta.data[campo]).name
    assert "mi" not in guardado and "config" not in respuesta.data[campo]
    assert len(Path(guardado).stem) == 32                       # UUID en hexadecimal
    assert any(Path(settings.MEDIA_ROOT).rglob(guardado))       # quedo dentro de MEDIA_ROOT
