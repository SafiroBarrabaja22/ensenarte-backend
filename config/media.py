"""
Sirve /media/ (archivos subidos por los usuarios) cuando no hay otro servidor
web delante, como en produccion con Tailscale Funnel -> gunicorn.

Los archivos subidos se sirven desde el MISMO dominio que el admin de Django.
Si alguien subiera un .html o un .svg con JavaScript, el navegador podria
ejecutarlo con la sesion del admin. Por eso cada respuesta lleva:

- Content-Security-Policy con `sandbox`: el documento no ejecuta scripts ni
  comparte origen con el sitio. Una imagen dentro de <img> no se ve afectada.
- X-Content-Type-Options: nosniff (ya la pone SecurityMiddleware), para que el
  navegador no "adivine" que un archivo es HTML.

Se activa con SERVIR_MEDIA (por defecto True). django.views.static.serve ya
impide salirse de MEDIA_ROOT con "../".
"""

from django.conf import settings
from django.http import Http404
from django.views.static import serve

POLITICA_MEDIA = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


def servir_media(request, path):
    if not settings.SERVIR_MEDIA:
        raise Http404("La carpeta media no se sirve desde Django.")
    respuesta = serve(request, path, document_root=settings.MEDIA_ROOT)
    respuesta["Content-Security-Policy"] = POLITICA_MEDIA
    # Los nombres de la biblioteca son UUID y no cambian; los demas pueden
    # reemplazarse, asi que la cache es corta.
    respuesta["Cache-Control"] = "public, max-age=3600"
    return respuesta
