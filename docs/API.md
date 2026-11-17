# Contrato de la API

> La referencia completa y siempre actualizada se genera desde el código:
> **Swagger UI** en `/api/docs/`, **ReDoc** en `/api/redoc/` y el esquema
> OpenAPI en `/api/schema/`. Este archivo es un resumen escrito a mano.

URL base en desarrollo: `http://127.0.0.1:8000/api`

Todas las respuestas son JSON con codificación UTF-8.

## Autenticación

La API usa JWT. Tras iniciar sesión se reciben dos tokens:

- `access`: dura 15 minutos y se envía en cada petición protegida.
- `refresh`: dura 7 días y sirve para pedir un `access` nuevo. Se rota: cada
  uso devuelve un refresh nuevo e invalida el anterior.

Detalles y razones en [SEGURIDAD.md](SEGURIDAD.md).

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
    "roles": ["Estudiante"]
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
  "usuario": {
    "nombre": "carlos",
    "correo": "...",
    "estrellas": 2,
    "roles": ["Estudiante"]
  }
}
```

Credenciales inválidas devuelven **401**.

## POST `/auth/refresh/`

**Cuerpo:** `{ "refresh": "<token>" }` → **Respuesta:** `{ "access": "<token nuevo>", "refresh": "<token nuevo>" }`

Hay que guardar los dos: el refresh enviado queda invalidado. Si se reutiliza,
la respuesta es **401**.

## POST `/auth/logout/`

Público, porque el access puede haber vencido. **Cuerpo:** `{ "refresh": "<token>" }`
→ **200** `{}`. Agrega el refresh a la lista negra, y a partir de ahí
`/auth/refresh/` lo rechaza con 401. Un refresh inválido o ya cerrado
devuelve 401.

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

Updated upstream
# 4. Panel administrativo
=======
# Historial de intentos por curso

## GET `/cursos/<slug>/evaluacion/historial/`

Autenticado. Devuelve como máximo los cinco intentos finalizados más recientes
del usuario para ese curso, ordenados del más antiguo al más reciente. Cada
elemento incluye `aciertos`, `errores`, `total` de preguntas y `fecha`. Los
intentos anteriores se eliminan al finalizar un sexto intento.

---

# 4. Evaluación con cámara

El usuario hace con la mano letras del abecedario frente a la cámara y el
**navegador** las reconoce (MediaPipe + KNN, ver [`ml/README.md`](../ml/README.md)).
El video nunca llega al servidor: al terminar la sesión el frontend envía todos
los intentos en una sola petición. Es independiente de la evaluación por curso
de la sección 3.

## POST `/evaluacion-camara/`

Autenticado. Guarda una sesión y devuelve el resultado calculado por el servidor.

```json
{
  "curso": "abecedario",
  "intentos": [
    { "letra_objetivo": "A", "acerto": true,  "tiempo_ms": 2300, "confianza": 0.8 },
    { "letra_objetivo": "B", "acerto": false, "tiempo_ms": 20000 }
  ]
}
```

| Campo | Regla |
|---|---|
| `curso` | Slug del curso de la sesión, obligatorio; el historial y la insignia se vinculan a este curso. |
| `intentos` | Obligatorio, entre 1 y 50 elementos (`EVALUACION_CAMARA_MAX_INTENTOS`) |
| `letra_objetivo` | 1 o 2 caracteres; se recortan espacios y se guarda en mayúscula (`"ll"` → `"LL"`) |
| `acerto` | Booleano, obligatorio |
| `tiempo_ms` | Entero ≥ 0, obligatorio |
| `confianza` | Opcional (o `null`), número entre 0 y 1 |

`total`, `correctas`, `porcentaje`, `aprobado` y `umbral_aplicado` **los
calcula el servidor**. Si el cliente los envía se ignoran (son de solo lectura).

- `total` = número de intentos; `correctas` = intentos con `acerto: true`.
- `porcentaje` = `correctas * 100 // total` (entero, redondeado hacia abajo).
- `aprobado` = `correctas * 100 >= umbral * total`, todo en enteros.
- `umbral_aplicado` = umbral vigente al guardar. Por defecto 70; se cambia con
  la variable de entorno `EVALUACION_CAMARA_UMBRAL_APROBACION`.

Así, 7/10 aprueba y 6/10 no. Respuesta **201**:

```json
{
  "id": 12,
  "fecha": "2026-10-10T15:54:17.596285-05:00",
  "total": 10,
  "correctas": 7,
  "porcentaje": 70,
  "aprobado": true,
  "umbral_aplicado": 70,
  "intentos": [
    { "letra_objetivo": "A", "acerto": true, "tiempo_ms": 2300, "confianza": 0.8 }
  ]
}
```

(`intentos` se devuelve completo; aquí se recorta.) **400** si algo no cumple
las reglas, con el error indexado por la posición del intento (desde 0). No
se guarda nada si un solo intento es inválido:

```json
{ "intentos": { "1": { "tiempo_ms": ["Asegúrese de que este valor es mayor o igual a 0."] } } }
```

```json
{ "intentos": ["Envia al menos un intento."] }
```

## GET `/evaluacion-camara/?curso=<slug>`

Autenticado. Historial de sesiones **del usuario autenticado y del curso
indicado** (nunca las de otros usuarios), de la más reciente a la más antigua,
paginado y limitado a cinco sesiones por curso. Una sesión perfecta establece
permanentemente `insignia_100_ganada` en el progreso del usuario. El recurso
configurado como insignia `curso_100` reemplaza la insignia de curso completado
en el perfil.

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    { "id": 12, "fecha": "...", "total": 10, "correctas": 7, "porcentaje": 70,
      "aprobado": true, "umbral_aplicado": 70, "intentos": [ ... ] }
  ]
}
```

---

# 5. Panel administrativo
>>>>>>> Stashed changes

Todo bajo `/panel/` exige autenticación y un rol (grupo de Django). Sin el
rol necesario devuelve **403** con `detail` explicando el motivo. La tabla
completa de rol contra endpoint está en el README ("Roles y permisos").

| Rol | Endpoints del panel |
|---|---|
| `Administrador` (grupo o superusuario) | Todos |
| `CreadorDeCursos` | Cursos, preguntas, opciones, diccionario, resumen, estrellas y gifs de **todos** los cursos. No escribe en la biblioteca |
| `Profesor` | Lo mismo, pero solo modifica los cursos que **él creó** y su contenido. En los listados solo ve los suyos; abrir o editar uno ajeno devuelve 403 |
| `Interprete` | Biblioteca (`/panel/recursos/`), gifs de preguntas y palabras de cualquier curso y `/panel/archivos/` |
| `Estudiante` | Nada del panel, salvo leer avatares en `/panel/recursos/` |

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

## GET `/panel/estudiantes/estrellas/`

Roles `Profesor`, `CreadorDeCursos` o `Administrador`. Lista de
estudiantes ordenada por estrellas, de mayor a menor.

```json
[
  { "usuario": "carlos", "correo": "carlos@correo.com", "estrellas": 5 },
  { "usuario": "ana", "correo": "ana@correo.com", "estrellas": 2 }
]
```

## POST `/panel/diccionario/<id>/gif/`

Roles `Interprete`, `Profesor` (solo en sus cursos), `CreadorDeCursos` o
`Administrador`. Sube el gif de una palabra del diccionario. `multipart/form-data` con el
archivo en el campo `gif`.

```bash
curl -X POST http://127.0.0.1:8000/api/panel/diccionario/1/gif/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "gif=@sena_a.gif"
```

Guarda el archivo en `MEDIA_ROOT` y actualiza `video_gif` con su URL.
Responde con la palabra actualizada. **400** si falta el archivo.

## POST `/panel/preguntas/<id>/gif/`

Igual que el anterior pero para el campo `video` de una pregunta de
evaluación.

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
