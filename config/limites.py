"""
Longitud maxima de los textos que escribe el usuario (unica fuente).

Proteccion contra inyeccion SQL: NO depende de estos limites. Todas las
consultas pasan por el ORM de Django o por cursor.execute con marcadores %s,
que envian el texto a la base como dato separado de la consulta (ver
docs/SEGURIDAD.md, "Inyeccion SQL"). Los limites sirven para:

- Responder 400 con un mensaje claro en vez de un 500 de MySQL ("Data too long").
- Evitar abusos: hashear una "contrasena" de varios MB consume CPU (PBKDF2).

Los campos de modelos (titulo de curso, texto de pregunta, etc.) ya tienen su
max_length en models.py y DRF lo aplica solo. Aqui van los campos que no salen
de un modelo. El frontend usa los mismos valores en sus atributos maxlength.
"""

MAX_NOMBRE_USUARIO = 150   # igual que User.username de Django
MAX_CORREO = 254           # igual que User.email (limite de RFC 5321)
MAX_PASSWORD = 128         # igual que el campo password de Django
MAX_DESCRIPCION_CURSO = 1000
MAX_UID_RECUPERACION = 64
MAX_TOKEN_RECUPERACION = 100
MAX_COMENTARIO_VALIDACION = 500   # comentario del Validador al aprobar o rechazar una sena
