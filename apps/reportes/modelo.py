"""
Estructura neutra de un reporte. datos.py la llena; pdf.py y excel.py la dibujan.
Asi los dos formatos muestran exactamente lo mismo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

# Formatos de columna que entienden pdf.py y excel.py.
TEXTO, ENTERO, DECIMAL, PORCENTAJE, FECHA, SI_NO = "texto", "entero", "decimal", "porcentaje", "fecha", "si_no"

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


@dataclass
class Tabla:
    """Una tabla del reporte. En Excel cada tabla va en su propia hoja."""

    hoja: str                 # nombre de la hoja de Excel (max. 31 caracteres)
    titulo: str               # titulo de la seccion en el PDF
    encabezados: list
    filas: list
    formatos: list            # uno de TEXTO, ENTERO, ... por columna
    anchos: list              # ancho de cada columna en caracteres (Excel); proporcion en PDF
    vacio: str = "Sin datos para mostrar."


@dataclass
class Reporte:
    titulo: str
    subtitulo: str
    nombre_archivo: str       # sin extension; solo ASCII
    tablas: list
    horizontal: bool = False
    certificado: dict | None = None   # datos de la portada de una constancia
    generado: datetime = field(default_factory=lambda: timezone.localtime())

    @property
    def generado_texto(self):
        return self.generado.strftime("%d/%m/%Y %H:%M")


def tabla_resumen(pares, hoja="Resumen", titulo="Resumen"):
    """Tabla de dos columnas Concepto | Valor."""
    return Tabla(
        hoja=hoja, titulo=titulo, encabezados=["Concepto", "Valor"],
        filas=[[concepto, valor] for concepto, valor in pares],
        formatos=[TEXTO, TEXTO], anchos=[34, 46],
    )


def fecha_larga(fecha):
    """16 de noviembre de 2026 (sin depender del locale del sistema)."""
    fecha = timezone.localtime(fecha) if timezone.is_aware(fecha) else fecha
    return f"{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"


def como_texto(valor, formato):
    """Representacion de una celda para el PDF (Excel usa el valor nativo)."""
    if valor is None or valor == "":
        return "-"
    if formato == SI_NO:
        return "Sí" if valor else "No"
    if formato == ENTERO:
        return f"{int(valor):,}".replace(",", ".")
    if formato == DECIMAL:
        return f"{Decimal(valor):.2f}".replace(".", ",")
    if formato == PORCENTAJE:
        return f"{Decimal(valor):.1f} %".replace(".", ",")
    if formato == FECHA:
        fecha = timezone.localtime(valor) if timezone.is_aware(valor) else valor
        return fecha.strftime("%d/%m/%Y %H:%M")
    return str(valor)
