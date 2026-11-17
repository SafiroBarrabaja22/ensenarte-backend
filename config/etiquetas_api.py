"""
Etiquetas de la documentacion OpenAPI.

Modulo sin dependencias a proposito: lo importa settings.py (antes de que Django
este listo) y tambien config/openapi.py. Unico lugar con estos nombres.
"""

ETIQUETA_AUTENTICACION = "Autenticación"
ETIQUETA_CURSOS = "Cursos"
ETIQUETA_EVALUACION = "Evaluación"
ETIQUETA_PANEL = "Panel"
ETIQUETA_REPORTES = "Reportes"

DESCRIPCION_ETIQUETAS = [
    {"name": ETIQUETA_AUTENTICACION, "description": "Registro, inicio y cierre de sesión con JWT, perfil y recuperación de contraseña."},
    {"name": ETIQUETA_CURSOS, "description": "Catálogo público, diccionario visual y progreso del estudiante."},
    {"name": ETIQUETA_EVALUACION, "description": "Evaluación por preguntas y evaluación del abecedario con cámara."},
    {"name": ETIQUETA_PANEL, "description": "Administración de cursos, preguntas, opciones, diccionario, gifs y biblioteca visual."},
    {"name": ETIQUETA_REPORTES, "description": "Cifras del panel, estrellas de los estudiantes y reportes descargables en PDF y Excel."},
]
