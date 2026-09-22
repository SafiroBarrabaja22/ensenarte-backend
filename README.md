# enSEÑArte — Backend (API + Base de datos)

API REST del aplicativo de aprendizaje de Lengua de Señas Colombiana (LSC).
Expone el catálogo de cursos, el diccionario visual, el motor de evaluaciones y
el panel administrativo. No renderiza ninguna interfaz: el cliente vive en el
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
│   └── cursos/             Dominio principal
│       ├── models.py       Curso, Pregunta, OpcionPregunta, PalabraDiccionario,
│       │                   ProgresoUsuario, IntentoEvaluacion
│       ├── views.py        Catálogo, diccionario y motor de evaluación
│       ├── views_panel.py  CRUD administrativo (ViewSets)
│       ├── permissions.py  EsCreadorDeCursos, EsProfesor, EsInterprete
│       └── management/commands/poblar_datos.py
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
python manage.py makemigrations usuarios cursos
python manage.py migrate

# 6. Superusuario y datos de ejemplo
python manage.py createsuperuser
python manage.py poblar_datos

# 7. Levantar el servidor
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/api/` y el admin de Django en
`http://127.0.0.1:8000/admin/`.

> Las migraciones no están versionadas en este repositorio: se generan con
> `makemigrations` en el primer arranque. Una vez generadas, **sí** deben
> commitearse para que todo el equipo comparta el mismo esquema.

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave criptográfica de Django. Obligatoria. | `k3f8...` |
| `DEBUG` | Modo desarrollo. En producción debe ser `False`. | `True` |
| `ALLOWED_HOSTS` | Dominios autorizados, separados por coma. | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend autorizados. | `http://localhost:5500` |
| `DATABASE_URL` | Cadena de conexión a la base de datos. | `sqlite:///db.sqlite3` |

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
