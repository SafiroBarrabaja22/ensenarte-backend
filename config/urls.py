"""Rutas raiz del proyecto. Todo lo publico cuelga de /api/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import AllowAny

from apps.evaluacion_camara.views import EvaluacionCamaraListCreateView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Documentacion OpenAPI. Publica: solo describe la API, no da acceso a
    # datos; los endpoints siguen exigiendo token y rol al probarlos.
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="esquema_api"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="esquema_api", permission_classes=[AllowAny]),
        name="docs_swagger",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="esquema_api", permission_classes=[AllowAny]),
        name="docs_redoc",
    ),
    path("api/auth/", include("apps.usuarios.urls")),
    path("api/reportes/", include("apps.reportes.urls")),
    path("api/", include("apps.cursos.urls")),
    path(
        "api/evaluacion-camara/",
        EvaluacionCamaraListCreateView.as_view(),
        name="evaluacion_camara",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
