"""
Protecciones de inicio de sesion, registro y recuperacion de contrasena.
Explicacion en docs/SEGURIDAD.md, seccion 8.

1. Limite por IP (DRF ScopedRateThrottle): frena a quien prueba miles de
   contrasenas o crea cuentas en masa desde una misma maquina.
2. Bloqueo por cuenta: tras LOGIN_MAX_FALLOS contrasenas incorrectas para el
   mismo usuario, el login se rechaza durante LOGIN_BLOQUEO_MINUTOS, aunque
   el atacante cambie de IP. Se aplica igual a usuarios que no existen, para
   no revelar cuales existen.
3. Al restablecer o cambiar la contrasena se cierran todas las sesiones
   abiertas (sus refresh tokens pasan a la lista negra).
"""

import hashlib

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


class LimiteDeIntentos:
    """Mixin para vistas publicas: limite por IP con mensaje en espanol."""

    throttle_classes = [ScopedRateThrottle]

    def throttled(self, request, wait):
        raise Throttled(wait, detail="Demasiados intentos desde tu conexión. Espera un momento y vuelve a intentarlo.")


class CuentaBloqueada(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "cuenta_bloqueada"

    def __init__(self):
        minutos = settings.LOGIN_BLOQUEO_MINUTOS
        super().__init__(
            f"Demasiados intentos fallidos para esta cuenta. Espera {minutos} minutos "
            "o recupera tu contraseña con \"¿Olvidaste tu contraseña?\"."
        )


def _clave(prefijo, valor):
    """Clave de cache sin datos personales en claro y sin caracteres raros."""
    resumen = hashlib.sha256(str(valor).strip().lower().encode("utf-8")).hexdigest()
    return f"{prefijo}:{resumen}"


# ---------------------------------------------------------------- Bloqueo de login


def comprobar_bloqueo(nombre_usuario):
    """Lanza CuentaBloqueada (429) si la cuenta acumula demasiados fallos."""
    if cache.get(_clave("login-fallos", nombre_usuario), 0) >= settings.LOGIN_MAX_FALLOS:
        raise CuentaBloqueada()


def registrar_fallo(nombre_usuario):
    clave = _clave("login-fallos", nombre_usuario)
    fallos = cache.get(clave, 0) + 1
    # Cada fallo renueva el plazo: el bloqueo dura N minutos desde el ultimo.
    cache.set(clave, fallos, settings.LOGIN_BLOQUEO_MINUTOS * 60)


def limpiar_fallos(nombre_usuario):
    cache.delete(_clave("login-fallos", nombre_usuario))


# ---------------------------------------------------------------- Recuperacion


def puede_pedir_recuperacion(correo):
    """Maximo RECUPERAR_MAX_POR_CORREO correos de recuperacion por hora y direccion."""
    clave = _clave("recuperar-correo", correo)
    enviados = cache.get(clave, 0)
    if enviados >= settings.RECUPERAR_MAX_POR_CORREO:
        return False
    cache.set(clave, enviados + 1, 3600)
    return True


# ---------------------------------------------------------------- Sesiones


def cerrar_todas_las_sesiones(usuario):
    """
    Invalida todos los refresh tokens del usuario. Los access tokens ya
    emitidos siguen sirviendo hasta que venzan (15 minutos como maximo).
    """
    pendientes = OutstandingToken.objects.filter(user=usuario).exclude(blacklistedtoken__isnull=False)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in pendientes], ignore_conflicts=True
    )
