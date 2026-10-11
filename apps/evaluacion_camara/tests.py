from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import EvaluacionCamara, IntentoCamara

URL = reverse("evaluacion_camara")


def intentos(correctas, total, **extra):
    """`total` intentos de los cuales los primeros `correctas` aciertan."""
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [
        {
            "letra_objetivo": letras[n % len(letras)],
            "acerto": n < correctas,
            "tiempo_ms": 1500,
            "confianza": 0.8,
            **extra,
        }
        for n in range(total)
    ]


class EvaluacionCamaraTests(APITestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("ana", password="ClaveSegura123")
        self.otro = User.objects.create_user("beto", password="ClaveSegura123")
        self.client.force_authenticate(self.usuario)

    def enviar(self, lista):
        return self.client.post(URL, {"intentos": lista}, format="json")

    # --- Calculo del resultado -------------------------------------------

    def test_siete_de_diez_aprueba(self):
        resp = self.enviar(intentos(7, 10))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["total"], 10)
        self.assertEqual(resp.data["correctas"], 7)
        self.assertEqual(resp.data["porcentaje"], 70)
        self.assertTrue(resp.data["aprobado"])
        self.assertEqual(resp.data["umbral_aplicado"], 70)

    def test_seis_de_diez_no_aprueba(self):
        resp = self.enviar(intentos(6, 10))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["porcentaje"], 60)
        self.assertFalse(resp.data["aprobado"])

    def test_borde_no_exacto_usa_enteros(self):
        # 7/10 = 70 % justo; con 3 intentos, 2/3 = 66.6 % no aprueba y 3/3 si.
        self.assertFalse(self.enviar(intentos(2, 3)).data["aprobado"])
        self.assertTrue(self.enviar(intentos(3, 3)).data["aprobado"])
        self.assertEqual(self.enviar(intentos(2, 3)).data["porcentaje"], 66)

    @override_settings(EVALUACION_CAMARA_UMBRAL_APROBACION=80)
    def test_umbral_configurable(self):
        resp = self.enviar(intentos(7, 10))
        self.assertFalse(resp.data["aprobado"])
        self.assertEqual(resp.data["umbral_aplicado"], 80)
        self.assertTrue(self.enviar(intentos(8, 10)).data["aprobado"])

    def test_ignora_resultado_enviado_por_el_cliente(self):
        resp = self.client.post(
            URL,
            {
                "intentos": intentos(1, 10),
                "total": 10,
                "correctas": 10,
                "porcentaje": 100,
                "aprobado": True,
                "umbral_aplicado": 0,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["correctas"], 1)
        self.assertEqual(resp.data["porcentaje"], 10)
        self.assertFalse(resp.data["aprobado"])
        self.assertEqual(resp.data["umbral_aplicado"], 70)

    def test_guarda_intentos_en_orden_y_normaliza_letra(self):
        lista = [
            {"letra_objetivo": "ll", "acerto": True, "tiempo_ms": 0},
            {"letra_objetivo": " b ", "acerto": False, "tiempo_ms": 900,
             "confianza": None},
            {"letra_objetivo": "C", "acerto": True, "tiempo_ms": 10,
             "confianza": 1},
        ]
        resp = self.enviar(lista)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        evaluacion = EvaluacionCamara.objects.get(pk=resp.data["id"])
        self.assertEqual(evaluacion.usuario, self.usuario)
        guardados = list(evaluacion.intentos.values_list(
            "orden", "letra_objetivo", "confianza"
        ))
        self.assertEqual(guardados, [(0, "LL", None), (1, "B", None), (2, "C", 1.0)])

    # --- Validacion -------------------------------------------------------

    def assertRechaza(self, cuerpo):
        resp = self.client.post(URL, cuerpo, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertEqual(EvaluacionCamara.objects.count(), 0)
        self.assertEqual(IntentoCamara.objects.count(), 0)
        return resp

    def test_rechaza_lista_vacia_o_ausente(self):
        self.assertRechaza({"intentos": []})
        self.assertRechaza({})

    def test_rechaza_mas_de_cincuenta(self):
        self.assertRechaza({"intentos": intentos(51, 51)})

    def test_acepta_cincuenta(self):
        self.assertEqual(self.enviar(intentos(50, 50)).status_code, 201)

    def test_rechaza_letra_invalida(self):
        for letra in ("", "   ", "ABC"):
            self.assertRechaza({"intentos": intentos(1, 1, letra_objetivo=letra)})

    def test_rechaza_tiempo_negativo(self):
        self.assertRechaza({"intentos": intentos(1, 1, tiempo_ms=-1)})

    def test_rechaza_confianza_fuera_de_rango(self):
        for valor in (-0.01, 1.01):
            self.assertRechaza({"intentos": intentos(1, 1, confianza=valor)})

    def test_rechaza_si_falta_acerto(self):
        self.assertRechaza(
            {"intentos": [{"letra_objetivo": "A", "tiempo_ms": 100}]}
        )

    def test_un_intento_invalido_no_guarda_nada(self):
        lista = intentos(5, 5)
        lista[3]["tiempo_ms"] = -5
        resp = self.assertRechaza({"intentos": lista})
        self.assertIn("intentos", resp.data)

    # --- Autenticacion e historial ----------------------------------------

    def test_requiere_autenticacion(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.enviar(intentos(7, 10)).status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(
            self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_historial_solo_del_usuario_y_mas_reciente_primero(self):
        primera = self.enviar(intentos(7, 10)).data["id"]
        segunda = self.enviar(intentos(2, 4)).data["id"]

        self.client.force_authenticate(self.otro)
        self.enviar(intentos(1, 1))
        resp_otro = self.client.get(URL)
        self.assertEqual(resp_otro.data["count"], 1)

        self.client.force_authenticate(self.usuario)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)
        ids = [e["id"] for e in resp.data["results"]]
        self.assertEqual(ids, [segunda, primera])
        self.assertEqual(len(resp.data["results"][1]["intentos"]), 10)

    def test_historial_vacio(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)
