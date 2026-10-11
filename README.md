# enSEÑArte — Backend (API + Base de datos)

API REST del aplicativo de aprendizaje de Lengua de Señas Colombiana (LSC).
Expone el catálogo de cursos, el diccionario visual, el motor de evaluaciones y
el panel administrativo, y guarda los resultados de la evaluación con cámara.
No renderiza ninguna interfaz: el cliente vive en el
repositorio [`ensenarte-frontend`](../ensenarte-frontend).

| | |
|---|---|
| **Framework** | Django 5.2 + Django REST Framework |
| **Autenticación** | JWT (SimpleJWT) |
| **Base de datos** | SQLite en desarrollo, PostgreSQL en producción |
| **Puerto por defecto** | `http://127.0.0.1:8000` |

---

## Arquitectura

```
Navegador ──HTTP/JSON──> API Django (este repo) ──ORM──> Base de datos
   │
   └── HTML/CSS/JS estático (repositorio ensenarte-frontend)
```

Los dos repositorios se despliegan por separado y se comunican únicamente por
HTTP. El backend no conoce las rutas del frontend; el frontend no conoce el
esquema de la base de datos, solo los contratos JSON documentados en
[`docs/API.md`](docs/API.md).

### Estructura del proyecto

```
ensenarte-backend/
├── config/                 Configuración del proyecto Django
│   ├── settings.py         Lee todo de variables de entorno (.env)
│   ├── urls.py             Rutas raíz: /admin/ y /api/
│   ├── wsgi.py / asgi.py
├── apps/
│   ├── usuarios/           Registro, login, perfil, recuperación de contraseña
│   │   ├── models.py       PerfilUsuario
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── signals.py      Crea el perfil automáticamente con cada User
│   ├── cursos/             Dominio principal
│   │   ├── models.py       Curso, Pregunta, OpcionPregunta, PalabraDiccionario,
│   │   │                   ProgresoUsuario, IntentoEvaluacion
│   │   ├── views.py        Catálogo, diccionario y motor de evaluación
│   │   ├── views_panel.py  CRUD administrativo (ViewSets)
│   │   ├── permissions.py  EsCreadorDeCursos, EsProfesor, EsInterprete
│   │   └── management/commands/poblar_datos.py
│   └── evaluacion_camara/  Resultados de la evaluación con cámara
│       ├── models.py       EvaluacionCamara, IntentoCamara
│       ├── serializers.py  Validación y cálculo del resultado
│       └── views.py        POST (guardar sesión) y GET (historial)
├── ml/                     Scripts con los que se entrenó el reconocedor
│                           (el servidor no los usa; ver ml/README.md)
├── docs/
│   ├── API.md              Contrato de todos los endpoints
│   └── MODELO_DATOS.md     Modelo entidad-relación y diccionario de datos
├── requirements.txt
└── .env.example
```

---

## Puesta en marcha

Requisitos: Python 3.11 o superior.

```bash
# 1. Clonar
git clone https://github.com/<tu-usuario>/ensenarte-backend.git
cd ensenarte-backend

# 2. Entorno virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Dependencias
pip install -r requirements.txt

# 4. Variables de entorno
cp .env.example .env             # Windows: copy .env.example .env
```

Genera una `SECRET_KEY` nueva y pégala en `.env`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

```bash
# 5. Migraciones
python manage.py migrate

# 6. Superusuario y datos de ejemplo
python manage.py createsuperuser
python manage.py poblar_datos

# 7. Levantar el servidor
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/api/` y el admin de Django en
`http://127.0.0.1:8000/admin/`.

> Las migraciones están versionadas en `apps/*/migrations/`: `migrate` crea
> todas las tablas, no hace falta `makemigrations` en el primer arranque. Si
> cambias un modelo, genera la migración con `makemigrations` y commitéala
> para que todo el equipo comparta el mismo esquema.

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave criptográfica de Django. Obligatoria. | `k3f8...` |
| `DEBUG` | Modo desarrollo. En producción debe ser `False`. | `True` |
| `ALLOWED_HOSTS` | Dominios autorizados, separados por coma. | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend autorizados. | `http://localhost:5500` |
| `DATABASE_URL` | Cadena de conexión a la base de datos. | `sqlite:///db.sqlite3` |
| `EVALUACION_CAMARA_UMBRAL_APROBACION` | Porcentaje mínimo (entero) para aprobar la evaluación con cámara. Opcional, por defecto `70`. | `70` |

El archivo `.env` está en `.gitignore` y **nunca** debe subirse al repositorio.

---

## Roles y permisos

| Rol | Cómo se asigna | Puede |
|---|---|---|
| Visitante | Sin cuenta | Ver el catálogo de cursos |
| Usuario | Se registra en `/api/auth/registro/` | Diccionario, evaluaciones, perfil |
| Profesor | Grupo `Profesor` | CRUD de diccionario y evaluaciones (`preguntas`/`opciones`), ver `/api/panel/estudiantes/estrellas/`. No administra cursos |
| Interprete | Grupo `Interprete` | Solo subir gifs: `POST /api/panel/diccionario/<id>/gif/` y `POST /api/panel/preguntas/<id>/gif/` |
| Creador de cursos | Grupo `CreadorDeCursos`, o `is_staff` | Todo el CRUD de `/api/panel/`, incluidos cursos |
| Superusuario | `createsuperuser` | Todo, incluido el admin de Django |

Los tres grupos (`CreadorDeCursos`, `Profesor`, `Interprete`) se crean al
ejecutar `poblar_datos`. No hay un registro especial por rol: el usuario se
crea normal en `/api/auth/registro/` (o desde el admin) y luego alguien con
acceso al admin de Django lo asigna al grupo correspondiente desde
Usuarios → seleccionar → Grupos. El login es el mismo para todos los roles;
lo único que cambia son los permisos, visibles en el perfil (`GET
/api/auth/perfil/`) como `es_creador`, `es_profesor` y `es_interprete`.

---

## Cómo funciona la evaluación

En la versión monolítica el estado de la evaluación vivía en `request.session`.
Con el frontend desacoplado no hay sesión de Django, así que el estado se
persiste en el modelo `IntentoEvaluacion`:

1. `POST /api/cursos/<slug>/evaluacion/iniciar/` crea un intento con las
   preguntas del curso en orden aleatorio.
2. `POST .../responder/` recibe `opcion_id` y devuelve si fue correcta.
3. Solo se avanza a la siguiente pregunta al acertar. Cada fallo suma un error.
4. Un acierto solo puntúa si esa pregunta no se había fallado antes.
5. Al terminar, el intento se consolida en `ProgresoUsuario` y se recalculan las
   estrellas del perfil.

Las reglas de puntaje son idénticas a las del proyecto original; lo único que
cambió es dónde se guarda el estado.

---

## Evaluación con cámara

Segunda evaluación, independiente de la anterior. El usuario hace con la mano
letras del abecedario frente a la cámara y el **navegador** las reconoce
(MediaPipe Hands + un clasificador KNN en JavaScript). El video nunca sale del
navegador. Al terminar la sesión, el frontend envía todos los intentos en una
sola petición, y el backend calcula y guarda el resultado.

### Endpoints

Los dos exigen JWT (`Authorization: Bearer <access>`). Cada usuario solo crea y
ve sus propias sesiones. Contrato completo en [`docs/API.md`](docs/API.md),
sección 4.

**`POST /api/evaluacion-camara/`**: guarda una sesión.

```json
{
  "intentos": [
    { "letra_objetivo": "A", "acerto": true,  "tiempo_ms": 2300, "confianza": 0.8 },
    { "letra_objetivo": "B", "acerto": true,  "tiempo_ms": 1800, "confianza": 1.0 },
    { "letra_objetivo": "E", "acerto": false, "tiempo_ms": 20000 }
  ]
}
```

Respuesta `201 Created`:

```json
{
  "id": 1,
  "fecha": "2026-10-10T15:54:17.596285-05:00",
  "total": 3,
  "correctas": 2,
  "porcentaje": 66,
  "aprobado": false,
  "umbral_aplicado": 70,
  "intentos": [
    { "letra_objetivo": "A", "acerto": true,  "tiempo_ms": 2300, "confianza": 0.8 },
    { "letra_objetivo": "B", "acerto": true,  "tiempo_ms": 1800, "confianza": 1.0 },
    { "letra_objetivo": "E", "acerto": false, "tiempo_ms": 20000, "confianza": null }
  ]
}
```

**`GET /api/evaluacion-camara/`**: historial del usuario autenticado, de la
sesión más reciente a la más antigua, con la paginación de DRF (`count`,
`next`, `previous`, `results`). Cada elemento tiene la misma forma que la
respuesta del POST.

### Reglas

- **`total`, `correctas`, `porcentaje` y `aprobado` los calcula el servidor.**
  Son de solo lectura: si el cliente los envía, se ignoran sin error. Lo mismo
  pasa con `umbral_aplicado`.
- `aprobado = correctas * 100 >= umbral * total`, comparando enteros (sin
  flotantes). Con el umbral por defecto (70), 7/10 aprueba y 6/10 no.
- `porcentaje = correctas * 100 // total` (entero, redondeado hacia abajo).
- El umbral se cambia con `EVALUACION_CAMARA_UMBRAL_APROBACION`. Cada sesión
  guarda el umbral con que se calificó, así que el historial no cambia si
  después se ajusta.
- Validación (si falla, `400` y no se guarda nada):
  - `intentos`: entre 1 y 50 elementos.
  - `letra_objetivo`: 1 o 2 caracteres; se guarda en mayúscula (`"ll"` → `"LL"`).
  - `acerto`: obligatorio.
  - `tiempo_ms`: entero mayor o igual a 0.
  - `confianza`: opcional, entre 0 y 1.
- **El servidor confía en `acerto`.** Lo decide el navegador, así que un usuario
  con conocimientos técnicos podría enviar resultados falsos. Esta evaluación
  sirve para practicar, no para certificar.

### Cómo se entrenó el modelo

Los scripts están en [`ml/`](ml/) y se documentan en
[`ml/README.md`](ml/README.md). En resumen:

1. Dataset **LSC70**, parte LSC70ANH: recortes de 120×120 px de la mano dominante,
   grabados por voluntarios de la Universidad del Cauca.
2. MediaPipe Hands extrae los 21 puntos de la mano en cada imagen. Se normalizan
   restando la muñeca, escalando por la distancia muñeca–dedo medio y reflejando
   las manos izquierdas. El navegador repite exactamente esta normalización.
3. Clasificador KNN (k=5, euclidiana) con 150 muestras de referencia por letra,
   incluidas copias giradas ±15° para tolerar una mano inclinada. La
   "confianza" es la fracción de los 5 vecinos que votan por la letra ganadora.
4. Evaluado separando por persona (gente que el modelo no vio), con la regla del
   frontend (letra correcta y confianza ≥ 0.6): **~90 %** de aciertos, y ~88 %
   con la mano girada 15°. SVM, MLP y regresión logística llegan a ~91–93 %,
   pero se mantuvo KNN porque es trivial de ejecutar en JavaScript.

El modelo exportado (`modelo_knn.json`) **se versiona en el repositorio del
frontend** (`prueba-web/modelo_knn.json`), no aquí.

### Límites

- Reconoce solo **20 letras**: A B C D E F I K L M N O P Q R T U V W Y. Faltan
  G, H, J, Ñ, S, X, Z y LL. Varias tienen movimiento, y el modelo mira un solo
  cuadro.
- Letras débiles: E (~62 %), R (~76 %), P (~80 %). Se confunden E→C, P→N
  y R→F.
- Mira solo la forma de la mano: ni movimiento, ni posición respecto al cuerpo,
  ni expresión facial.
- Se entrenó con los 70 voluntarios del dataset, todos jóvenes (18–29 años)
  y casi todos diestros. Con una webcam real (otra luz, otro fondo,
  otra distancia) el rendimiento puede ser menor que el medido.

### Dataset y licencia

LSC70 se publica bajo **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**:
se puede usar y adaptar citando a los autores.

> Muñoz Galindez, J. A., Villota Coral, L. V., & Vargas-Cañas, R. (2024).
> *Speak in Colombian Sign Language: A Dynamic LSC70 Database* (Versión 2)
> [Dataset]. Mendeley Data. https://doi.org/10.17632/9ssyn8tff5.2

> Muñoz Galindez, J. A., Villota Coral, L. V., & Vargas-Cañas, R. (2024).
> The dynamic Colombian sign language dataset for basic conversation LSC70.
> *Data in Brief*, 58, 111213. https://doi.org/10.1016/j.dib.2024.111213

El repositorio no incluye imágenes del dataset (`ml/data/` está en `.gitignore`).

---

## Dónde viven las imágenes y los gifs

La base de datos guarda **solo el nombre del archivo** (por ejemplo
`abecedario/a.gif`). Los archivos en sí son recursos de presentación y están en
el repositorio del frontend, bajo `assets/imagenes/` y `assets/videos/`.

Hay dos excepciones que sí se guardan en este backend, en `MEDIA_ROOT`
(`/media/`):

- Las fotos de perfil que sube el usuario.
- Los gifs que sube el rol **Interprete** vía `POST
  /api/panel/diccionario/<id>/gif/` y `POST /api/panel/preguntas/<id>/gif/`.
  En ese caso el campo `video_gif`/`video` deja de ser un nombre de archivo del
  frontend y pasa a guardar la URL del archivo subido (`/media/...`).

---

## Diferencias respecto a la versión monolítica

| Antes | Ahora | Motivo |
|---|---|---|
| App `LenguaSeñas` (con ñ) | `apps/cursos` y `apps/usuarios` | La ñ en un módulo Python da problemas de importación y codificación |
| `SECRET_KEY` y `DEBUG` en el código | Variables de entorno | No exponer secretos en el repositorio |
| `db.sqlite3` versionado | Ignorado en `.gitignore` | La base de datos no es código fuente |
| Vista `recuperar` cambiaba la clave con solo el nombre de usuario | Flujo de dos pasos con token firmado de un solo uso | Cualquiera podía tomar la cuenta de otro |
| Sin `requirements.txt` | Dependencias fijadas por versión | Reproducibilidad del entorno |
| Estado de evaluación en la sesión | Modelo `IntentoEvaluacion` | El cliente ya no comparte sesión con el servidor |
| Sin `MEDIA_ROOT` pero con `ImageField` | Media configurado | Las fotos de perfil estaban rotas |
| Plantillas Django | API JSON | Requisito de separación front/back |

---

## Pruebas rápidas con curl

```bash
# Registro
curl -X POST http://127.0.0.1:8000/api/auth/registro/ \
  -H "Content-Type: application/json" \
  -d '{"nombre":"prueba","correo":"prueba@correo.com","password":"ClaveSegura123"}'

# Login
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"prueba","password":"ClaveSegura123"}'

# Catálogo (público)
curl http://127.0.0.1:8000/api/cursos/

# Endpoint autenticado
curl http://127.0.0.1:8000/api/auth/perfil/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# Evaluación con cámara: guardar una sesión y ver el historial
curl -X POST http://127.0.0.1:8000/api/evaluacion-camara/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"intentos":[{"letra_objetivo":"A","acerto":true,"tiempo_ms":2300,"confianza":0.8}]}'

curl http://127.0.0.1:8000/api/evaluacion-camara/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

## Tests

```bash
python manage.py test
```

---

## Despliegue

1. `DEBUG=False` y `SECRET_KEY` real en las variables del proveedor.
2. `ALLOWED_HOSTS` con el dominio del backend.
3. `CORS_ALLOWED_ORIGINS` con el dominio del frontend.
4. `DATABASE_URL` apuntando a PostgreSQL.
5. `python manage.py migrate && python manage.py collectstatic --noinput`.
6. Servir con `gunicorn config.wsgi:application`.

---

## Licencia y autoría

Proyecto académico. Repositorio del cliente:
[`ensenarte-frontend`](https://github.com/<tu-usuario>/ensenarte-frontend).
