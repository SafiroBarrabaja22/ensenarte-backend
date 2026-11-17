# enSEÑArte — Backend (API + Base de datos)

[![CI](https://github.com/SafiroBarrabaja22/ensenarte-backend/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SafiroBarrabaja22/ensenarte-backend/actions/workflows/ci.yml)

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
│       ├── permissions.py  Una clase de permiso por rol + combinaciones
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
python manage.py poblar_datos      # cursos de ejemplo + una cuenta demo por rol

# 7. Levantar el servidor
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/api/` y el admin de Django en
`http://127.0.0.1:8000/admin/`.

### Documentación interactiva (OpenAPI)

| Ruta | Qué es |
|---|---|
| `http://127.0.0.1:8000/api/docs/` | **Swagger UI**: probar cada endpoint desde el navegador |
| `http://127.0.0.1:8000/api/redoc/` | **ReDoc**: la misma documentación en formato de lectura |
| `http://127.0.0.1:8000/api/schema/` | Esquema OpenAPI 3 en YAML (para Postman, Insomnia, generadores de clientes) |

Para probar endpoints protegidos en Swagger UI:
1. Ejecuta `POST /api/auth/login/` (por ejemplo con `estudiante_demo` / `Ensenarte2026!`).
2. Copia el `access` de la respuesta.
3. Pulsa **Authorize** y pega el token, sin escribir `Bearer`.

El token se conserva aunque recargues la página. Los endpoints están agrupados
en Autenticación, Cursos, Evaluación, Panel y Reportes, y cada uno documenta
qué roles lo pueden usar y sus respuestas 400, 401, 403 y 404.

Para importar la API en Postman: *Import* → URL `http://127.0.0.1:8000/api/schema/`.

> Las migraciones no están versionadas en este repositorio: se generan con
> `makemigrations` en el primer arranque. Una vez generadas, **sí** deben
> commitearse para que todo el equipo comparta el mismo esquema.

---

## Compartir el contenido con el equipo

Los cursos, preguntas, diccionario y la biblioteca visual se comparten por el
repositorio: los datos en `apps/cursos/fixtures/contenido.json` y los archivos
en `media/biblioteca/` y `media/contenido/`. Usuarios, progreso e intentos no
se comparten.

**Para dejar tu base igual a la del repositorio** (después de `git pull`):

```bash
python manage.py migrate
python manage.py cargar_contenido
```

Reemplaza el contenido local (y borra el progreso de evaluaciones, que depende
de él); los usuarios se conservan.

**Para publicar tus cambios de contenido** al resto del equipo:

```bash
python manage.py exportar_contenido
git add apps/cursos/fixtures/contenido.json media/biblioteca media/contenido
git commit -m "Actualiza contenido"
git push
```

Conviene que una sola persona edite el contenido a la vez: si dos exportan
cambios distintos, el último `contenido.json` reemplaza al anterior.

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave criptográfica de Django. Obligatoria. | `k3f8...` |
| `DEBUG` | Modo desarrollo. En producción debe ser `False`. | `True` |
| `ALLOWED_HOSTS` | Dominios autorizados, separados por coma. | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend autorizados, separados por coma. Sin `*`, sin ruta ni barra final (si no, el backend no arranca). Ver [docs/SEGURIDAD.md](docs/SEGURIDAD.md). | Desarrollo: `http://localhost:5500,http://127.0.0.1:5500` · Producción: `https://safirobarrabaja22.github.io` |
| `JWT_ACCESO_MINUTOS` | Duración del token de acceso. Opcional. | `15` |
| `JWT_REFRESCO_DIAS` | Duración del refresh token (se rota en cada uso). Opcional. | `7` |
| `DATABASE_URL` | Cadena de conexión a la base de datos. | `sqlite:///db.sqlite3` |

El archivo `.env` está en `.gitignore` y **nunca** debe subirse al repositorio.

---

## Roles y permisos

Los roles son grupos de Django. Los nombres están definidos una sola vez en
`apps/usuarios/roles.py`, y los grupos los crea la migración
`usuarios/0003_grupos_de_roles` al correr `migrate`: no hay que crearlos a mano
ni correr ningún comando. Un usuario puede tener varios roles.

| Rol (grupo) | Cómo se asigna | Puede |
|---|---|---|
| Visitante | Sin cuenta | Ver el catálogo de cursos |
| `Estudiante` | Automático al registrarse en `/api/auth/registro/` | Diccionario, evaluaciones (preguntas y cámara), progreso, perfil |
| `Profesor` | Admin de Django → Usuarios → Grupos | Lo de Estudiante + crear cursos y administrar **solo los suyos** (preguntas, opciones, diccionario, gifs), resumen y estrellas |
| `Interprete` | Admin de Django | Lo de Estudiante + biblioteca visual (recursos, avatares, insignias) y gifs de cualquier curso |
| `CreadorDeCursos` | Admin de Django | Lo de Estudiante + administrar el contenido de **todos** los cursos |
| `Administrador` | Admin de Django, o ser superusuario | Todo |

`is_staff` por sí solo ya no da ningún rol: solo permite entrar al admin de
Django. La migración pasó a `Administrador` a los usuarios staff que ya
existían, y a `Estudiante` a las cuentas que no tenían ningún rol.

El perfil (`GET /api/auth/perfil/` y la respuesta del login) devuelve
`"roles": ["Profesor", "Estudiante"]`. Un usuario autenticado sin ningún rol
recibe **403** en todo, salvo su perfil y el cambio de contraseña.

### Rol contra endpoint

✅ permitido · ❌ denegado (403, o 401 sin sesión) · 🔸 solo en los cursos que él creó

| Endpoint | Visitante | Estudiante | Profesor | Intérprete | Creador | Admin |
|---|---|---|---|---|---|---|
| `POST auth/registro/`, `auth/login/`, `auth/refresh/`, `auth/verify/`, `auth/recuperar/*` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET/PATCH auth/perfil/`, `POST auth/cambiar-password/` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET cursos/`, `GET cursos/<slug>/` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET cursos/<slug>/diccionario/`, `GET progreso/` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `cursos/<slug>/evaluacion/*` (iniciar, actual, responder, resultado, historial) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET/POST evaluacion-camara/` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET panel/resumen/`, `GET panel/estudiantes/estrellas/` | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| `GET panel/cursos/` (listado) | ❌ | ❌ | 🔸 | ❌ | ✅ | ✅ |
| `POST panel/cursos/` | ❌ | ❌ | ✅ (queda como dueño) | ❌ | ✅ | ✅ |
| `GET/PATCH/DELETE panel/cursos/<id>/` | ❌ | ❌ | 🔸 | ❌ | ✅ | ✅ |
| CRUD `panel/preguntas/`, `panel/opciones/`, `panel/diccionario/` y `POST panel/diccionario/reordenar/` | ❌ | ❌ | 🔸 | ❌ | ✅ | ✅ |
| `POST panel/diccionario/<id>/gif/`, `POST panel/preguntas/<id>/gif/` | ❌ | ❌ | 🔸 | ✅ | ✅ | ✅ |
| `POST panel/archivos/` | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| `GET panel/recursos/` (biblioteca) | ❌ | Solo avatares | ✅ | ✅ | ✅ | ✅ |
| `POST/PATCH/DELETE panel/recursos/` (recursos, avatares, insignias) | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |

### Cuentas de demostración

`python manage.py poblar_datos` crea (o restablece) una cuenta por rol. Todas
usan la misma contraseña: **`Ensenarte2026!`**

| Usuario | Rol | Para mostrar |
|---|---|---|
| `admin_demo` | Administrador (además es superusuario y entra a `/admin/`) | Acceso total y asignación de roles |
| `creador_demo` | CreadorDeCursos | Edita los cursos de cualquier profesor |
| `profesor_demo` | Profesor | Crea un curso y lo administra |
| `profesor2_demo` | Profesor | Intenta editar el curso de `profesor_demo` y recibe 403 |
| `interprete_demo` | Interprete | Biblioteca visual y gifs |
| `estudiante_demo` | Estudiante | Cursos y evaluaciones; si abre el panel, lo redirige |

Los profesores demo no son dueños de los cursos que ya existen. Para mostrar
el permiso por objeto: entra como `profesor_demo` y crea un curso desde el
panel. Luego entra como `profesor2_demo`: ese curso no aparece en su listado y,
si abre su URL, recibe "Permiso denegado".

> Con `DEBUG=False` el comando **no** crea estas cuentas, porque tienen una
> contraseña conocida. Para forzarlo: `python manage.py poblar_datos --usuarios-demo`.

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

## Pruebas y cobertura

```bash
pip install -r requirements-dev.txt   # pytest, pytest-django, pytest-cov
pytest                                # corre todo y mide cobertura
```

- La suite usa **SQLite en memoria** (`config/settings_pruebas.py`), nunca la
  base del `.env`. Los datos se crean con las fixtures de `tests/conftest.py`
  (usuarios por rol, cursos con preguntas, imágenes en memoria).
- El umbral es **70 %** (`--cov-fail-under=70` en `pytest.ini`). Si la cobertura
  baja de ahí, `pytest` termina con error aunque todas las pruebas pasen.
- El reporte HTML queda en `htmlcov/index.html`. `.coveragerc` excluye
  migraciones, el entorno virtual, settings, `manage.py`, `wsgi.py`, `asgi.py`
  y los propios archivos de prueba.
- `python manage.py test apps` sigue funcionando (también con SQLite en
  memoria), pero solo corre las pruebas de estilo `unittest` de `apps/`; las de
  `tests/` son de pytest.

| Archivo | Qué cubre |
|---|---|
| `tests/test_autenticacion.py` | Registro, login, JWT (ausente, expirado, mal formado, refresh, logout), perfil, contraseñas y recuperación |
| `tests/test_cursos.py` | Catálogo, detalle, diccionario y progreso |
| `tests/test_evaluacion.py` | Evaluación completa de principio a fin, reglas de puntaje, insignia 100 % y límites |
| `tests/test_evaluacion_camara.py` | Sesión con cámara de punta a punta |
| `tests/test_panel.py` | CRUD de cursos, preguntas, opciones y diccionario; quinta opción; gifs, archivos, biblioteca y reportes |
| `tests/test_permisos.py` | Por cada rol, endpoints de otros roles a los que **no** puede entrar (403) |
| `tests/test_comandos.py` | `poblar_datos`, `exportar_contenido`, `cargar_contenido`, `otorgar_insignias_curso_100` |
| `apps/*/tests*.py` | Roles por objeto, JWT/CORS, documentación OpenAPI y cálculo de la evaluación con cámara |

### Integración continua (GitHub Actions)

El workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada
push y en cada pull request, en `main` y en cualquier rama de trabajo. Hace esto:

1. Levanta Python 3.12 y un servicio PostgreSQL 16.
2. Instala `requirements-dev.txt` con caché de pip.
3. Corre `manage.py check` y `makemigrations --check`: falla si alguien cambió
   un modelo sin generar su migración.
4. Corre `pytest` con cobertura, y falla si baja de **70 %**.
5. Publica el reporte HTML como artifact `reporte-cobertura-html` (14 días).
   Se descarga desde la pestaña *Actions* → la ejecución → *Artifacts*, y se
   publica incluso cuando la cobertura no alcanza.

La insignia de arriba muestra el estado en `main`.

**Secrets que hay que crear una sola vez** en GitHub (*Settings → Secrets and
variables → Actions → New repository secret*). Son solo para la base temporal
de la CI; no uses los de producción:

| Secret | Valor sugerido |
|---|---|
| `CI_SECRET_KEY` | Una clave aleatoria de 50 caracteres: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `CI_POSTGRES_USER` | `ensenarte_ci` |
| `CI_POSTGRES_PASSWORD` | Una clave aleatoria de **solo letras y números** (va dentro de una URL) |
| `CI_POSTGRES_DB` | `ensenarte_ci` |

Si falta alguno, el primer paso del workflow falla y dice cuál. GitHub no
entrega secrets a los pull requests que vienen de *forks*, así que en esos PR
la CI falla en ese primer paso.

### Pruebas de las reglas en MySQL

Los triggers y procedimientos (migraciones `cursos/0011` y `0012`) solo existen
en MySQL. Sus pruebas se saltan en SQLite y en la CI. Para correrlas contra el
servidor MySQL de pruebas:

```bash
# PowerShell: $env:PRUEBAS_DATABASE_URL = "mysql://usuario:clave@host:3306/proyecto_pruebas"
PRUEBAS_DATABASE_URL="mysql://usuario:clave@host:3306/proyecto_pruebas" pytest
```

Django crea `test_proyecto_pruebas`, le aplica todas las migraciones, corre la
suite y la borra; `proyecto_pruebas` no se toca. Nunca uses `proyecto_v2`.

---

## Reglas de negocio en la base de datos (MySQL)

Además de la API, la base de datos impide romper estas reglas aunque el cambio
venga del admin de Django, de un script o de una consulta SQL directa:

| Trigger | Regla |
|---|---|
| `opcion_una_correcta_*` | Una pregunta tiene una sola opción correcta (para cambiarla: `CALL marcar_opcion_correcta(id)`) |
| `opcion_maximo_*` | Una pregunta admite como máximo 4 opciones |
| `curso_auditoria_*` | Toda alta, cambio y baja de cursos queda en `cursos_auditoriacurso` (visible en el admin, solo lectura) |
| `progreso_estrellas_*` | Las estrellas del perfil son la cantidad de cursos completados |
| `intento_finalizado_inmutable` | Un intento terminado no admite más respuestas |

| Procedimiento | Qué hace |
|---|---|
| `cerrar_intento_evaluacion(id)` | Consolida el intento en el progreso, la insignia del 100 % y las estrellas |
| `estadisticas_curso(id, umbral)` | Promedios de aciertos y errores, estudiantes que completaron y tasa de aprobación |
| `ranking_estudiantes(n)` | Los n primeros estudiantes por cursos completados y aciertos |
| `clonar_curso(id, slug, usuario)` | Copia preguntas, opciones y palabras bajo un slug nuevo, con los mismos recursos; el clon queda inactivo |
| `purgar_intentos_abandonados(dias)` | Borra intentos sin terminar y sesiones de cámara incompletas de más de N días |
| `marcar_opcion_correcta(id)` | Deja una opción como la única correcta de su pregunta |

Si una regla se viola, MySQL responde con `SIGNAL SQLSTATE '45000'` y un
mensaje en español. Desde Python se usan con `apps/cursos/procedimientos.py`.

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
3. `CORS_ALLOWED_ORIGINS=https://safirobarrabaja22.github.io` (origen de GitHub
   Pages, sin `/ensenarte-frontend/`).
4. `DATABASE_URL` apuntando a PostgreSQL.
5. `python manage.py migrate && python manage.py collectstatic --noinput`.
6. Servir con `gunicorn config.wsgi:application`.

---

## Licencia y autoría

Proyecto académico. Repositorio del cliente:
[`ensenarte-frontend`](https://github.com/<tu-usuario>/ensenarte-frontend).
