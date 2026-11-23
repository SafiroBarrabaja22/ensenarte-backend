import secrets

from django.contrib.auth.models import Group, User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .roles import (
    ROL_ADMINISTRADOR,
    ROL_ESTUDIANTE,
    ROL_INTERPRETE,
    ROL_PROFESOR,
    TODOS_LOS_ROLES,
    asignar_rol,
    roles_de,
)

# Clave al azar en cada ejecucion: ninguna contrasena queda escrita en el codigo.
CLAVE = secrets.token_urlsafe(12) + "Aa1!"


class GruposDeRolesTests(APITestCase):
    def test_la_migracion_crea_todos_los_grupos(self):
        existentes = set(Group.objects.values_list("name", flat=True))
        self.assertTrue(set(TODOS_LOS_ROLES) <= existentes)

    def test_superusuario_siempre_es_administrador(self):
        admin = User.objects.create_superuser("raiz", password=CLAVE)
        self.assertEqual(roles_de(admin), [ROL_ADMINISTRADOR])

    def test_is_staff_por_si_solo_no_da_roles(self):
        staff = User.objects.create_user("staff", password=CLAVE, is_staff=True)
        self.assertEqual(roles_de(staff), [])

    def test_asignar_rol_desconocido_falla(self):
        usuario = User.objects.create_user("x", password=CLAVE)
        with self.assertRaises(ValueError):
            asignar_rol(usuario, "Profesr")


class PerfilRolesTests(APITestCase):
    def test_registro_crea_estudiante_y_login_devuelve_roles(self):
        respuesta = self.client.post(
            reverse("registro"),
            {"nombre": "nuevo", "correo": "nuevo@correo.com", "password": CLAVE},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["usuario"]["roles"], [ROL_ESTUDIANTE])

        login = self.client.post(
            reverse("login"),
            {"username": "nuevo", "password": CLAVE},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertEqual(login.data["usuario"]["roles"], [ROL_ESTUDIANTE])

    def test_un_rol_de_trabajo_anula_el_grupo_estudiante(self):
        """Quien se registro (Estudiante) y luego recibio Profesor ya no es estudiante."""
        usuario = User.objects.create_user("profe", password=CLAVE)
        asignar_rol(usuario, ROL_ESTUDIANTE)
        asignar_rol(usuario, ROL_PROFESOR)
        self.client.force_authenticate(usuario)
        respuesta = self.client.get(reverse("perfil"))
        self.assertEqual(respuesta.data["roles"], [ROL_PROFESOR])
        self.assertNotIn("es_creador", respuesta.data)

    def test_perfil_devuelve_varios_roles_de_trabajo_en_orden(self):
        usuario = User.objects.create_user("varios", password=CLAVE)
        asignar_rol(usuario, ROL_INTERPRETE)
        asignar_rol(usuario, ROL_PROFESOR)
        self.client.force_authenticate(usuario)
        self.assertEqual(self.client.get(reverse("perfil")).data["roles"], [ROL_PROFESOR, ROL_INTERPRETE])

    def test_perfil_sin_rol_devuelve_lista_vacia(self):
        usuario = User.objects.create_user("sinrol", password=CLAVE)
        self.client.force_authenticate(usuario)
        self.assertEqual(self.client.get(reverse("perfil")).data["roles"], [])
