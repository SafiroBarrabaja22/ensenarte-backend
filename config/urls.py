"""Rutas raiz del proyecto. Todo lo publico cuelga de /api/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.usuarios.urls")),
    path("api/evaluacion-camara/", include("apps.evaluacion_camara.urls")),
    path("api/", include("apps.cursos.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
