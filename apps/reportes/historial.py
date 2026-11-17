"""
PDF del historial de intentos de una evaluacion (por preguntas o con camara).

Replica la tarjeta "Tu progreso" que ve el estudiante antes de empezar una
evaluacion (ensenarte-frontend/js/lib/historial-intentos.js + css/extra.css):
mismo titulo que la pagina, anillo con la ultima sesion, comparacion con la
anterior, grafica "Tus ultimos intentos" y tarjetas por sesion. Al final, una
tabla con el detalle de cada sesion.

Los puntajes se calculan igual que en el frontend, para que el PDF muestre
exactamente lo mismo que la pagina.
"""

import math
from dataclasses import dataclass
from functools import partial
from io import BytesIO

from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.graphics.shapes import Circle, Drawing, Line, Path, Rect, String, Wedge
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.cursos.models import Curso, IntentoEvaluacion
from apps.evaluacion_camara.models import EvaluacionCamara
from config.marca import FUENTE_PDF, FUENTE_PDF_NEGRITA

from .modelo import ENTERO, FECHA, MESES, SI_NO, TEXTO, Tabla
from .pdf import ALTO_LOGO, C, ESTILOS, MARGEN, CanvasNumerado, _estilo, _p, tabla

TIPOS = {"preguntas", "camara"}
SESIONES = 5   # el frontend muestra las ultimas 5

ESTILOS_HISTORIAL = {
    "tarjeta_titulo": _estilo("tarjeta_titulo", fontName=FUENTE_PDF_NEGRITA, fontSize=16, leading=20),
    "tarjeta_subtitulo": _estilo("tarjeta_subtitulo", fontSize=10, leading=13, textColor=C["texto_tenue"]),
    "h3": _estilo("h3", fontName=FUENTE_PDF_NEGRITA, fontSize=11.5, leading=15, spaceBefore=4, spaceAfter=6),
    "insignia": _estilo("insignia", fontName=FUENTE_PDF_NEGRITA, fontSize=9.5, leading=12, textColor=C["texto_suave"]),
    "insignia_positiva": _estilo("insignia_positiva", fontName=FUENTE_PDF_NEGRITA, fontSize=9.5, leading=12,
                                 textColor=C["teal_oscuro"]),
    "vacio": _estilo("vacio", fontSize=10.5, leading=14, textColor=C["texto_tenue"]),
}


@dataclass
class Sesion:
    numero: int
    fecha: object
    puntos: int
    aciertos: int
    errores: int | None
    total: int
    aprobado: bool | None = None
    umbral: int | None = None


def _redondear(valor):
    """Math.round de JavaScript (la mitad sube), no el redondeo bancario de Python."""
    return int(math.floor(valor + 0.5))


def _fecha_corta(fecha):
    """'16 nov', como Intl.DateTimeFormat('es-CO', {day, month: 'short'})."""
    fecha = timezone.localtime(fecha)
    return f"{fecha.day} {MESES[fecha.month - 1][:3]}"


# ------------------------------------------------------------------ Datos


def sesiones_de(usuario, curso, tipo):
    """Ultimas 5 sesiones finalizadas, de la mas antigua a la mas reciente."""
    if tipo == "camara":
        registros = list(
            EvaluacionCamara.objects.filter(usuario=usuario, curso=curso).order_by("-fecha", "-id")[:SESIONES]
        )[::-1]
        return [
            Sesion(numero=i, fecha=r.fecha, puntos=max(0, min(100, r.porcentaje)), aciertos=r.correctas,
                   errores=r.total - r.correctas, total=r.total, aprobado=r.aprobado, umbral=r.umbral_aplicado)
            for i, r in enumerate(registros, start=1)
        ]
    registros = list(
        IntentoEvaluacion.objects.filter(usuario=usuario, curso=curso, finalizado=True)
        .order_by("-fecha_inicio", "-id")[:SESIONES]
    )[::-1]
    return [
        Sesion(numero=i, fecha=r.fecha_inicio,
               puntos=max(0, min(100, _redondear(r.aciertos * 100 / r.total_preguntas) if r.total_preguntas else 0)),
               aciertos=r.aciertos, errores=r.errores, total=r.total_preguntas)
        for i, r in enumerate(registros, start=1)
    ]


def nombre_curso(curso):
    """Como nombreCursoParaEvaluacion() del frontend: el titulo del curso."""
    return (curso.titulo or curso.nombre.replace("-", " ").replace("_", " ")).strip()


# ------------------------------------------------------------------ Dibujos


def anillo(puntos, diametro=34 * mm):
    """El anillo 'Ultima sesion': pista menta y avance teal desde arriba, en sentido horario."""
    d = Drawing(diametro, diametro)
    cx = cy = diametro / 2
    exterior = diametro / 2
    interior = exterior - 3.2 * mm
    d.add(Wedge(cx, cy, exterior, 0, 360, radius1=interior, fillColor=C["menta"], strokeColor=None))
    if puntos >= 100:
        d.add(Wedge(cx, cy, exterior, 0, 360, radius1=interior, fillColor=C["teal"], strokeColor=None))
    elif puntos > 0:
        d.add(Wedge(cx, cy, exterior, 90 - puntos * 3.6, 90, radius1=interior, fillColor=C["teal"], strokeColor=None))
    d.add(String(cx, cy + 0.5 * mm, f"{puntos}%", fontName=FUENTE_PDF_NEGRITA, fontSize=21,
                 fillColor=C["teal_oscuro"], textAnchor="middle"))
    d.add(String(cx, cy - 5.5 * mm, "Última sesión", fontName=FUENTE_PDF, fontSize=8,
                 fillColor=C["texto_tenue"], textAnchor="middle"))
    return d


def grafica(sesiones, ancho, alto=44 * mm):
    """'Tus ultimos intentos': curva suave, punto coral por sesion y teal en la ultima."""
    d = Drawing(ancho, alto)
    pie = 8 * mm           # espacio para las etiquetas de abajo
    caja_alto = alto - pie
    d.add(Rect(0, pie, ancho, caja_alto, rx=3 * mm, ry=3 * mm, fillColor=C["fondo"], strokeColor=C["linea"],
               strokeWidth=0.8))
    margen_y = 7 * mm
    util = caja_alto - 2 * margen_y
    medio = pie + margen_y + util / 2
    d.add(Line(4 * mm, medio, ancho - 4 * mm, medio, strokeColor=C["linea"], strokeWidth=0.8, strokeDashArray=[3, 3]))

    cantidad = len(sesiones)
    puntos = [
        (ancho * (i + 0.5) / cantidad, pie + margen_y + s.puntos / 100 * util)
        for i, s in enumerate(sesiones)
    ]
    if cantidad > 1:
        camino = Path(strokeColor=C["teal_claro"], strokeWidth=2.6, fillColor=None,
                      strokeLineCap=1, strokeLineJoin=1)
        camino.moveTo(*puntos[0])
        for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
            dx = (x1 - x0) / 3
            camino.curveTo(x0 + dx, y0, x1 - dx, y1, x1, y1)
        d.add(camino)
    for i, ((x, y), sesion) in enumerate(zip(puntos, sesiones)):
        ultima = i == cantidad - 1
        d.add(Circle(x, y, 2.2 * mm, fillColor=C["teal"] if ultima else C["coral"],
                     strokeColor=C["blanco"], strokeWidth=1.5))
        # En la pagina el valor se ve al pasar el raton; en papel va escrito.
        d.add(String(x, y + 3.6 * mm, f"{sesion.puntos}%", fontName=FUENTE_PDF_NEGRITA, fontSize=8.5,
                     fillColor=C["teal_oscuro"] if ultima else C["texto_suave"], textAnchor="middle"))
        etiqueta = "Hoy" if ultima else f"Intento {i + 1}"
        d.add(String(x, 2.5 * mm, etiqueta, fontName=FUENTE_PDF, fontSize=8.5, fillColor=C["texto_suave"],
                     textAnchor="middle"))
    return d


def comparacion(sesiones):
    """La insignia 'frente a tu sesion anterior' de la pagina."""
    if len(sesiones) < 2:
        return None
    ultima, anterior = sesiones[-1], sesiones[-2]
    diferencia = ultima.puntos - anterior.puntos
    if diferencia == 0:
        texto = f"Sin cambios frente a tu sesión anterior ({anterior.puntos}%)"
    else:
        signo = "+" if diferencia > 0 else ""
        texto = f"{signo}{diferencia} puntos frente a tu sesión anterior ({anterior.puntos}%)"
    estilo = "insignia_positiva" if diferencia > 0 else "insignia"
    # Pildora del ancho del texto, como en la pagina.
    ancho = stringWidth(texto, FUENTE_PDF_NEGRITA, 9.5) + 22
    insignia = Table([[Paragraph(texto, ESTILOS_HISTORIAL[estilo])]], colWidths=[ancho])
    insignia.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C["menta_fuerte"] if diferencia > 0 else C["fondo"]),
        ("ROUNDEDCORNERS", [9, 9, 9, 9]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return insignia


def tarjetas(sesiones, ancho):
    """Una tarjeta por sesion: 'Sesion N', el porcentaje en teal y la fecha corta."""
    columnas = SESIONES
    hueco = 3 * mm
    ancho_tarjeta = (ancho - hueco * (columnas - 1)) / columnas
    celdas = []
    for sesion in sesiones:
        contenido = Table(
            [[Paragraph(f"Sesión {sesion.numero}", _estilo("t1", fontSize=9.5, textColor=C["texto_suave"]))],
             [Paragraph(f"{sesion.puntos}%", _estilo("t2", fontName=FUENTE_PDF_NEGRITA, fontSize=15, leading=19,
                                                      textColor=C["teal"]))],
             [Paragraph(_fecha_corta(sesion.fecha), _estilo("t3", fontSize=8.5, textColor=C["texto_tenue"]))]],
            colWidths=[ancho_tarjeta],
        )
        contenido.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, C["menta"]),
            ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ("BACKGROUND", (0, 0), (-1, -1), C["blanco"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ]))
        celdas.append(contenido)
    celdas += [""] * (columnas - len(celdas))
    fila = []
    anchos = []
    for i, celda in enumerate(celdas):
        fila.append(celda)
        anchos.append(ancho_tarjeta)
        if i < columnas - 1:
            fila.append("")
            anchos.append(hueco)
    resultado = Table([fila], colWidths=anchos)
    resultado.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return resultado


def tarjeta_progreso(sesiones, tipo, ancho):
    """La tarjeta completa 'Tu progreso', con el mismo orden que la pagina."""
    interior = ancho - 2 * 7 * mm
    encabezado = "Tu progreso con cámara" if tipo == "camara" else "Tu progreso"
    contenido = [
        Paragraph(encabezado, ESTILOS_HISTORIAL["tarjeta_titulo"]),
        Paragraph(f"Tus últimas {len(sesiones)} sesiones" if len(sesiones) != 1 else "Tu última sesión",
                  ESTILOS_HISTORIAL["tarjeta_subtitulo"]) if sesiones else
        Paragraph("Revisa tus últimas sesiones", ESTILOS_HISTORIAL["tarjeta_subtitulo"]),
        Spacer(1, 3 * mm),
    ]
    if not sesiones:
        contenido.append(Paragraph("Aún no tienes intentos en esta evaluación.", ESTILOS_HISTORIAL["vacio"]))
    else:
        dibujo = anillo(sesiones[-1].puntos)
        insignia = comparacion(sesiones)
        celdas = [dibujo] + ([insignia] if insignia else [])
        anchos = [dibujo.width + 8 * mm] + ([insignia._colWidths[0]] if insignia else [])
        resumen = Table([celdas], colWidths=anchos, hAlign="CENTER")
        resumen.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        contenido += [
            resumen,
            Spacer(1, 3 * mm),
            Paragraph("Tus últimos intentos", ESTILOS_HISTORIAL["h3"]),
            grafica(sesiones, interior),
            Spacer(1, 3 * mm),
            tarjetas(sesiones, interior),
        ]
    caja = Table([[contenido]], colWidths=[ancho])
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, C["linea"]),
        ("ROUNDEDCORNERS", [14, 14, 14, 14]),
        ("BACKGROUND", (0, 0), (-1, -1), C["blanco"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 7 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm),
    ]))
    return caja


def tabla_detalle(sesiones, tipo):
    if tipo == "camara":
        return Tabla(
            hoja="Detalle", titulo="Detalle de las sesiones",
            encabezados=["Sesión", "Fecha", "Correctas", "Total", "Puntaje (%)", "Umbral (%)", "Aprobada"],
            filas=[[f"Sesión {s.numero}", s.fecha, s.aciertos, s.total, s.puntos, s.umbral, s.aprobado]
                   for s in sesiones],
            formatos=[TEXTO, FECHA, ENTERO, ENTERO, ENTERO, ENTERO, SI_NO],
            anchos=[12, 20, 11, 9, 11, 10, 11],
            vacio="Aún no tienes intentos en esta evaluación.",
        )
    return Tabla(
        hoja="Detalle", titulo="Detalle de las sesiones",
        encabezados=["Sesión", "Fecha", "Aciertos", "Errores", "Preguntas", "Puntaje (%)"],
        filas=[[f"Sesión {s.numero}", s.fecha, s.aciertos, s.errores, s.total, s.puntos] for s in sesiones],
        formatos=[TEXTO, FECHA, ENTERO, ENTERO, ENTERO, ENTERO],
        anchos=[12, 20, 10, 10, 11, 11],
        vacio="Aún no tienes intentos en esta evaluación.",
    )


# ------------------------------------------------------------------ Documento


def construir(usuario, slug, tipo):
    """Devuelve (bytes del PDF, nombre del archivo)."""
    curso = get_object_or_404(Curso, nombre=slug, activo=True)
    sesiones = sesiones_de(usuario, curso, tipo)
    estudiante = usuario.get_full_name() or usuario.username
    modalidad = "Evaluación con cámara" if tipo == "camara" else "Evaluación"
    titulo = f"{nombre_curso(curso)} · {modalidad}"     # el mismo titulo que la pagina
    generado = timezone.localtime()

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, leftMargin=MARGEN, rightMargin=MARGEN,
        topMargin=MARGEN + ALTO_LOGO + 8 * mm, bottomMargin=MARGEN + 8 * mm,
        title=titulo, subject=f"Historial de intentos de {estudiante}", author="enSEÑArte", creator="enSEÑArte",
    )
    historia = [
        _p(titulo, "titulo"),
        _p(f"Historial de intentos de {estudiante}", "subtitulo"),
        _p(f"Generado el {generado.strftime('%d/%m/%Y %H:%M')}", "fecha"),
        tarjeta_progreso(sesiones, tipo, documento.width),
    ]
    if sesiones:
        detalle = tabla_detalle(sesiones, tipo)
        historia.append(KeepTogether([_p(detalle.titulo, "seccion"), tabla(detalle, documento.width)]))
        if tipo == "camara":
            historia.append(Spacer(1, 3 * mm))
            historia.append(Paragraph(
                "Una sesión se aprueba cuando el puntaje alcanza el umbral vigente en ese momento.",
                ESTILOS["fecha"],
            ))
    documento.build(historia, canvasmaker=partial(
        CanvasNumerado, titulo=titulo, generado=generado.strftime("%d/%m/%Y %H:%M"),
    ))
    nombre = f"historial-{curso.nombre}-{'camara' if tipo == 'camara' else 'preguntas'}-{generado:%Y%m%d}.pdf"
    return buffer.getvalue(), nombre
