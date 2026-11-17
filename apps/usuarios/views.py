from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from apps.correos.servicio import al_confirmar, enviar_bienvenida
from config.openapi import (
    EJEMPLO_PERFIL,
    ETIQUETA_AUTENTICACION,
    TOKEN_EJEMPLO,
    error_400,
    error_401,
    ok,
    respuestas,
)

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

MensajeSerializer = inline_serializer("Mensaje", {"mensaje": serializers.CharField()})

TokensSerializer = inline_serializer(
    "TokensLogin",
    {
        "access": serializers.CharField(help_text="Token de acceso (15 min). Va en `Authorization: Bearer`."),
        "refresh": serializers.CharField(help_text="Token para renovar la sesión (7 días, se rota)."),
        "usuario": PerfilSerializer(),
    },
)

ERROR_401_CREDENCIALES = error_401(
    "Usuario o contraseña incorrectos, o cuenta inactiva.",
    {"detail": "No se encontró una cuenta de usuario activa para las credenciales dadas"},
)

ERROR_401_TOKEN = error_401(
    "El token es inválido, venció o ya fue usado o cerrado.",
    {"detail": "El token no es válido o ha expirado", "code": "token_not_valid"},
)


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Registrar estudiante",
    auth=[],  # publico: sin candado en Swagger UI
    description="Crea una cuenta nueva con el rol **Estudiante**. Público. "
    "La contraseña pasa por los validadores de Django (mínimo 8 caracteres, "
    "no solo numérica, no común, distinta del usuario).",
    request=RegistroSerializer,
    responses=respuestas(
        ok(
            inline_serializer("Registro", {"mensaje": serializers.CharField(), "usuario": PerfilSerializer()}),
            {"mensaje": "Usuario registrado con exito.", "usuario": {**EJEMPLO_PERFIL, "estrellas": 0}},
            codigo=201,
            descripcion="Cuenta creada.",
        ),
        error_400({"nombre": ["El nombre de usuario ya existe."], "password": ["Esta contraseña es demasiado común."]}),
    ),
)
class RegistroView(APIView):
    """POST /api/auth/registro/"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Tras el commit y sin propagar errores: un SMTP caido no impide registrarse.
        al_confirmar(enviar_bienvenida, user)
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        return Response(
            {
                "mensaje": "Usuario registrado con exito.",
                "usuario": PerfilSerializer(perfil, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Iniciar sesión",
    description="Devuelve el par de tokens JWT y el perfil del usuario (con sus `roles`). "
    "Copia `access` y pégalo en el botón **Authorize** de esta página.",
    responses=respuestas(
        ok(TokensSerializer, {"access": TOKEN_EJEMPLO, "refresh": TOKEN_EJEMPLO, "usuario": EJEMPLO_PERFIL}),
        error_400({"username": ["Este campo es requerido."]}),
        ERROR_401_CREDENCIALES,
    ),
)
class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ -> access, refresh y datos del usuario."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Renovar el token de acceso",
    description="Recibe el `refresh` y devuelve un `access` **y** un `refresh` nuevos. "
    "El refresh enviado queda invalidado (rotación): guarda siempre el nuevo.",
    responses=respuestas(
        ok(
            inline_serializer("TokensRenovados", {"access": serializers.CharField(), "refresh": serializers.CharField()}),
            {"access": TOKEN_EJEMPLO, "refresh": TOKEN_EJEMPLO},
        ),
        error_400({"refresh": ["Este campo es requerido."]}),
        ERROR_401_TOKEN,
    ),
)
class RefrescarTokenView(TokenRefreshView):
    permission_classes = [AllowAny]


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Verificar un token",
    description="Responde 200 con cuerpo vacío si el token (access o refresh) es válido.",
    responses=respuestas(
        ok(OpenApiTypes.OBJECT, {}, descripcion="El token es válido. Cuerpo vacío."),
        error_400({"token": ["Este campo es requerido."]}),
        ERROR_401_TOKEN,
    ),
)
class VerificarTokenView(TokenVerifyView):
    permission_classes = [AllowAny]


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Cerrar sesión",
    description="Agrega el `refresh` a la lista negra: deja de servir para renovar la sesión. "
    "Público porque el access puede haber vencido; tener el refresh basta.",
    responses=respuestas(
        ok(OpenApiTypes.OBJECT, {}, descripcion="Sesión cerrada. Cuerpo vacío."),
        error_400({"refresh": ["Este campo es requerido."]}),
        ERROR_401_TOKEN,
    ),
)
class CerrarSesionView(TokenBlacklistView):
    permission_classes = [AllowAny]


class PerfilView(APIView):
    """GET y PATCH /api/auth/perfil/"""

    permission_classes = [IsAuthenticated]

    def get_perfil(self, request):
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)
        return perfil

    @extend_schema(
        tags=[ETIQUETA_AUTENTICACION],
        summary="Ver mi perfil",
        description="Datos del usuario autenticado, incluido el arreglo `roles`. "
        "Cualquier usuario con sesión, tenga o no rol.",
        responses=respuestas(ok(PerfilSerializer, EJEMPLO_PERFIL), error_401()),
    )
    def get(self, request):
        perfil = self.get_perfil(request)
        return Response(PerfilSerializer(perfil, context={"request": request}).data)

    @extend_schema(
        tags=[ETIQUETA_AUTENTICACION],
        summary="Editar mi perfil",
        description="Actualización parcial: nombre, correo, avatar (nombre de archivo o ruta de "
        "la biblioteca) y/o foto de perfil. Para subir foto usa `multipart/form-data`.",
        request={
            "application/json": ActualizarPerfilSerializer,
            "multipart/form-data": ActualizarPerfilSerializer,
        },
        responses=respuestas(
            ok(PerfilSerializer, {**EJEMPLO_PERFIL, "avatar": "opcionUnoPerfil.png"}),
            error_400({"correo": ["Ese correo ya esta registrado."]}),
            error_401(),
        ),
    )
    def patch(self, request):
        perfil = self.get_perfil(request)
        serializer = ActualizarPerfilSerializer(
            perfil, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        perfil = serializer.save()
        return Response(PerfilSerializer(perfil, context={"request": request}).data)


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Cambiar mi contraseña",
    description="Requiere la contraseña actual. Después conviene volver a iniciar sesión.",
    request=CambiarPasswordSerializer,
    responses=respuestas(
        ok(MensajeSerializer, {"mensaje": "Contrasena actualizada. Vuelve a iniciar sesion."}),
        error_400({"password_actual": ["La contrasena actual no es correcta."]}),
        error_401(),
    ),
)
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


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Solicitar recuperación de contraseña",
    auth=[],  # publico: sin candado en Swagger UI
    description="Paso 1. Siempre responde lo mismo, exista o no el correo (para no revelar "
    "qué cuentas existen). Con `DEBUG=True` agrega `debug` con `uid` y `token` para probar "
    "el paso 2 sin servidor de correo. Hoy no se envía ningún correo.",
    request=SolicitarRecuperacionSerializer,
    responses=respuestas(
        ok(
            inline_serializer(
                "RecuperacionSolicitada",
                {
                    "mensaje": serializers.CharField(),
                    "debug": inline_serializer(
                        "RecuperacionDebug", {"uid": serializers.CharField(), "token": serializers.CharField()}, required=False
                    ),
                },
            ),
            {
                "mensaje": "Si el correo esta registrado, enviamos las instrucciones de recuperacion.",
                "debug": {"uid": "Mw", "token": "c4k2j1-0f3b8e2d1a9c7e6b5d4f3a2b1c0d9e8f"},
            },
        ),
        error_400({"correo": ["Introduzca una dirección de correo electrónico válida."]}),
    ),
)
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


@extend_schema(
    tags=[ETIQUETA_AUTENTICACION],
    summary="Confirmar recuperación de contraseña",
    auth=[],  # publico: sin candado en Swagger UI
    description="Paso 2. Recibe `uid` y `token` del paso 1 y la contraseña nueva. "
    "El token es de un solo uso.",
    request=ConfirmarRecuperacionSerializer,
    responses=respuestas(
        ok(MensajeSerializer, {"mensaje": "Contrasena restablecida. Ya puedes iniciar sesion."}),
        error_400({"non_field_errors": ["El enlace de recuperacion no es valido."]}),
    ),
)
class ConfirmarRecuperacionView(APIView):
    """POST /api/auth/recuperar/confirmar/"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmarRecuperacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"mensaje": "Contrasena restablecida. Ya puedes iniciar sesion."})
