from django.contrib.auth.models import Group, User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .roles import (
    ROL_ADMINISTRADOR,
    ROL_ESTUDIANTE,
    ROL_PROFESOR,
    TODOS_LOS_ROLES,
    asignar_rol,
    roles_de,
)


class GruposDeRolesTests(APITestCase):
    def test_la_migracion_crea_todos_los_grupos(self):
        existentes = set(Group.objects.values_list("name", flat=True))
        self.assertTrue(set(TODOS_LOS_ROLES) <= existentes)

    def test_superusuario_siempre_es_administrador(self):
        admin = User.objects.create_superuser("raiz", password="ClaveSegura123")
        self.assertEqual(roles_de(admin), [ROL_ADMINISTRADOR])

    def test_is_staff_por_si_solo_no_da_roles(self):
        staff = User.objects.create_user("staff", password="ClaveSegura123", is_staff=True)
        self.assertEqual(roles_de(staff), [])

    def test_asignar_rol_desconocido_falla(self):
        usuario = User.objects.create_user("x", password="ClaveSegura123")
        with self.assertRaises(ValueError):
            asignar_rol(usuario, "Profesr")


class PerfilRolesTests(APITestCase):
    def test_registro_crea_estudiante_y_login_devuelve_roles(self):
        respuesta = self.client.post(
            reverse("registro"),
            {"nombre": "nuevo", "correo": "nuevo@correo.com", "password": "ClaveSegura123"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["usuario"]["roles"], [ROL_ESTUDIANTE])

        login = self.client.post(
            reverse("login"),
            {"username": "nuevo", "password": "ClaveSegura123"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertEqual(login.data["usuario"]["roles"], [ROL_ESTUDIANTE])

    def test_perfil_devuelve_varios_roles_en_orden(self):
        usuario = User.objects.create_user("profe", password="ClaveSegura123")
        asignar_rol(usuario, ROL_ESTUDIANTE)
        asignar_rol(usuario, ROL_PROFESOR)
        self.client.force_authenticate(usuario)
        respuesta = self.client.get(reverse("perfil"))
        self.assertEqual(respuesta.data["roles"], [ROL_PROFESOR, ROL_ESTUDIANTE])
        self.assertNotIn("es_creador", respuesta.data)

    def test_perfil_sin_rol_devuelve_lista_vacia(self):
        usuario = User.objects.create_user("sinrol", password="ClaveSegura123")
        self.client.force_authenticate(usuario)
        self.assertEqual(self.client.get(reverse("perfil")).data["roles"], [])
