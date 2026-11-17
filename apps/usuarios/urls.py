from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenRefreshView,
    TokenVerifyView,
)

from . import views

urlpatterns = [
    path("registro/", views.RegistroView.as_view(), name="registro"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(permission_classes=[AllowAny]), name="token_refresh"),
    path("verify/", TokenVerifyView.as_view(permission_classes=[AllowAny]), name="token_verify"),
    # Cierre de sesion: recibe {"refresh": ...} y lo agrega a la lista negra.
    # AllowAny porque el access puede haber vencido; tener el refresh basta.
    path("logout/", TokenBlacklistView.as_view(permission_classes=[AllowAny]), name="logout"),
    path("perfil/", views.PerfilView.as_view(), name="perfil"),
    path(
        "cambiar-password/",
        views.CambiarPasswordView.as_view(),
        name="cambiar_password",
    ),
    path(
        "recuperar/solicitar/",
        views.SolicitarRecuperacionView.as_view(),
        name="recuperar_solicitar",
    ),
    path(
        "recuperar/confirmar/",
        views.ConfirmarRecuperacionView.as_view(),
        name="recuperar_confirmar",
    ),
]
