"""
Permisos por rol: cada rol tiene al menos un endpoint de OTRO rol al que no puede entrar.

El Administrador es la excepcion por diseno: tiene acceso a todo. Para el se
comprueba lo contrario (que entra a los endpoints de cada uno de los otros roles).
"""

import pytest

pytestmark = pytest.mark.django_db


def _ids(curso):
    return {
        "curso": curso.id,
        "pregunta": curso.preguntas.first().id,
        "palabra": curso.diccionario.first().id,
    }


# (rol, metodo, ruta, cuerpo, de quien es el endpoint)
DENEGADOS = [
    # Estudiante -> panel (Profesor/Creador/Admin) y biblioteca (Interprete)
    ("estudiante", "get", "/api/panel/resumen/", None, "Profesor"),
    ("estudiante", "get", "/api/panel/cursos/", None, "Profesor"),
    ("estudiante", "post", "/api/panel/preguntas/", {"texto": "x"}, "Profesor"),
    ("estudiante", "get", "/api/panel/estudiantes/estrellas/", None, "Profesor"),
    ("estudiante", "post", "/api/panel/recursos/", {"nombre": "x"}, "Interprete"),
    ("estudiante", "post", "/api/panel/archivos/", {}, "Interprete"),
    # Profesor -> biblioteca (Interprete) y cursos de otro profesor
    ("profesor", "post", "/api/panel/recursos/", {"nombre": "x"}, "Interprete"),
    ("profesor", "patch", "/api/panel/cursos/{ajeno}/", {"titulo": "x"}, "otro Profesor"),
    ("profesor", "delete", "/api/panel/cursos/{ajeno}/", None, "otro Profesor"),
    ("profesor", "post", "/api/panel/preguntas/", {"curso": "{ajeno}", "texto": "x"}, "otro Profesor"),
    ("profesor", "post", "/api/panel/diccionario/{palabra_ajena}/gif/", {}, "otro Profesor"),
    # Interprete -> contenido y reportes (Profesor/Creador)
    ("interprete", "get", "/api/panel/cursos/", None, "Profesor"),
    ("interprete", "post", "/api/panel/cursos/", {"nombre": "x"}, "Creador"),
    ("interprete", "get", "/api/panel/resumen/", None, "Profesor"),
    ("interprete", "get", "/api/panel/estudiantes/estrellas/", None, "Profesor"),
    ("interprete", "delete", "/api/panel/preguntas/{pregunta_ajena}/", None, "Profesor"),
    # Creador -> biblioteca (Interprete)
    ("creador", "post", "/api/panel/recursos/", {"nombre": "x"}, "Interprete"),
    # Sin rol -> todo lo que exige un rol
    ("sin_rol", "get", "/api/progreso/", None, "Estudiante"),
    ("sin_rol", "post", "/api/cursos/saludos/evaluacion/iniciar/", None, "Estudiante"),
    ("sin_rol", "get", "/api/evaluacion-camara/", None, "Estudiante"),
]


@pytest.mark.parametrize("rol, metodo, ruta, cuerpo, duenno", DENEGADOS,
                         ids=[f"{d[0]}-{d[1]}-{d[2]}" for d in DENEGADOS])
def test_rol_no_entra_a_endpoint_de_otro_rol(request, como, curso_ajeno, rol, metodo, ruta, cuerpo, duenno):
    usuario = request.getfixturevalue(rol)
    reemplazos = {
        "{ajeno}": str(curso_ajeno.id),
        "{palabra_ajena}": str(curso_ajeno.diccionario.first().id),
        "{pregunta_ajena}": str(curso_ajeno.preguntas.first().id),
    }
    for marca, valor in reemplazos.items():
        ruta = ruta.replace(marca, valor)
    if cuerpo:
        cuerpo = {k: (int(reemplazos[v]) if v in reemplazos else v) for k, v in cuerpo.items()}
    respuesta = getattr(como(usuario), metodo)(ruta, cuerpo, format="json")
    assert respuesta.status_code == 403, f"{rol} entró a un endpoint de {duenno}"
    assert respuesta.data["detail"]


def test_profesor_no_ve_cursos_de_otro_profesor_en_el_listado(como, profesor, curso, curso_ajeno):
    nombres = [c["nombre"] for c in como(profesor).get("/api/panel/cursos/").data["results"]]
    assert nombres == ["abecedario"]


def test_interprete_sube_gifs_a_cualquier_curso(como, interprete, curso_ajeno, gif):
    palabra = curso_ajeno.diccionario.first()
    respuesta = como(interprete).post(f"/api/panel/diccionario/{palabra.id}/gif/", {"gif": gif()}, format="multipart")
    assert respuesta.status_code == 200


def test_estudiante_solo_lee_avatares_de_la_biblioteca(como, estudiante, administrador, png):
    admin = como(administrador)
    admin.post("/api/panel/recursos/", {"nombre": "Insignia", "archivo": png(), "categoria": "insignia"}, format="multipart")
    admin.post("/api/panel/recursos/", {"nombre": "Avatar", "archivo": png(), "categoria": "avatar"}, format="multipart")
    respuesta = como(estudiante).get("/api/panel/recursos/")
    assert [r["nombre"] for r in respuesta.data] == ["Avatar"]


@pytest.mark.parametrize("metodo, ruta, cuerpo, duenno", [
    ("get", "/api/progreso/", None, "Estudiante"),
    ("get", "/api/panel/resumen/", None, "Profesor"),
    ("patch", "/api/panel/cursos/{ajeno}/", {"titulo": "Admin"}, "Profesor dueño"),
    ("get", "/api/panel/estudiantes/estrellas/", None, "Profesor"),
    ("post", "/api/panel/diccionario/reordenar/", {"curso": "{ajeno}", "ids": "{ids}"}, "Profesor dueño"),
])
def test_administrador_entra_a_los_endpoints_de_todos_los_roles(como, administrador, curso_ajeno, metodo, ruta, cuerpo, duenno):
    ruta = ruta.replace("{ajeno}", str(curso_ajeno.id))
    if cuerpo and cuerpo.get("curso") == "{ajeno}":
        cuerpo = {**cuerpo, "curso": curso_ajeno.id}
    if cuerpo and cuerpo.get("ids") == "{ids}":
        cuerpo = {**cuerpo, "ids": list(curso_ajeno.diccionario.values_list("id", flat=True))}
    respuesta = getattr(como(administrador), metodo)(ruta, cuerpo, format="json")
    assert respuesta.status_code in (200, 204), f"Administrador no pudo entrar a un endpoint de {duenno}"


def test_administrador_escribe_en_la_biblioteca(como, administrador, png):
    respuesta = como(administrador).post("/api/panel/recursos/", {"nombre": "x", "archivo": png()}, format="multipart")
    assert respuesta.status_code == 201
