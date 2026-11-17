"""
Dibujo de un Reporte en PDF con ReportLab.

Formato comun: logo y titulo arriba en cada pagina, linea con el color
corporativo, fecha de generacion, tablas con encabezado teal y filas
alternadas, y pie "Pagina X de Y".
"""

from functools import partial
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config.marca import COLORES, FUENTE_PDF, FUENTE_PDF_NEGRITA, LOGO_ALTO, LOGO_ANCHO, RUTA_LOGO

from .modelo import DECIMAL, ENTERO, PORCENTAJE, como_texto

C = {nombre: colors.HexColor(valor) for nombre, valor in COLORES.items()}
MARGEN = 15 * mm
ANCHO_LOGO = 45 * mm
ALTO_LOGO = ANCHO_LOGO * LOGO_ALTO / LOGO_ANCHO
NUMERICOS = {ENTERO, DECIMAL, PORCENTAJE}


def _estilo(nombre, **kwargs):
    base = {"fontName": FUENTE_PDF, "fontSize": 10, "leading": 14, "textColor": C["tinta"]}
    return ParagraphStyle(nombre, **{**base, **kwargs})


ESTILOS = {
    "titulo": _estilo("titulo", fontName=FUENTE_PDF_NEGRITA, fontSize=20, leading=24, spaceAfter=4),
    "subtitulo": _estilo("subtitulo", fontSize=11, leading=15, textColor=C["texto_suave"]),
    "fecha": _estilo("fecha", fontSize=9, textColor=C["texto_tenue"], spaceAfter=10),
    "seccion": _estilo("seccion", fontName=FUENTE_PDF_NEGRITA, fontSize=13, leading=17,
                       textColor=C["teal_oscuro"], spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "encabezado": _estilo("encabezado", fontName=FUENTE_PDF_NEGRITA, fontSize=9, leading=12, textColor=C["blanco"]),
    "encabezado_derecha": _estilo("encabezado_derecha", fontName=FUENTE_PDF_NEGRITA, fontSize=9, leading=12,
                                  textColor=C["blanco"], alignment=TA_RIGHT),
    "celda": _estilo("celda", fontSize=9, leading=12),
    "celda_derecha": _estilo("celda_derecha", fontSize=9, leading=12, alignment=TA_RIGHT),
    # Constancia
    "cert_titulo": _estilo("cert_titulo", fontName=FUENTE_PDF_NEGRITA, fontSize=24, leading=30,
                           textColor=C["teal"], alignment=TA_CENTER, spaceAfter=14),
    "cert_texto": _estilo("cert_texto", fontSize=13, leading=18, textColor=C["texto_suave"], alignment=TA_CENTER),
    "cert_nombre": _estilo("cert_nombre", fontName=FUENTE_PDF_NEGRITA, fontSize=28, leading=36,
                           alignment=TA_CENTER, spaceBefore=6, spaceAfter=6),
    "cert_curso": _estilo("cert_curso", fontName=FUENTE_PDF_NEGRITA, fontSize=20, leading=26,
                          textColor=C["teal_oscuro"], alignment=TA_CENTER, spaceBefore=6, spaceAfter=6),
    "cert_insignia": _estilo("cert_insignia", fontName=FUENTE_PDF_NEGRITA, fontSize=11, leading=15,
                             textColor=C["teal"], alignment=TA_CENTER, spaceBefore=8),
}


class CanvasNumerado(canvas.Canvas):
    """
    Canvas que dibuja encabezado y pie en cada pagina. Guarda las paginas y las
    pinta al final, cuando ya conoce el total ("Pagina X de Y").
    """

    def __init__(self, *args, titulo="", generado="", certificado=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._titulo = titulo
        self._generado = generado
        self._certificado = certificado

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._marco(total)
            super().showPage()
        super().save()

    def _marco(self, total):
        ancho, alto = self._pagesize
        if self._certificado:
            # Doble borde decorativo de la constancia.
            self.setStrokeColor(C["teal"])
            self.setLineWidth(2.5)
            self.rect(8 * mm, 8 * mm, ancho - 16 * mm, alto - 16 * mm)
            self.setStrokeColor(C["linea"])
            self.setLineWidth(0.8)
            self.rect(11 * mm, 11 * mm, ancho - 22 * mm, alto - 22 * mm)

        # Encabezado: logo, titulo del reporte y linea corporativa.
        y_logo = alto - MARGEN - ALTO_LOGO
        self.drawImage(str(RUTA_LOGO), MARGEN, y_logo, width=ANCHO_LOGO, height=ALTO_LOGO, mask="auto")
        self.setFont(FUENTE_PDF, 9)
        self.setFillColor(C["texto_suave"])
        self.drawRightString(ancho - MARGEN, y_logo + 3 * mm, self._titulo)
        self.setStrokeColor(C["teal"])
        self.setLineWidth(1.2)
        self.line(MARGEN, y_logo - 3 * mm, ancho - MARGEN, y_logo - 3 * mm)

        # Pie: generacion y numeracion.
        self.setStrokeColor(C["linea"])
        self.setLineWidth(0.6)
        self.line(MARGEN, MARGEN + 2 * mm, ancho - MARGEN, MARGEN + 2 * mm)
        self.setFont(FUENTE_PDF, 8)
        self.setFillColor(C["texto_tenue"])
        self.drawString(MARGEN, MARGEN - 2 * mm, f"enSEÑArte · Generado el {self._generado}")
        self.drawRightString(ancho - MARGEN, MARGEN - 2 * mm, f"Página {self.getPageNumber()} de {total}")


def _p(texto, estilo):
    """Paragraph con el texto escapado (ReportLab interpreta etiquetas tipo XML)."""
    return Paragraph(escape(str(texto)), ESTILOS[estilo])


def tabla(datos, ancho_disponible):
    """Tabla con encabezado teal, filas alternadas y numeros alineados a la derecha."""
    total = sum(datos.anchos)
    anchos = [ancho_disponible * a / total for a in datos.anchos]
    derecha = [formato in NUMERICOS for formato in datos.formatos]

    filas = [[_p(e, "encabezado_derecha" if d else "encabezado") for e, d in zip(datos.encabezados, derecha)]]
    for fila in datos.filas:
        filas.append([
            _p(como_texto(valor, formato), "celda_derecha" if d else "celda")
            for valor, formato, d in zip(fila, datos.formatos, derecha)
        ])
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), C["teal"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C["blanco"], C["menta"]]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, C["linea"]),
        ("BOX", (0, 0), (-1, -1), 0.5, C["linea"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if not datos.filas:
        filas.append([_p(datos.vacio, "celda")] + [""] * (len(datos.encabezados) - 1))
        estilo.append(("SPAN", (0, 1), (-1, 1)))
    resultado = Table(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
    resultado.setStyle(TableStyle(estilo))
    return resultado


def _historia(reporte, ancho):
    historia = [
        _p(reporte.titulo, "titulo"),
        _p(reporte.subtitulo, "subtitulo"),
        _p(f"Generado el {reporte.generado_texto}", "fecha"),
    ]
    for datos in reporte.tablas:
        historia.append(_p(datos.titulo, "seccion"))
        historia.append(tabla(datos, ancho))
    return historia


def _historia_constancia(reporte, ancho, alto):
    """Portada de la constancia. Siempre cabe en una pagina: si un nombre o un
    curso muy largos no caben, KeepInFrame reduce el contenido."""
    datos = reporte.certificado
    historia = [
        Spacer(1, 2 * mm),
        _p("CONSTANCIA DE CURSO COMPLETADO", "cert_titulo"),
        _p("Se hace constar que", "cert_texto"),
        _p(datos["estudiante"], "cert_nombre"),
        _p("completó satisfactoriamente el curso", "cert_texto"),
        _p(datos["curso"], "cert_curso"),
        _p(f"en la plataforma enSEÑArte, el {datos['fecha']}.", "cert_texto"),
    ]
    if datos["insignia_100"]:
        historia.append(_p("Con la insignia Curso 100 % por acertar todas las preguntas.", "cert_insignia"))
    historia.append(Spacer(1, 6 * mm))
    detalle = tabla(reporte.tablas[0], ancho * 0.62)
    detalle.hAlign = "CENTER"
    historia.append(detalle)
    # La fecha de generacion ya va en el pie de pagina.
    return [KeepInFrame(ancho, alto, historia, mode="shrink", hAlign="CENTER")]


def construir(reporte):
    """Devuelve el PDF como bytes."""
    buffer = BytesIO()
    tamano = landscape(A4) if reporte.horizontal else A4
    documento = SimpleDocTemplate(
        buffer,
        pagesize=tamano,
        leftMargin=MARGEN,
        rightMargin=MARGEN,
        topMargin=MARGEN + ALTO_LOGO + 8 * mm,
        bottomMargin=MARGEN + 8 * mm,
        title=reporte.titulo,
        subject=reporte.subtitulo,
        author="enSEÑArte",
        creator="enSEÑArte",
    )
    if reporte.certificado:
        historia = _historia_constancia(reporte, documento.width, documento.height)
    else:
        historia = _historia(reporte, documento.width)
    documento.build(
        historia,
        canvasmaker=partial(
            CanvasNumerado,
            titulo=reporte.titulo,
            generado=reporte.generado_texto,
            certificado=bool(reporte.certificado),
        ),
    )
    return buffer.getvalue()
