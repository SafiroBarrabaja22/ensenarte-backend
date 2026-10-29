"""Rutas raiz del proyecto. Todo lo publico cuelga de /api/."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.usuarios.urls")),
    path("api/evaluacion-camara/", include("apps.evaluacion_camara.urls")),
    path("api/", include("apps.cursos.urls")),
]
