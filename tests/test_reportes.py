"""Reportes en PDF (ReportLab) y Excel (openpyxl): contenido, formato y permisos por rol."""

import base64
import re
import zipfile
import zlib
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.db import connection
from django.utils import timezone
from openpyxl import load_workbook

from apps.cursos.models import IntentoEvaluacion, ProgresoUsuario
from apps.reportes import excel, pdf
from apps.reportes.modelo import DECIMAL, ENTERO, FECHA, PORCENTAJE, SI_NO, TEXTO, Reporte, Tabla, tabla_resumen

pytestmark = pytest.mark.django_db

TIPO_PDF = "application/pdf"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEAL = "0F7F7A"
MENTA = "E8F2EE"
ES_MYSQL = connection.vendor == "mysql"


# ------------------------------------------------------------------ utilidades


def texto_pdf(contenido):
    """
    Texto de los flujos del PDF. ReportLab los guarda con los filtros
    /ASCII85Decode y /FlateDecode: se deshacen en ese orden.
    """
    partes = []
    # ReportLab escribe "...~>endstream" sin salto de linea antes de endstream.
    for flujo in re.finditer(rb"stream\r?\n(.*?)endstream", contenido, re.S):
        datos = flujo.group(1).strip()
        try:
            if datos.endswith(b"~>"):
                datos = base64.a85decode(datos[:-2], adobe=False)
            partes.append(zlib.decompress(datos).decode("latin-1"))
        except (ValueError, zlib.error):
            continue  # imagenes u otros flujos binarios
    return "\n".join(partes)


def es_pdf_valido(respuesta, nombre):
    assert respuesta.status_code == 200, getattr(respuesta, "data", respuesta.content[:200])
    assert respuesta["Content-Type"] == TIPO_PDF
    assert respuesta["Content-Disposition"] == f'attachment; filename="{nombre}"'
    contenido = respuesta.content
    assert contenido.startswith(b"%PDF-") and contenido.rstrip().endswith(b"%%EOF")
    assert b"/Subtype /Image" in contenido, "falta el logo"
    return texto_pdf(contenido)


def libro_de(respuesta, nombre):
    assert respuesta.status_code == 200, getattr(respuesta, "data", respuesta.content[:200])
    assert respuesta["Content-Type"] == TIPO_XLSX
    assert respuesta["Content-Disposition"] == f'attachment; filename="{nombre}"'
    with zipfile.ZipFile(BytesIO(respuesta.content)) as archivo:
        assert any(n.startswith("xl/media/") and n.endswith(".png") for n in archivo.namelist()), "falta el logo"
    return load_workbook(BytesIO(respuesta.content))


def hoja_con_formato(hoja, titulo, encabezados):
    """Titulo, fecha, encabezado teal y pie con numeracion."""
    assert hoja["A3"].value == titulo
    assert hoja["A3"].font.name == "Arial" and hoja["A3"].font.bold
    assert hoja["A5"].value.startswith("Generado el ")
    assert [c.value for c in hoja[7][: len(encabezados)]] == encabezados
    assert hoja["A7"].fill.fgColor.rgb.endswith(TEAL)
    assert hoja["A7"].font.color.rgb.endswith("FFFFFF")
    assert "&P" in hoja.oddFooter.right.text and "&N" in hoja.oddFooter.right.text


def completar(usuario, curso, **campos):
    return ProgresoUsuario.objects.create(usuario=usuario, curso=curso, completado=True, **campos)


# ================================================================== 1. Constancia

URL_CONSTANCIA = "/api/reportes/constancia/abecedario/"


def test_constancia_pdf(como, estudiante, curso):
    completar(estudiante, curso, aciertos=3, insignia_100_ganada=True)
    texto = es_pdf_valido(como(estudiante).get(URL_CONSTANCIA), "constancia-abecedario.pdf")
    assert "CONSTANCIA DE CURSO COMPLETADO" in texto
    assert "(estudiante)" in texto
    assert "Abecedario" in texto
    assert "Insignia Curso 100" in texto
    assert "gina 1 de 1" in texto          # una sola pagina; "Página" (la á va codificada)


def test_constancia_excel(como, estudiante, curso):
    completar(estudiante, curso, aciertos=2, errores=1)
    libro = libro_de(como(estudiante).get(URL_CONSTANCIA + "?formato=xlsx"), "constancia-abecedario.xlsx")
    assert libro.sheetnames == ["Constancia"]
    hoja = libro["Constancia"]
    hoja_con_formato(hoja, "Constancia de curso completado", ["Concepto", "Valor"])
    datos = {hoja.cell(fila, 1).value: hoja.cell(fila, 2).value for fila in range(8, hoja.max_row + 1)}
    assert datos["Estudiante"] == "estudiante"
    assert datos["Curso"] == "Abecedario"
    assert datos["Resultado"] == "2 aciertos y 1 error en su última evaluación"
    assert datos["Insignia Curso 100 %"] == "No"
    assert datos["Profesor del curso"] == "profesor"
    assert hoja["A9"].fill.fgColor.rgb.endswith(MENTA)   # filas alternadas


def test_constancia_por_camara_sin_aciertos(como, estudiante, curso):
    completar(estudiante, curso)
    libro = libro_de(como(estudiante).get(URL_CONSTANCIA + "?formato=xlsx"), "constancia-abecedario.xlsx")
    valores = [c.value for c in libro["Constancia"]["B"]]
    assert "Evaluación con cámara aprobada" in valores


@pytest.mark.parametrize("url, codigo", [
    (URL_CONSTANCIA, 404),                                  # aun no completa el curso
    ("/api/reportes/constancia/no-existe/", 404),
    (URL_CONSTANCIA + "?formato=docx", 400),
])
def test_constancia_errores(como, estudiante, curso, url, codigo):
    respuesta = como(estudiante).get(url)
    assert respuesta.status_code == codigo
    assert respuesta.data["detail"]


def test_constancia_es_solo_del_propio_usuario(como, estudiante, crear_usuario, curso):
    from apps.usuarios.roles import ROL_ESTUDIANTE

    completar(estudiante, curso)
    otro = crear_usuario(ROL_ESTUDIANTE, "otro")
    assert como(otro).get(URL_CONSTANCIA).status_code == 404   # la de estudiante no le pertenece


def test_constancia_sin_token_o_sin_rol(api, como, sin_rol, curso):
    assert api.get(URL_CONSTANCIA).status_code == 401
    assert como(sin_rol).get(URL_CONSTANCIA).status_code == 403


def test_descarga_con_jwt_real(con_jwt, estudiante, curso):
    completar(estudiante, curso)
    respuesta = con_jwt(estudiante).get(URL_CONSTANCIA)
    assert respuesta.status_code == 200 and respuesta["Content-Type"] == TIPO_PDF


# ================================================================== 2. Progreso del curso


@pytest.fixture
def actividad(curso, estudiante, crear_usuario):
    """Un estudiante completo, otro con evaluacion abierta."""
    from apps.usuarios.roles import ROL_ESTUDIANTE

    completar(estudiante, curso, aciertos=3, errores=1, insignia_100_ganada=True)
    otra = crear_usuario(ROL_ESTUDIANTE, "beatriz")
    IntentoEvaluacion.objects.create(usuario=otra, curso=curso, orden=[1, 2], aciertos=1)
    return curso


def test_progreso_pdf(como, profesor, actividad):
    texto = es_pdf_valido(
        como(profesor).get(f"/api/reportes/cursos/{actividad.id}/progreso/"),
        f"progreso-abecedario-{timezone.localdate():%Y%m%d}.pdf",
    )
    assert "Progreso de los estudiantes" in texto
    assert "(estudiante)" in texto and "(beatriz)" in texto
    assert "Completado" in texto


def test_progreso_excel(como, profesor, actividad):
    libro = libro_de(
        como(profesor).get(f"/api/reportes/cursos/{actividad.id}/progreso/?formato=xlsx"),
        f"progreso-abecedario-{timezone.localdate():%Y%m%d}.xlsx",
    )
    assert libro.sheetnames == ["Resumen", "Estudiantes"]
    hoja = libro["Estudiantes"]
    encabezados = ["Estudiante", "Correo", "Estado", "Aciertos", "Errores", "Insignia 100 %", "Última actividad"]
    hoja_con_formato(hoja, "Progreso de los estudiantes", encabezados)
    filas = [[c.value for c in fila] for fila in hoja.iter_rows(min_row=8)]
    assert filas[0][:6] == ["estudiante", "estudiante@correo.com", "Completado", 3, 1, "Sí"]
    assert filas[1][:3] == ["beatriz", "beatriz@correo.com", "Evaluación en curso"]
    assert isinstance(filas[0][6], type(timezone.now().replace(tzinfo=None)))  # fecha real, no texto
    assert hoja["D8"].number_format == "#,##0"
    assert hoja.freeze_panes == "A8" and hoja.auto_filter.ref == "A7:G9"
    resumen = {libro["Resumen"].cell(f, 1).value: libro["Resumen"].cell(f, 2).value for f in range(8, 14)}
    assert resumen["Estudiantes con actividad"] == "2"
    assert resumen["Completaron el curso"] == "1"


def test_progreso_de_curso_sin_actividad(como, creador, curso):
    libro = libro_de(
        como(creador).get(f"/api/reportes/cursos/{curso.id}/progreso/?formato=xlsx"),
        f"progreso-abecedario-{timezone.localdate():%Y%m%d}.xlsx",
    )
    assert libro["Estudiantes"]["A8"].value == "Ningún estudiante ha trabajado todavía en este curso."


@pytest.mark.parametrize("quien, codigo", [
    ("profesor", 200), ("creador", 200), ("administrador", 200),
    ("profesor2", 403), ("estudiante", 403), ("interprete", 403),
])
def test_progreso_permisos_por_rol(request, como, curso, quien, codigo):
    respuesta = como(request.getfixturevalue(quien)).get(f"/api/reportes/cursos/{curso.id}/progreso/")
    assert respuesta.status_code == codigo


def test_progreso_errores(api, como, creador, curso):
    assert api.get(f"/api/reportes/cursos/{curso.id}/progreso/").status_code == 401
    assert como(creador).get("/api/reportes/cursos/999999/progreso/").status_code == 404
    assert como(creador).get(f"/api/reportes/cursos/{curso.id}/progreso/?formato=csv").status_code == 400


# ================================================================== 3. Plataforma


@pytest.mark.parametrize("quien", ["estudiante", "profesor", "interprete", "creador"])
def test_plataforma_solo_para_el_administrador(request, como, quien):
    assert como(request.getfixturevalue(quien)).get("/api/reportes/plataforma/").status_code == 403


def test_plataforma_sin_token(api):
    assert api.get("/api/reportes/plataforma/").status_code == 401


def test_plataforma_formato_invalido(como, administrador):
    assert como(administrador).get("/api/reportes/plataforma/?formato=txt").status_code == 400


@pytest.mark.skipif(ES_MYSQL, reason="En MySQL los procedimientos existen y el reporte se genera.")
def test_plataforma_sin_mysql_responde_503(como, administrador):
    respuesta = como(administrador).get("/api/reportes/plataforma/")
    assert respuesta.status_code == 503
    assert "procedimientos almacenados" in respuesta.data["detail"]


@pytest.mark.skipif(not ES_MYSQL, reason="Usa los procedimientos almacenados de MySQL.")
def test_plataforma_con_procedimientos_almacenados(como, administrador, actividad, crear_curso):
    crear_curso("vacio", preguntas=0, palabras=0)
    hoy = f"{timezone.localdate():%Y%m%d}"
    texto = es_pdf_valido(como(administrador).get("/api/reportes/plataforma/"), f"estadisticas-plataforma-{hoy}.pdf")
    assert "Estad" in texto and "(estudiante)" in texto

    libro = libro_de(como(administrador).get("/api/reportes/plataforma/?formato=xlsx"),
                     f"estadisticas-plataforma-{hoy}.xlsx")
    assert libro.sheetnames == ["Resumen", "Cursos", "Ranking"]
    cursos = {fila[0].value: [c.value for c in fila] for fila in libro["Cursos"].iter_rows(min_row=8)}
    assert cursos["Abecedario"][2] == "Sí"
    assert cursos["Abecedario"][6] == 1        # estudiantes que completaron (procedimiento)
    assert libro["Cursos"]["H8"].number_format == "0.0%"
    ranking = [[c.value for c in fila] for fila in libro["Ranking"].iter_rows(min_row=8)]
    assert ranking[0][:3] == [1, "estudiante", 1]


# ================================================================== Dibujo (sin base de datos)


def _reporte_largo(filas=80):
    ahora = timezone.now()
    tabla = Tabla(
        hoja="Datos", titulo="Datos de prueba",
        encabezados=["Nombre", "Entero", "Decimal", "Porcentaje", "Fecha", "Activo"],
        filas=[[f"<fila {n}>", n, Decimal("1.5"), Decimal("50"), ahora - timedelta(days=n), n % 2 == 0] for n in range(filas)],
        formatos=[TEXTO, ENTERO, DECIMAL, PORCENTAJE, FECHA, SI_NO],
        anchos=[20, 10, 10, 10, 18, 8],
    )
    return Reporte("Reporte de prueba", "Subtitulo", "prueba", [tabla_resumen([("Clave", "Valor")]), tabla])


def test_pdf_de_varias_paginas_numera_todas():
    contenido = pdf.construir(_reporte_largo())
    texto = texto_pdf(contenido)
    paginas = len(re.findall(rb"/Type /Page\b", contenido))
    assert paginas >= 2
    for numero in range(1, paginas + 1):
        assert f"gina {numero} de {paginas}" in texto
    # "<fila 0>" se dibuja como texto (escapado), no se interpreta como etiqueta.
    assert "(<) Tj (fila 0) Tj (>)" in texto


def test_excel_valores_nativos_y_filas_alternadas():
    libro = load_workbook(BytesIO(excel.construir(_reporte_largo(filas=3))))
    hoja = libro["Datos"]
    assert [hoja.cell(8, c).value for c in range(2, 5)] == [0, 1.5, 0.5]
    assert hoja["D8"].number_format == "0.0%"
    assert hoja["F8"].value == "Sí" and hoja["F9"].value == "No"
    assert hoja["A8"].fill.fgColor.rgb != hoja["A9"].fill.fgColor.rgb
    assert hoja["A9"].fill.fgColor.rgb.endswith(MENTA)


def test_tabla_vacia_muestra_mensaje():
    vacia = Tabla("Vacia", "Vacia", ["A", "B"], [], [TEXTO, TEXTO], [10, 10], vacio="Nada por aqui")
    reporte = Reporte("Vacio", "Sub", "vacio", [vacia])
    assert "Nada por aqui" in texto_pdf(pdf.construir(reporte))
    assert load_workbook(BytesIO(excel.construir(reporte)))["Vacia"]["A8"].value == "Nada por aqui"


def test_constancia_siempre_cabe_en_una_pagina():
    largo = "Nombre Extremadamente Largo " * 6
    reporte = Reporte(
        "Constancia de curso completado", "x", "constancia",
        [tabla_resumen([("Estudiante", largo), ("Curso", largo)], hoja="Constancia", titulo="Detalle")],
        horizontal=True,
        certificado={"estudiante": largo, "curso": largo, "fecha": "1 de enero de 2026", "insignia_100": True},
    )
    contenido = pdf.construir(reporte)
    assert len(re.findall(rb"/Type /Page\b", contenido)) == 1
    assert "gina 1 de 1" in texto_pdf(contenido)
