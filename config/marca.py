"""
Identidad visual de enSEÑArte para lo que genera el backend: correos (apps/correos)
y reportes PDF/Excel (apps/reportes).

Los colores son los mismos de ensenarte-frontend/css/tokens.css. Aqui van como
valores literales porque ni los clientes de correo ni ReportLab ni Excel
entienden var(--...). Si cambia la paleta del frontend, cambiala tambien aqui.
"""

from pathlib import Path

RUTA_LOGO = Path(__file__).resolve().parent / "recursos" / "logo.png"
# Proporcion del logo (360x84 px): se dibuja a 180x42 puntos/pixeles.
LOGO_ANCHO, LOGO_ALTO = 180, 42

COLORES = {
    "fondo": "#f6faf8",
    "blanco": "#ffffff",
    "menta": "#e8f2ee",
    "linea": "#dce8e4",
    "tinta": "#1b2f36",
    "texto_suave": "#5c6f75",
    "texto_tenue": "#728589",
    "teal": "#0f7f7a",
    "teal_oscuro": "#075b5b",
    "coral_palido": "#fce4e0",
    "error_texto": "#8a2e24",
}

# Tipografia para correos (cae a Arial si DM Sans no esta instalada).
FUENTE_CORREO = "'DM Sans', Arial, Helvetica, sans-serif"
# Tipografia de los reportes: Helvetica en PDF (fuente base de PDF, no requiere
# incrustarla) y Arial en Excel (misma metrica, instalada en Windows y Office).
FUENTE_PDF = "Helvetica"
FUENTE_PDF_NEGRITA = "Helvetica-Bold"
FUENTE_EXCEL = "Arial"
