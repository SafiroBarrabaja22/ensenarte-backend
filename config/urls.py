"""Rutas raiz del proyecto. Todo lo publico cuelga de /api/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.evaluacion_camara.views import EvaluacionCamaraListCreateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.usuarios.urls")),
    path("api/", include("apps.cursos.urls")),
    path(
        "api/evaluacion-camara/",
        EvaluacionCamaraListCreateView.as_view(),
        name="evaluacion_camara",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
