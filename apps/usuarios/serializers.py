from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.serializers import PasswordField, TokenObtainPairSerializer

from config.limites import (
    MAX_CORREO,
    MAX_NOMBRE_USUARIO,
    MAX_PASSWORD,
    MAX_TOKEN_RECUPERACION,
    MAX_UID_RECUPERACION,
)

from apps.cursos.archivos import MAX_BYTES_FOTO_PERFIL, nombre_seguro, validar_imagen
from apps.cursos.models import RecursoVisual

from .models import PerfilUsuario
from .roles import ROL_ESTUDIANTE, asignar_rol, roles_de

AVATARES_ANTERIORES = {
    "imgPredeterminadaUsuario.png",
    "opcionUnoPerfil.png",
    "opcionDosPerfil.png",
    "opcionTresPerfil.png",
    "opcionCuatroPerfil.png",
    "opcionCincoPerfil.png",
}


class PerfilSerializer(serializers.ModelSerializer):
    """Representacion del usuario que consume el frontend."""

    nombre = serializers.CharField(source="user.username", read_only=True)
    correo = serializers.EmailField(source="user.email", read_only=True)
    foto_perfil_url = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = PerfilUsuario
        fields = (
            "nombre",
            "correo",
            "avatar",
            "foto_perfil",
            "foto_perfil_url",
            "estrellas",
            "roles",
        )
        read_only_fields = ("estrellas",)
        extra_kwargs = {"foto_perfil": {"write_only": True, "required": False}}

    def get_foto_perfil_url(self, obj) -> str | None:
        if not obj.foto_perfil:
            return None
        request = self.context.get("request")
        url = obj.foto_perfil.url
        return request.build_absolute_uri(url) if request else url

    def get_roles(self, obj) -> list[str]:
        """Roles del usuario, p. ej. ["Profesor", "Estudiante"]. Ver usuarios/roles.py."""
        return roles_de(obj.user)


class RegistroSerializer(serializers.Serializer):
    """Reemplaza la vista `registro` del monolito, ahora con validaciones reales."""

    nombre = serializers.CharField(max_length=MAX_NOMBRE_USUARIO)
    correo = serializers.EmailField(max_length=MAX_CORREO)
    password = serializers.CharField(write_only=True, min_length=8, max_length=MAX_PASSWORD)
    # Trampa para bots: el formulario tiene este campo oculto. Una persona no
    # lo ve y lo deja vacio; un bot que rellena todos los campos lo llena.
    sitio_web = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=200,
        help_text="Dejar vacío. Campo trampa contra bots: si trae texto, el registro se rechaza.",
    )

    def validate(self, attrs):
        if attrs.pop("sitio_web", ""):
            raise serializers.ValidationError("No se pudo completar el registro.")
        return attrs

    def validate_nombre(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("El nombre de usuario ya existe.")
        return value

    def validate_correo(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("El correo ya esta en uso.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        usuario = User.objects.create_user(
            username=validated_data["nombre"],
            email=validated_data["correo"],
            password=validated_data["password"],
        )
        # El registro publico siempre crea estudiantes; los demas roles los
        # asigna un Administrador desde el admin de Django.
        asignar_rol(usuario, ROL_ESTUDIANTE)
        return usuario


class LoginSerializer(TokenObtainPairSerializer):
    """Devuelve el par de tokens JWT junto con los datos del usuario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # simplejwt crea estos campos sin limite de longitud.
        self.fields[self.username_field] = serializers.CharField(
            write_only=True, max_length=MAX_NOMBRE_USUARIO
        )
        self.fields["password"] = PasswordField(max_length=MAX_PASSWORD)

    def validate(self, attrs):
        data = super().validate(attrs)
        perfil, _ = PerfilUsuario.objects.get_or_create(user=self.user)
        data["usuario"] = PerfilSerializer(
            perfil, context=self.context
        ).data
        return data


class ActualizarPerfilSerializer(serializers.Serializer):
    """Edicion de perfil: nombre, correo y avatar o foto."""

    nombre = serializers.CharField(max_length=MAX_NOMBRE_USUARIO, required=False)
    correo = serializers.EmailField(max_length=MAX_CORREO, required=False)
    avatar = serializers.CharField(max_length=100, required=False)
    foto_perfil = serializers.ImageField(required=False, allow_null=True)

    def validate_foto_perfil(self, archivo):
        if archivo is None:          # null = quitar la foto
            return archivo
        extension = validar_imagen(archivo, max_bytes=MAX_BYTES_FOTO_PERFIL)
        archivo.name = nombre_seguro(extension)   # el nombre original no llega al disco
        return archivo

    def validate_nombre(self, value):
        user = self.context["request"].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ese nombre de usuario ya esta tomado.")
        return value

    def validate_correo(self, value):
        user = self.context["request"].user
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ese correo ya esta registrado.")
        return value

    def validate_avatar(self, value):
        if value in AVATARES_ANTERIORES:
            return value
        prefijo = "/media/"
        if value.startswith(prefijo):
            ruta = value[len(prefijo):]
            if RecursoVisual.objects.filter(
                archivo=ruta,
                categoria=RecursoVisual.Categoria.AVATAR,
            ).exists():
                return value
        raise serializers.ValidationError(
            "Selecciona un avatar disponible en la biblioteca."
        )

    def update(self, instance, validated_data):
        user = instance.user
        if "nombre" in validated_data:
            user.username = validated_data["nombre"]
        if "correo" in validated_data:
            user.email = validated_data["correo"]
        user.save()

        if "avatar" in validated_data:
            instance.avatar = validated_data["avatar"]
        if "foto_perfil" in validated_data:
            foto_perfil = validated_data["foto_perfil"]
            if foto_perfil is None and instance.foto_perfil:
                instance.foto_perfil.delete(save=False)
            instance.foto_perfil = foto_perfil
        instance.save()
        return instance


class CambiarPasswordSerializer(serializers.Serializer):
    """Cambio de contrasena estando autenticado. Exige la contrasena actual."""

    password_actual = serializers.CharField(write_only=True, max_length=MAX_PASSWORD)
    password_nueva = serializers.CharField(write_only=True, min_length=8, max_length=MAX_PASSWORD)

    def validate_password_actual(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contrasena actual no es correcta.")
        return value

    def validate_password_nueva(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["password_nueva"])
        user.save()
        return user


class SolicitarRecuperacionSerializer(serializers.Serializer):
    """
    Paso 1 de la recuperacion de contrasena.

    El monolito permitia cambiar la clave de cualquier usuario sabiendo solo su
    nombre. Aqui se exige el correo y se emite un token firmado de un solo uso.
    """

    correo = serializers.EmailField(max_length=MAX_CORREO)

    def cuentas(self):
        """
        Cuentas activas con ese correo y con contrasena (el registro impide
        correos repetidos, pero el admin podria crearlos). Puede ser vacia: la
        vista responde lo mismo en ese caso, para no revelar que correos existen.
        """
        usuarios = User.objects.filter(email__iexact=self.validated_data["correo"], is_active=True)
        return [
            {
                "usuario": usuario,
                "uid": urlsafe_base64_encode(force_bytes(usuario.pk)),
                "token": default_token_generator.make_token(usuario),
            }
            for usuario in usuarios
            if usuario.has_usable_password()
        ]


class ConfirmarRecuperacionSerializer(serializers.Serializer):
    """Paso 2 de la recuperacion: uid + token + contrasena nueva."""

    uid = serializers.CharField(max_length=MAX_UID_RECUPERACION)
    token = serializers.CharField(max_length=MAX_TOKEN_RECUPERACION)
    password_nueva = serializers.CharField(write_only=True, min_length=8, max_length=MAX_PASSWORD)

    def validate(self, attrs):
        try:
            pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError("El enlace de recuperacion no es valido.")

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                "El enlace de recuperacion expiro o ya fue usado."
            )

        validate_password(attrs["password_nueva"], user)
        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["password_nueva"])
        user.save()
        return user
