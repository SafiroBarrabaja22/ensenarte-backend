from django.urls import path

from . import views

urlpatterns = [
    path("registro/", views.RegistroView.as_view(), name="registro"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefrescarTokenView.as_view(), name="token_refresh"),
    path("verify/", views.VerificarTokenView.as_view(), name="token_verify"),
    # Cierre de sesion: lista negra del refresh (ver CerrarSesionView).
    path("logout/", views.CerrarSesionView.as_view(), name="logout"),
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
