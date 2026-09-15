from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PerfilUsuario
from .serializers import (
    ActualizarPerfilSerializer,
    CambiarPasswordSerializer,
    ConfirmarRecuperacionSerializer,
    LoginSerializer,
    PerfilSerializer,
    RegistroSerializer,
    SolicitarRecuperacionSerializer,
)


class RegistroView(APIView):
    """POST /api/auth/registro/"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        return Response(
            {
                "mensaje": "Usuario registrado con exito.",
                "usuario": PerfilSerializer(perfil, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ -> access, refresh y datos del usuario."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


class PerfilView(APIView):
    """GET y PATCH /api/auth/perfil/"""

    permission_classes = [IsAuthenticated]

    def get_perfil(self, request):
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
        return perfil

    def get(self, request):
        perfil = self.get_perfil(request)
        return Response(PerfilSerializer(perfil, context={"request": request}).data)

    def patch(self, request):
        perfil = self.get_perfil(request)
        serializer = ActualizarPerfilSerializer(
            perfil, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        perfil = serializer.save()
        return Response(PerfilSerializer(perfil, context={"request": request}).data)


class CambiarPasswordView(APIView):
    """POST /api/auth/cambiar-password/ (usuario autenticado)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CambiarPasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"mensaje": "Contrasena actualizada. Vuelve a iniciar sesion."})


class SolicitarRecuperacionView(APIView):
    """
    POST /api/auth/recuperar/solicitar/

    En produccion el token se enviaria por correo. En desarrollo (DEBUG=True) se
    devuelve en la respuesta para poder probar el flujo completo sin SMTP.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SolicitarRecuperacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.generar_token()

        respuesta = {
            "mensaje": "Si el correo esta registrado, enviamos las instrucciones de recuperacion."
        }
        if settings.DEBUG and datos:
            respuesta["debug"] = datos
        return Response(respuesta)


class ConfirmarRecuperacionView(APIView):
    """POST /api/auth/recuperar/confirmar/"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmarRecuperacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"mensaje": "Contrasena restablecida. Ya puedes iniciar sesion."})
