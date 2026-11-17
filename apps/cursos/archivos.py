"""
Validacion de las imagenes que suben los usuarios (unica fuente).

Lo usan la biblioteca (RecursoVisual), las imagenes de contenido, los gifs de
palabras y preguntas y la foto de perfil. Explicacion en docs/SEGURIDAD.md,
seccion 9.

Por cada archivo se comprueba:
1. Que la extension este permitida. No se admite SVG: es XML y puede llevar
   JavaScript.
2. El tamano maximo.
3. Que el CONTENIDO sea de verdad una imagen del formato que dice la
   extension. Pillow la abre y la verifica: un .html o un .exe renombrado a
   .png se rechaza. Pillow tambien frena las "bombas de descompresion"
   (imagenes pequenas en disco que ocupan gigas en memoria al abrirlas).
4. El nombre con que se guarda lo genera el servidor (UUID + extension): el
   nombre original no llega al disco.

Solo se admiten formatos que los navegadores muestran y que Pillow puede
verificar. TIFF, HEIC y AVIF quedaron fuera por eso.
"""

import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

# extension -> formato que debe detectar Pillow en el contenido
FORMATOS_IMAGEN = {
    ".png": "PNG",
    ".gif": "GIF",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".jfif": "JPEG",
    ".webp": "WEBP",
    ".bmp": "BMP",
}
FORMATOS_GIF = {".gif": "GIF"}

MAX_BYTES_IMAGEN = 10 * 1024 * 1024        # 10 MB: biblioteca, contenido y gifs
MAX_BYTES_FOTO_PERFIL = 5 * 1024 * 1024    # 5 MB


def _nombres(formatos):
    return ", ".join(sorted({extension.lstrip(".").upper() for extension in formatos}))


def validar_imagen(archivo, formatos=FORMATOS_IMAGEN, max_bytes=MAX_BYTES_IMAGEN):
    """
    Lanza serializers.ValidationError si el archivo no es una imagen permitida.
    Devuelve la extension (en minusculas) para armar el nombre seguro.
    """
    extension = Path(archivo.name or "").suffix.lower()
    if extension not in formatos:
        raise serializers.ValidationError(f"Formato no permitido. Formatos aceptados: {_nombres(formatos)}.")
    if archivo.size > max_bytes:
        raise serializers.ValidationError(f"El archivo no puede superar {max_bytes // (1024 * 1024)} MB.")
    try:
        archivo.seek(0)
        with Image.open(archivo) as imagen:
            formato = imagen.format
            imagen.verify()   # recorre el archivo: detecta datos corruptos o truncados
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise serializers.ValidationError("El archivo no es una imagen válida.")
    finally:
        archivo.seek(0)
    if formato != formatos[extension]:
        raise serializers.ValidationError(
            f"El contenido del archivo no corresponde a su extensión {extension}."
        )
    return extension


def nombre_seguro(extension):
    """Nombre generado por el servidor; el del usuario nunca se usa."""
    return f"{uuid.uuid4().hex}{extension}"
