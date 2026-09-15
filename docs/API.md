# Contrato de la API

URL base en desarrollo: `http://127.0.0.1:8000/api`

Todas las respuestas son JSON con codificación UTF-8.

## Autenticación

La API usa JWT. Tras iniciar sesión se reciben dos tokens:

- `access`: dura 60 minutos, se envía en cada petición protegida.
- `refresh`: dura 7 días, sirve para pedir un `access` nuevo.

Cabecera en peticiones protegidas:

```
Authorization: Bearer <access>
```

## Formato de errores

Errores de validación (HTTP 400):

```json
{ "correo": ["El correo ya esta en uso."] }
```

Errores de permiso o recurso (HTTP 401, 403, 404):

```json
{ "detail": "Curso no encontrado." }
```

---

# 1. Autenticación y usuarios

## POST `/auth/registro/`

Público. Crea un usuario y su perfil.

**Cuerpo**
```json
{ "nombre": "carlos", "correo": "carlos@correo.com", "password": "ClaveSegura123" }
```

**Respuesta 201**
```json
{
  "mensaje": "Usuario registrado con exito.",
  "usuario": {
    "nombre": "carlos",
    "correo": "carlos@correo.com",
    "avatar": "imgPredeterminadaUsuario.png",
    "foto_perfil_url": null,
    "estrellas": 0,
    "es_creador": false
  }
}
```

La contraseña pasa por los validadores de Django: mínimo 8 caracteres, no
puede ser solo numérica ni una contraseña común.

## POST `/auth/login/`

Público.

**Cuerpo**
```json
{ "username": "carlos", "password": "ClaveSegura123" }
```

**Respuesta 200**
```json
{
  "access": "eyJhbGciOi...",
  "refresh": "eyJhbGciOi...",
  "usuario": { "nombre": "carlos", "correo": "...", "estrellas": 2, "es_creador": false }
}
```

Credenciales inválidas devuelven **401**.

## POST `/auth/refresh/`

**Cuerpo:** `{ "refresh": "<token>" }` → **Respuesta:** `{ "access": "<token nuevo>" }`

## GET `/auth/perfil/`

Autenticado. Devuelve el perfil del usuario del token.

## PATCH `/auth/perfil/`

Autenticado. Campos opcionales: `nombre`, `correo`, `avatar`, `foto_perfil`
(este último requiere `multipart/form-data`).

## POST `/auth/cambiar-password/`

Autenticado.

```json
{ "password_actual": "ClaveVieja123", "password_nueva": "ClaveNueva456" }
```

## POST `/auth/recuperar/solicitar/`

Público. Paso 1 de la recuperación.

```json
{ "correo": "carlos@correo.com" }
```

Responde siempre lo mismo exista o no el correo, para no revelar qué cuentas
están registradas. Con `DEBUG=True` incluye además un objeto `debug` con el
`uid` y el `token`, de modo que el flujo se pueda probar sin servidor de correo.

## POST `/auth/recuperar/confirmar/`

Público. Paso 2.

```json
{ "uid": "MQ", "token": "c1k2-...", "password_nueva": "ClaveNueva456" }
```

El token es de un solo uso y se invalida al cambiar la contraseña.

---

# 2. Catálogo y contenido

## GET `/cursos/`

Público. Lista los cursos activos.

```json
[
  {
    "id": 1,
    "nombre": "abecedario",
    "titulo": "Abecedario",
    "descripcion": "Curso basico del abecedario en LSC.",
    "portada_curso": "portadaAbecedario.jpg",
    "imagen_diccionario": "portadaAbecedario.jpg",
    "imagen_evaluacion": "evaluacionInicio.jpg",
    "activo": true,
    "total_preguntas": 10,
    "total_palabras": 10
  }
]
```

Los campos de imagen son **nombres de archivo**, no URLs: el frontend los
resuelve contra `assets/imagenes/` y `assets/videos/`.

## GET `/cursos/<slug>/`

Público. Detalle de un curso. El `slug` es el campo `nombre`.

## GET `/cursos/<slug>/diccionario/`

Autenticado.

```json
{
  "curso": { "...": "igual que en /cursos/<slug>/" },
  "palabras": [
    { "id": 1, "titulo": "A", "imagen_frontal": "abecedario/a.png", "video_gif": "abecedario/a.gif" }
  ]
}
```

## GET `/progreso/`

Autenticado. Progreso del usuario en todos los cursos.

```json
[
  {
    "curso": "abecedario",
    "curso_titulo": "Abecedario",
    "aciertos": 8,
    "errores": 3,
    "completado": true,
    "fecha_ultima_actividad": "2026-03-01T14:22:10Z"
  }
]
```

---

# 3. Evaluación

Flujo completo:

```
iniciar/  ──>  actual/  ──>  responder/  ──(correcta)──>  siguiente pregunta
                                  │
                                  └──(última)──>  resultado/
```

## POST `/cursos/<slug>/evaluacion/iniciar/`

Autenticado. Crea un intento nuevo y descarta cualquier intento abierto previo
del mismo usuario y curso.

**Respuesta 201**
```json
{
  "id": 7,
  "total": 10,
  "actual": 1,
  "aciertos": 0,
  "errores": 0,
  "finalizado": false,
  "pregunta": {
    "id": 3,
    "texto": "Cual es la sena para la letra A?",
    "video": "abecedario/a.gif",
    "opciones": [
      { "id": 9, "texto": "B" },
      { "id": 8, "texto": "A" }
    ]
  }
}
```

Las opciones llegan barajadas y **sin** el campo `es_correcta`. Si el curso no
tiene preguntas responde **404**.

## GET `/cursos/<slug>/evaluacion/actual/`

Autenticado. Devuelve el intento en curso con la misma forma de arriba. Si no
hay ninguno abierto responde **404**, señal para llamar a `iniciar/`.

## POST `/cursos/<slug>/evaluacion/responder/`

Autenticado. **Cuerpo:** `{ "opcion_id": 8 }`

Respuesta si la opción es correcta y quedan preguntas:
```json
{ "correcta": true, "mensaje": "Correcto.", "finalizado": false, "siguiente": { "...": "intento actualizado" } }
```

Respuesta si es incorrecta:
```json
{ "correcta": false, "mensaje": "Incorrecto, intenta de nuevo.", "finalizado": false, "estado": { "...": "misma pregunta" } }
```

Respuesta al acertar la última:
```json
{
  "correcta": true,
  "mensaje": "Correcto.",
  "finalizado": true,
  "resultado": { "curso": "abecedario", "curso_titulo": "Abecedario", "aciertos": 9, "errores": 2, "mensaje": "Sigue practicando, vas muy bien." }
}
```

Si `opcion_id` no pertenece a la pregunta actual responde **400**.

## GET `/cursos/<slug>/evaluacion/resultado/`

Autenticado. Resultado del último intento finalizado. **404** si nunca terminó
una evaluación de ese curso.

Escala de mensajes: 0 errores → felicitación; hasta 15 → ánimo; hasta 30 →
"la práctica hace al maestro"; más de 30 → sugiere repasar el diccionario.

---

# 4. Panel administrativo

Todo bajo `/panel/` exige pertenecer al grupo `CreadorDeCursos`, o ser `staff`
o superusuario. En caso contrario devuelve **403**.

Las listas usan la paginación por defecto de DRF:

```json
{ "count": 12, "next": null, "previous": null, "results": [] }
```

## GET `/panel/resumen/`

```json
{ "total_cursos": 2, "cursos_activos": 2, "total_preguntas": 15, "total_palabras": 15, "total_usuarios": 4 }
```

## `/panel/cursos/`

CRUD completo: `GET` (lista), `POST` (crear), `GET /<id>/`, `PATCH /<id>/`,
`DELETE /<id>/`. El campo `creado_por` se asigna solo con el usuario del token.

**Cuerpo de creación**
```json
{
  "nombre": "saludos",
  "titulo": "Saludos y cortesia",
  "descripcion": "Expresiones basicas.",
  "portada_curso": "cursos.jpg",
  "imagen_diccionario": "livres.jpg",
  "imagen_evaluacion": "evaluacionInicio.jpg",
  "activo": true
}
```

`nombre` debe ser un slug único (minúsculas, sin espacios ni tildes).

## `/panel/preguntas/`

CRUD completo. Filtro: `GET /panel/preguntas/?curso=<id>`.
Campos: `curso` (id), `texto`, `video`. Incluye sus `opciones` en la lectura.

## `/panel/opciones/`

CRUD completo. Filtro: `GET /panel/opciones/?pregunta=<id>`.
Campos: `pregunta` (id), `texto`, `es_correcta`.

Dos reglas aplicadas en el servidor:
- Máximo 4 opciones por pregunta (la quinta devuelve 400).
- Marcar una opción como correcta desmarca automáticamente las demás.

## `/panel/diccionario/`

CRUD completo. Filtro: `GET /panel/diccionario/?curso=<id>`.
Campos: `curso` (id), `titulo`, `imagen_frontal`, `video_gif`.

---

# Códigos de estado

| Código | Significado |
|---|---|
| 200 | Operación exitosa |
| 201 | Recurso creado |
| 204 | Eliminado, sin contenido |
| 400 | Datos inválidos |
| 401 | Falta el token o expiró |
| 403 | Autenticado pero sin permisos |
| 404 | El recurso no existe |
