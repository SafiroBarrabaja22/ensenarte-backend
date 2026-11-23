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
| **Base de datos** | MySQL (producción y equipo); SQLite en memoria para las pruebas |
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
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend autorizados, separados por coma. Sin `*`, sin ruta ni barra final (si no, el backend no arranca). Ver [docs/SEGURIDAD.md](docs/SEGURIDAD.md). | Desarrollo: `http://localhost:5500,http://127.0.0.1:5500` · Producción (Docker): `https://<dominio>.ts.net` |
| `JWT_ACCESO_MINUTOS` | Duración del token de acceso. Opcional. | `15` |
| `JWT_REFRESCO_DIAS` | Duración del refresh token (se rota en cada uso). Opcional. | `7` |
| `DATABASE_URL` | Cadena de conexión a la base de datos (si no hay `DB_NAME`). | `sqlite:///db.sqlite3` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL por variables; si `DB_NAME` existe tiene prioridad sobre `DATABASE_URL`. Es lo que usa Docker. | `proyecto_v2`, …, `host.docker.internal`, `3306` |

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

1. Levanta Python 3.12. No usa ningún servidor de base de datos: las pruebas
   corren sobre **SQLite en memoria**, igual que en local.
2. Comprueba que `requirements-ci.txt` esté al día e instala esas dependencias: versiones
   exactas con hash (`--require-hashes`) y solo paquetes precompilados (`--only-binary :all:`).
   Si cambias `requirements.txt` o `requirements-dev.txt`, regenera `requirements-ci.txt` con
   el comando de la cabecera de `requirements-ci.in`. Si cambias `requirements.txt`, regenera
   también `requirements-docker.txt`, el que instala el Dockerfile (comando en la cabecera de
   `requirements-docker.in`); el mismo paso de la CI lo revisa.
3. Corre `manage.py check` y `makemigrations --check`: falla si alguien cambió
   un modelo sin generar su migración.
4. Corre `pytest` con cobertura, y falla si baja de **70 %**.
5. Publica el reporte HTML como artifact `reporte-cobertura-html` (14 días).
   Se descarga desde la pestaña *Actions* → la ejecución → *Artifacts*, y se
   publica incluso cuando la cobertura no alcanza.

La insignia de arriba muestra el estado en `main`.

**Secret que hay que crear una sola vez** en GitHub (*Settings → Secrets and
variables → Actions → New repository secret*). Es solo para la CI; no uses la
clave de producción:

| Secret | Valor sugerido |
|---|---|
| `CI_SECRET_KEY` | Una clave aleatoria de 50 caracteres: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |

Si falta, el primer paso del workflow falla y lo dice. GitHub no
entrega secrets a los pull requests que vienen de *forks*, así que en esos PR
la CI falla en ese primer paso.

### Pruebas de las reglas en MySQL

Los triggers y procedimientos almacenados (migraciones `cursos/0011` y `0012`)
solo existen en MySQL: en SQLite esas migraciones no ejecutan nada. Por eso sus
pruebas **se saltan en local y en la CI**, que corren sobre SQLite en memoria:

- `tests/test_reglas_mysql.py`: las 39 pruebas de triggers y procedimientos.
- `tests/test_reportes.py`: 1 prueba del reporte de estadísticas de la
  plataforma, que usa los procedimientos.

Por eso `pytest` muestra "40 skipped" y la CI pasa en verde sin haberlas
ejecutado. **Antes de subir cambios a los triggers, los procedimientos o el
código que los usa, córrelas a mano** contra el servidor MySQL de pruebas:

```bash
# PowerShell: $env:PRUEBAS_DATABASE_URL = "mysql://usuario:clave@host:3306/proyecto_pruebas"
PRUEBAS_DATABASE_URL="mysql://usuario:clave@host:3306/proyecto_pruebas" pytest
```

Django crea `test_proyecto_pruebas`, le aplica todas las migraciones, corre la
suite y la borra; `proyecto_pruebas` no se toca. Nunca uses `proyecto_v2`
(`config/settings_pruebas.py` se niega a correr contra ella).

Para correr solo las pruebas que dependen de MySQL (más rápido; `--no-cov`
porque solas no llegan al 70 %):

```bash
PRUEBAS_DATABASE_URL="mysql://usuario:clave@host:3306/proyecto_pruebas"   pytest tests/test_reglas_mysql.py tests/test_reportes.py --no-cov
```

---

## Correos

La app `apps/correos` envía tres correos con plantilla HTML y versión en texto
plano (`EmailMultiAlternatives`):

| Correo | Cuándo | Para quién |
|---|---|---|
| Bienvenida | Al registrarse | El nuevo estudiante |
| Resultados | Al terminar una evaluación por preguntas (aciertos, errores, porcentaje y mensaje) | El estudiante |
| Curso completado | La primera vez que un estudiante completa un curso, por preguntas o con cámara | El profesor que creó el curso |

- **Desarrollo:** con `DEBUG=True` los correos se imprimen en la consola de
  `runserver` y no se envía nada.
- **Producción:** con `DEBUG=False` se usa SMTP con `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL`
  (ver `.env.example`). `URL_FRONTEND` define los enlaces de los botones.
- **Compatibilidad con clientes de correo:** maquetación con tablas, estilos
  solo en línea, ancho máximo de 600px y logo incrustado por Content-ID
  (`apps/correos/recursos/logo.png`), no enlazado.
- **Robustez:** el envío se programa con `transaction.on_commit` y cualquier
  error (SMTP caído, credenciales, plantilla) queda en el log sin afectar el
  registro ni la evaluación. `EMAIL_TIMEOUT` (10 s) limita la espera.

Las plantillas están en `apps/correos/templates/correos/`: `base.html` y, para
cada correo, `<nombre>.html` y `<nombre>.txt`.

---

## Reportes en PDF y Excel

App `apps/reportes`: ReportLab para el PDF y openpyxl para el Excel (no se usa
WeasyPrint, que necesita GTK en Windows). Cada reporte se pide con
`?formato=pdf` (por defecto) o `?formato=xlsx`:

| Reporte | Endpoint | Quién |
|---|---|---|
| Constancia de curso completado | `GET /api/reportes/constancia/<slug>/` | El propio estudiante (cualquier rol), solo si completó el curso |
| Progreso de los estudiantes de un curso | `GET /api/reportes/cursos/<id>/progreso/` | Profesor (solo sus cursos), CreadorDeCursos, Administrador |
| Estadísticas de la plataforma | `GET /api/reportes/plataforma/` | Administrador. Usa los procedimientos `estadisticas_curso` y `ranking_estudiantes`: solo con MySQL (si no, 503) |
| Historial de intentos de una evaluación (solo PDF) | `GET /api/reportes/historial/<slug>/?tipo=preguntas\|camara` | El propio estudiante (cualquier rol). Botón "Exportar PDF" en la tarjeta "Tu progreso" de cada evaluación; mismo título y diseño que la página |

Formato común: logo arriba, título, fecha de generación, tipografía Helvetica
(PDF) / Arial (Excel), encabezados de tabla teal, filas alternadas y
numeración ("Página X de Y" en el PDF, `&P de &N` en el pie de impresión del
Excel). En Excel los números y fechas son valores reales (se pueden ordenar,
filtrar y sumar). La constancia siempre cabe en una página.

**Descarga desde el frontend:** un enlace directo no lleva el token JWT y la
API responde 401. El frontend pide el archivo con `fetch` y la cabecera
`Authorization`, lo convierte en blob y lo descarga. El nombre llega en
`Content-Disposition`, que se expone por CORS (`CORS_EXPOSE_HEADERS`).

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

## Despliegue con Docker

La aplicación corre en la miniPC (CachyOS) con Docker y se publica con HTTPS por
**Tailscale Funnel**. MySQL **no** está en Docker: es el que ya está instalado en
la miniPC.

```
Navegador ──https──▶ Tailscale Funnel ──▶ 127.0.0.1:8080  frontend (nginx)
                                                │  páginas, CSS, JS, assets
                                                └─ /api/ /admin/ /media/ /static/ ──▶ backend:8000 (gunicorn)
                                                                                          │
                                                          host.docker.internal:3306 ◀──────┘  MySQL de la miniPC
```

- **Una sola entrada:** el nginx del frontend sirve las páginas y reenvía la API al
  backend. Todo queda en el mismo dominio: no hay CORS, y la cámara de la
  evaluación funciona porque va por HTTPS.
- **Puertos solo locales:** el 8080 y el 8000 escuchan solo en `127.0.0.1`. Desde
  fuera solo se entra por Funnel.
- **Archivos de los docentes:** viven en el volumen `ensenarte_media`, que no se
  pierde al reconstruir.
- **Modelo de la cámara:** el reconocimiento corre en el navegador. El frontend carga
  `assets/modelos/modelo_knn.json`, que entra en la imagen del frontend, y MediaPipe
  desde su CDN. `ml/` (dataset, `landmarks.csv` y pruebas de ajuste) no se usa en tiempo
  de ejecución y queda fuera de la imagen del backend. Si se reentrena el modelo, copia
  el nuevo `ml/modelo_knn.json` a `ensenarte-frontend/assets/modelos/`.
- **Archivos:**
  - [Dockerfile](Dockerfile) y [.dockerignore](.dockerignore);
  - [despliegue/docker-compose.yml](despliegue/docker-compose.yml);
  - [despliegue/docker.env.example](despliegue/docker.env.example);
  - el `Dockerfile` y el `docker/nginx.conf` del frontend.

> El despliegue anterior (gunicorn como servicio de systemd, [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md)
> y `despliegue/desplegar.sh`) está **obsoleto**. Se conserva como referencia, pero no
> lo uses junto con Docker: los dos ocupan el puerto 8000.

### 1. Instalar Docker en la miniPC

```bash
sudo pacman -S --needed git docker docker-compose docker-buildx
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"     # luego cierra sesión y vuelve a entrar
docker compose version
```

### 2. Apagar el despliegue anterior (si se instaló)

```bash
sudo systemctl disable --now ensenarte-backend   # detiene y quita del arranque el servicio viejo
systemctl status ensenarte-backend --no-pager     # "inactive (dead)" o "could not be found": bien
sudo tailscale funnel reset                       # borra el Funnel viejo, que apuntaba al 8000
ss -ltn | grep -E ':(8000|8080) ' || echo "puertos 8000 y 8080 libres"
```

No hace falta borrar `/etc/systemd/system/ensenarte-backend.service`; deshabilitado no
arranca.

### 3. Preparar MySQL para la red de Docker

El contenedor llega al MySQL de la miniPC por `host.docker.internal`, que es la IP del
puente de Docker (normalmente `172.17.0.1`). La conexión llega desde una IP `172.x`.

1. **Que el servicio esté encendido y arranque con la miniPC.** Esto va primero: si MySQL
   está apagado, el 3306 aparece cerrado aunque `bind-address` esté bien.
   ```bash
   systemctl list-unit-files | grep -Ei 'mariadb|mysqld'   # nombre del servicio: mariadb o mysqld
   systemctl status mariadb --no-pager                     # "inactive (dead)" o "disabled": está apagado
   sudo systemctl enable --now mariadb                     # (o mysqld) lo enciende y lo deja en el arranque
   systemctl is-enabled mariadb && systemctl is-active mariadb   # enabled / active
   ```
   Si no arranca, el motivo está en `journalctl -u mariadb -b --no-pager | tail -n 30`.
2. **`bind-address` no puede ser solo `127.0.0.1`.** Con el servicio ya activo, mira dónde
   escucha:
   ```bash
   sudo ss -ltnp | grep 3306
   ```
   - Si sale `127.0.0.1:3306`, edita `[mysqld]` en `/etc/my.cnf.d/server.cnf` (MariaDB)
     o en `/etc/mysql/my.cnf` (MySQL), pon `bind-address = 0.0.0.0` y reinicia con
     `sudo systemctl restart mariadb` (o `mysqld`).
   - Si ya sale `0.0.0.0:3306` o `*:3306` (por ejemplo, porque el equipo se conecta por
     Tailscale), no cambies nada.
   - No uses `bind-address = 172.17.0.1`: al arrancar la miniPC, MySQL puede iniciar antes
     que Docker, y entonces esa IP todavía no existe.
3. **Firewall: el 3306 solo para Docker y Tailscale.** Con `bind-address = 0.0.0.0`, MySQL
   escucha en todas las interfaces, también en la de la red local. El firewall deja entrar
   al 3306 solo desde la red de Docker (`172.16.0.0/12`) y desde Tailscale (`100.64.0.0/10`
   por la interfaz `tailscale0`), y bloquea el resto. Ver [Firewall para MySQL](#firewall-para-mysql).
4. **El usuario de la aplicación debe poder entrar desde la red de Docker:**
   ```sql
   -- sudo mariadb   (o: mysql -u root -p)
   CREATE USER '<usuario_bd>'@'172.%' IDENTIFIED BY '<clave_bd>';
   GRANT ALL PRIVILEGES ON proyecto_v2.* TO '<usuario_bd>'@'172.%';
   FLUSH PRIVILEGES;
   ```
   Si el usuario ya existe como `'<usuario_bd>'@'%'`, ya cubre `172.%` y no hace falta
   crearlo de nuevo.

#### Firewall para MySQL

**Primero, mira cuál firewall está activo.** CachyOS trae **ufw** activado de fábrica,
pero puede haberse cambiado:

```bash
systemctl is-active ufw firewalld nftables    # el que diga "active" es el que manda
sudo ufw status verbose                       # ufw: "Status: active"
sudo firewall-cmd --state                     # firewalld: "running"
sudo nft list ruleset | head -n 40            # todos usan nftables por debajo; esto muestra las reglas
```

Usa solo **uno** de los tres bloques de abajo, el del firewall activo.

- **Si los tres dicen `inactive`:** activa ufw. Pero si entras a la miniPC por SSH desde la
  red local, permite el SSH antes de activarlo:
  ```bash
  sudo pacman -S --needed ufw
  sudo ufw allow ssh
  sudo systemctl enable --now ufw
  sudo ufw enable
  ```
- **Los puertos 8080 y 8000 no necesitan reglas:** escuchan solo en `127.0.0.1`, y Funnel
  entra por `tailscaled`, que es un proceso local.

**ufw (lo normal en CachyOS)**

```bash
sudo ufw status numbered | grep 3306                                  # si hay un "3306 ALLOW Anywhere" viejo, bórralo:
# sudo ufw delete <número>
sudo ufw allow proto tcp from 172.16.0.0/12 to any port 3306 comment 'MySQL desde Docker'
sudo ufw allow in on tailscale0 proto tcp from 100.64.0.0/10 to any port 3306 comment 'MySQL desde Tailscale'
sudo ufw deny 3306/tcp                                                # todo lo demás
sudo ufw status numbered                                              # las dos ALLOW antes que la DENY
```

ufw aplica las reglas en orden: las dos `ALLOW` deben salir con número menor que la
`DENY`. Si la `DENY` quedó antes, bórrala y vuelve a crearla.

**firewalld**

```bash
Z=$(sudo firewall-cmd --get-default-zone)                    # normalmente "public"
sudo firewall-cmd --get-active-zones                          # ¿tailscale0 está en otra zona? usa esa en su regla
sudo firewall-cmd --permanent --zone="$Z" --remove-service=mysql 2>/dev/null; true
sudo firewall-cmd --permanent --zone="$Z" --remove-port=3306/tcp 2>/dev/null; true
sudo firewall-cmd --permanent --zone="$Z" --add-rich-rule='rule family="ipv4" source address="172.16.0.0/12" port port="3306" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone="$Z" --add-rich-rule='rule family="ipv4" source address="100.64.0.0/10" port port="3306" protocol="tcp" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --zone="$Z" --list-all                      # 3306 solo en las dos rich rules
```

- Así, lo que no coincide con las dos reglas cae en el rechazo por defecto de la zona.
- Docker pone sus redes en su propia zona `docker`, que ya acepta el tráfico de los
  contenedores. La regla de `172.16.0.0/12` cubre el caso en que no lo haga.

**nftables a mano (sin ufw ni firewalld)**

En `/etc/nftables.conf`, dentro de `chain input` de `table inet filter`, agrega estas
reglas **antes** de la regla final de rechazo (`reject` o `counter drop`):

```
tcp dport 3306 ip saddr 172.16.0.0/12 accept comment "MySQL desde Docker"
iifname "tailscale0" tcp dport 3306 ip saddr 100.64.0.0/10 accept comment "MySQL desde Tailscale"
tcp dport 3306 drop comment "MySQL: nadie mas"
```

```bash
sudo nft -c -f /etc/nftables.conf            # revisa la sintaxis sin aplicar nada
sudo systemctl restart nftables
sudo systemctl restart docker tailscaled     # el archivo empieza con "flush ruleset" y borra sus reglas
cd /srv/ensenarte && docker compose up -d
```

**Comprobar (con cualquiera de los tres)**

```bash
# Desde el contenedor (cuando ya esté levantado, paso 5): debe decir "ok"
docker compose exec backend python -c "import socket; socket.create_connection(('host.docker.internal', 3306), 3); print('ok')"
# Desde otro equipo de la red local, SIN Tailscale: debe fallar (timeout o refused)
nc -zv -w 3 <ip-lan-de-la-minipc> 3306
# Desde un equipo de la tailnet: debe conectar
nc -zv -w 3 <ip-100.x-de-la-minipc> 3306
```

### 4. Código y configuración

```bash
sudo mkdir -p /srv/ensenarte && sudo chown -R "$USER": /srv/ensenarte
cd /srv/ensenarte
git clone https://github.com/SafiroBarrabaja22/ensenarte-backend.git
git clone https://github.com/SafiroBarrabaja22/ensenarte-frontend.git
# Si ya estaban clonados: git -C <repo> switch main && git -C <repo> pull
git -C ensenarte-backend branch --show-current && git -C ensenarte-frontend branch --show-current   # main / main
cp ensenarte-backend/despliegue/docker-compose.yml .
cp ensenarte-backend/despliegue/docker.env.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"            # cópiala en SECRET_KEY
nano .env                                                                # completa lo que va entre <...>
```

Debe quedar así:

```
/srv/ensenarte/
├── docker-compose.yml
├── .env
├── ensenarte-backend/
└── ensenarte-frontend/
```

Las variables están explicadas en `despliegue/docker.env.example` y en la tabla de
[docs/DESPLIEGUE.md](docs/DESPLIEGUE.md). Las más importantes:

| Variable | Valor |
|---|---|
| `DB_HOST` | `host.docker.internal` |
| `NUM_PROXIES` | `2` (Funnel y nginx) |
| `ALLOWED_HOSTS` | el dominio `.ts.net`, `localhost` y `127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `URL_FRONTEND` | `https://<dominio>.ts.net` |

### 5. Construir y levantar

```bash
cd /srv/ensenarte
docker compose up -d --build
docker compose ps                                                   # backend "healthy" al minuto
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py check --deploy         # solo el aviso W021 (HSTS preload) es esperado
```

### 6. Publicar con HTTPS (Tailscale Funnel)

```bash
sudo tailscale funnel --bg 8080
tailscale funnel status          # https://<maquina>.<tailnet>.ts.net (Funnel on) -> http://127.0.0.1:8080
```

En la consola de Tailscale de la tailnet dueña de la miniPC tienen que estar activos
*HTTPS Certificates* y el permiso de Funnel para el nodo (ver la sección 1.8 de
[docs/DESPLIEGUE.md](docs/DESPLIEGUE.md)). `--bg` deja la configuración guardada, así que
sobrevive a los reinicios.

### 7. Verificar

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/              # 200: página de inicio
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/cursos/   # 200: API por el proxy
curl -sI https://<maquina>.<tailnet>.ts.net/admin/login/ | head -1            # desde otra red: 200
```

Después abre `https://<maquina>.<tailnet>.ts.net/` en el navegador. El admin está en
`/admin/` (debe verse con estilos) y Swagger en `/api/docs/`.

### 8. Actualizar

```bash
cd /srv/ensenarte
git -C ensenarte-backend pull && git -C ensenarte-frontend pull
cp ensenarte-backend/despliegue/docker-compose.yml .     # por si cambió
docker compose up -d --build
docker compose exec backend python manage.py migrate
```

### 9. Operación

| Para | Comando |
|---|---|
| Logs en vivo | `docker compose logs -f backend` (o `frontend`) |
| Estado | `docker compose ps` |
| Reiniciar | `docker compose restart backend` |
| Apagar / encender | `docker compose down` / `docker compose up -d` (los datos de `media` se conservan) |
| Respaldar la base | En la miniPC: `mysqldump -u <usuario_bd> -p --single-transaction --routines --triggers proyecto_v2 \| gzip > proyecto_v2-$(date +%F).sql.gz` |
| Respaldar `media` | `docker run --rm -v ensenarte_media:/media -v "$PWD":/respaldo alpine tar czf /respaldo/media-$(date +%F).tgz -C /media .` |

- **Primera vez:** el volumen `ensenarte_media` se llena con `media/biblioteca` y
  `media/contenido` del repositorio.
- **Después:** guarda lo que suben los docentes. Si llegan imágenes nuevas a esas
  carpetas por git, cópialas al volumen:
  `docker compose cp ensenarte-backend/media/biblioteca/. backend:/app/media/biblioteca/`.

### Si algo falla

| Síntoma | Dónde mirar | Causa probable |
|---|---|---|
| `docker compose up --build` falla en `pip install` con `mysql_config` / `pkg-config` | salida del build | No se instalaron `default-libmysqlclient-dev` y `pkg-config` (Dockerfile, etapa 1) |
| Falla en `collectstatic` | salida del build | Error de `settings.py`; el mensaje dice qué variable falta |
| `backend` reinicia una y otra vez | `docker compose logs backend` | `ImproperlyConfigured`: falta una variable en `.env` o `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` llevan ruta o `*` |
| `Can't connect to MySQL server on 'host.docker.internal'` | `docker compose logs backend` y `systemctl status mariadb` | MySQL apagado (`enable --now`), `bind-address` en `127.0.0.1`, o falta la regla del firewall para `172.16.0.0/12` (paso 3) |
| `Access denied for user ...@'172.x.x.x'` | `docker compose logs backend` | Falta el usuario `'<usuario_bd>'@'172.%'` (paso 3) |
| `backend` queda `unhealthy` | `docker inspect --format '{{json .State.Health}}' ensenarte-backend-1` | No conecta a MySQL, o `127.0.0.1` no está en `ALLOWED_HOSTS` |
| 502 Bad Gateway en `/api/` | `docker compose logs frontend` | El backend no está corriendo o todavía arranca |
| 400 Bad Request en todo | `docker compose logs backend` | El dominio no está en `ALLOWED_HOSTS` |
| Error CSRF al entrar al admin | navegador | `CSRF_TRUSTED_ORIGINS` no es exactamente `https://<dominio>` |
| La subida de un archivo falla con 413 | `docker compose logs frontend` | Supera los 12 MB que acepta nginx (`client_max_body_size`) |
| Imágenes de los cursos rotas | `docker compose exec backend ls media/biblioteca` | El volumen se creó vacío: bórralo solo si no tiene subidas (`docker compose down -v`) y vuelve a levantar |
| La cámara no abre | navegador | La página no se abrió por `https://` (Funnel) |

---

## Licencia y autoría

Proyecto académico. Repositorio del cliente:
[`ensenarte-frontend`](https://github.com/<tu-usuario>/ensenarte-frontend).
