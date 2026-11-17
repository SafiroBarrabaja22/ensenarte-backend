"""
Dibujo de un Reporte en Excel (.xlsx) con openpyxl.

Cada tabla va en su propia hoja con el mismo formato que el PDF: logo arriba,
titulo, fecha de generacion, encabezado con el color corporativo, filas
alternadas y tipografia Arial. Al imprimir, cada hoja lleva encabezado y pie
"Pagina &P de &N" (codigos de Excel para pagina actual y total).

Los valores van con su tipo real (numeros, fechas) para que se puedan ordenar,
filtrar y sumar en Excel; el formato visual va en number_format.
"""

from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ImagenExcel
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config.marca import COLORES, FUENTE_EXCEL, LOGO_ALTO, LOGO_ANCHO, RUTA_LOGO

from .modelo import DECIMAL, ENTERO, FECHA, PORCENTAJE, SI_NO

# openpyxl usa colores RRGGBB sin '#'.
X = {nombre: valor.lstrip("#").upper() for nombre, valor in COLORES.items()}
FILA_ENCABEZADO = 7
LINEA = Side(style="thin", color=X["linea"])

FORMATOS_NUMERO = {
    ENTERO: "#,##0",
    DECIMAL: "#,##0.00",
    PORCENTAJE: "0.0%",
    FECHA: "dd/mm/yyyy hh:mm",
}


def _fuente(**kwargs):
    return Font(name=FUENTE_EXCEL, **{"size": 10, "color": X["tinta"], **kwargs})


def _valor(valor, formato):
    """Valor nativo para la celda de Excel."""
    if valor is None:
        return None
    if formato == SI_NO:
        return "Sí" if valor else "No"
    if formato == ENTERO:
        return int(valor)
    if formato == DECIMAL:
        return float(Decimal(valor))
    if formato == PORCENTAJE:
        return float(Decimal(valor)) / 100   # Excel guarda 0.5 y lo muestra 50,0 %
    if formato == FECHA:
        fecha = timezone.localtime(valor) if timezone.is_aware(valor) else valor
        return fecha.replace(tzinfo=None)    # Excel no admite zona horaria
    return str(valor)


def _encabezado(hoja, reporte, columnas):
    hoja.sheet_view.showGridLines = False
    logo = ImagenExcel(str(RUTA_LOGO))
    logo.width, logo.height = LOGO_ANCHO, LOGO_ALTO
    hoja.add_image(logo, "A1")
    hoja.row_dimensions[1].height = 36

    ultima = get_column_letter(max(columnas, 2))
    for fila, texto, fuente in (
        (3, reporte.titulo, _fuente(size=16, bold=True)),
        (4, reporte.subtitulo, _fuente(size=11, color=X["texto_suave"])),
        (5, f"Generado el {reporte.generado_texto}", _fuente(size=9, color=X["texto_tenue"])),
    ):
        hoja.merge_cells(f"A{fila}:{ultima}{fila}")
        celda = hoja[f"A{fila}"]
        celda.value = texto
        celda.font = fuente
    hoja.row_dimensions[3].height = 24

    # Impresion: encabezado y pie en cada pagina, una pagina de ancho.
    for seccion, texto in (
        (hoja.oddHeader.left, "enSEÑArte"),
        (hoja.oddHeader.right, reporte.titulo),
        (hoja.oddFooter.left, f"Generado el {reporte.generado_texto}"),
        (hoja.oddFooter.right, "Página &P de &N"),
    ):
        seccion.text = texto
        seccion.font = f"{FUENTE_EXCEL},Regular"
        seccion.size = 8
        seccion.color = X["texto_suave"]
    hoja.page_setup.orientation = "landscape" if reporte.horizontal else "portrait"
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.print_title_rows = f"{FILA_ENCABEZADO}:{FILA_ENCABEZADO}"


def _tabla(hoja, datos):
    columnas = len(datos.encabezados)
    for indice, (titulo, ancho) in enumerate(zip(datos.encabezados, datos.anchos), start=1):
        celda = hoja.cell(row=FILA_ENCABEZADO, column=indice, value=titulo)
        celda.font = _fuente(bold=True, color=X["blanco"])
        celda.fill = PatternFill("solid", fgColor=X["teal"])
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = Border(bottom=LINEA)
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    hoja.row_dimensions[FILA_ENCABEZADO].height = 30

    alterna = PatternFill("solid", fgColor=X["menta"])
    if not datos.filas:
        fila = FILA_ENCABEZADO + 1
        hoja.cell(row=fila, column=1, value=datos.vacio).font = _fuente(italic=True, color=X["texto_suave"])
        hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=columnas)
        return
    for numero, valores in enumerate(datos.filas):
        fila = FILA_ENCABEZADO + 1 + numero
        for indice, (valor, formato) in enumerate(zip(valores, datos.formatos), start=1):
            celda = hoja.cell(row=fila, column=indice, value=_valor(valor, formato))
            celda.font = _fuente()
            celda.border = Border(bottom=LINEA)
            celda.alignment = Alignment(vertical="center", wrap_text=formato not in FORMATOS_NUMERO)
            if formato in FORMATOS_NUMERO:
                celda.number_format = FORMATOS_NUMERO[formato]
            if numero % 2 == 1:
                celda.fill = alterna
    ultima = FILA_ENCABEZADO + len(datos.filas)
    hoja.freeze_panes = f"A{FILA_ENCABEZADO + 1}"
    hoja.auto_filter.ref = f"A{FILA_ENCABEZADO}:{get_column_letter(columnas)}{ultima}"


def construir(reporte):
    """Devuelve el .xlsx como bytes."""
    libro = Workbook()
    libro.remove(libro.active)
    for datos in reporte.tablas:
        hoja = libro.create_sheet(datos.hoja[:31])
        _encabezado(hoja, reporte, len(datos.encabezados))
        _tabla(hoja, datos)
    libro.properties.title = reporte.titulo
    libro.properties.subject = reporte.subtitulo
    libro.properties.creator = "enSEÑArte"
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
