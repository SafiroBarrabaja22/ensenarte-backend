# CLAUDE.md — ensenarte-backend

API REST de enSEÑArte (aprendizaje de Lengua de Señas Colombiana, LSC). No
renderiza HTML: el cliente vive en el repositorio hermano `../ensenarte-frontend`
y se comunica solo por HTTP/JSON. Contrato detallado en [docs/API.md](docs/API.md)
y modelo de datos en [docs/MODELO_DATOS.md](docs/MODELO_DATOS.md).

## Stack y versiones

Versiones fijadas en [requirements.txt](requirements.txt):

| Paquete | Versión |
|---|---|
| Django | 5.2.19 |
| djangorestframework | 3.18.3 |
| djangorestframework-simplejwt | 5.5.1 |
| drf-spectacular | 0.30.0 |
| django-cors-headers | 4.4.0 |
| django-environ | 0.11.2 |
| Pillow | 13.0.0 |
| mysqlclient | 2.3.0 |
| psycopg2-binary | 2.9.9 |
| gunicorn | 23.0.0 |
| whitenoise | 6.9.0 |

> **Ojo: el `.venv` local NO coincide con requirements.txt.** Hoy tiene
> instalados Python 3.14.0, Django 6.1.1, DRF 3.18.1, simplejwt 5.5.1,
> django-cors-headers 4.9.0, django-environ 0.14.0, Pillow 12.3.0,
> gunicorn 26.2.0. El README pide Python 3.11+. Antes de depender de una API
> de Django/DRF, revisa contra qué versión se está ejecutando; no actualices
> requirements.txt sin que el equipo lo decida.
>
> Django, DRF, simplejwt y Pillow se subieron el 17/11/2026 porque `pip-audit` encontró
> vulnerabilidades conocidas en las versiones anteriores. La suite pasa con estas
> versiones en Python 3.12 (igual que la CI). La CI corre `pip-audit` en cada push
> y `.github/dependabot.yml` propone actualizaciones cada semana.

- Base de datos: `DATABASE_URL` (django-environ). SQLite por defecto
  (`db.sqlite3`, ignorado en git); MySQL en producción (docs/DESPLIEGUE.md).
- Idioma/zona: `LANGUAGE_CODE = "es-co"`, `TIME_ZONE = "America/Bogota"`, `USE_TZ = True`.
- Paginación global: `PageNumberPagination`, `PAGE_SIZE = 50`
  (algunas vistas del panel la desactivan, ver abajo).
- Configuración sensible solo por `.env` (plantilla en [.env.example](.env.example)).
  Nunca leer, imprimir ni commitear `.env`.

## Comandos

```bash
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver             # http://127.0.0.1:8000
pip install -r requirements-dev.txt
pytest                                 # 206 pruebas + cobertura (umbral 70 %, reporte en htmlcov/)
python manage.py test apps             # solo las 65 de apps/ (unittest); tests/ es de pytest
# Ambos usan config/settings_pruebas.py: SQLite en memoria, hasher MD5 y
# MEDIA_ROOT temporal. Nunca tocan el MySQL compartido del .env.
python manage.py makemigrations <app>  # ver Convenciones
```

Comandos propios (`apps/cursos/management/commands/`):

| Comando | Qué hace |
|---|---|
| `poblar_datos` | Cursos de ejemplo + una cuenta demo por rol (los grupos los crea la migración) |
| `cargar_contenido` | Reemplaza cursos/preguntas/opciones/palabras/biblioteca con `apps/cursos/fixtures/contenido.json`. **Borra progreso e intentos**; conserva usuarios |
| `exportar_contenido` | Escribe el contenido actual en `apps/cursos/fixtures/contenido.json` |
| `otorgar_insignias_curso_100` | Marca retroactivamente `insignia_100_ganada` |

## Estructura

```
ensenarte-backend/
├── config/               settings.py (todo desde .env), urls.py (raíz), wsgi/asgi
├── apps/
│   ├── usuarios/         PerfilUsuario, registro/login JWT, perfil, recuperación de contraseña
│   │   ├── roles.py      Nombres de roles (única fuente) y helpers roles_de/tiene_rol
│   │   └── signals.py    post_save de User -> crea PerfilUsuario
│   ├── cursos/           Dominio principal: cursos, preguntas, diccionario, evaluación, biblioteca
│   │   ├── views.py        Catálogo, diccionario, progreso y motor de evaluación (function views)
│   │   ├── views_panel.py  Panel administrativo (ViewSets + function views)
│   │   ├── permissions.py  EsCreadorDeCursos, EsProfesor, EsInterprete
│   │   ├── fixtures/contenido.json   Contenido compartido del equipo
│   │   └── management/commands/
│   └── evaluacion_camara/ Sesiones de evaluación con cámara (sin urls.py propio; se monta en config/urls.py)
├── despliegue/          Servicio systemd, desplegar.sh y respaldar_bd.py (ver docs/DESPLIEGUE.md)
├── docs/                 API.md, MODELO_DATOS.md, SEGURIDAD.md, DESPLIEGUE.md, diagramas/
├── media/                Subidas. En git solo media/biblioteca/ y media/contenido/
└── ml/                   Datos/experimentos del modelo KNN (no versionado hoy)
```

## Modelos y relaciones

Todos usan `django.contrib.auth.models.User` (no hay User personalizado).

**usuarios**
- `PerfilUsuario` — `user` OneToOne→User (`related_name="perfil"`), `foto_perfil`
  (ImageField, `fotos_perfil/`), `avatar` (CharField: nombre de archivo o ruta
  de biblioteca), `estrellas`.

**cursos**
- `RecursoVisual` — imagen subida a `media/biblioteca/<uuid>.<ext>`;
  `categoria` ∈ {`recurso`, `avatar`, `insignia`, `curso_100`};
  `subido_por` FK→User (SET_NULL); `estado_validacion` ∈ {`pendiente`, `aprobada`,
  `rechazada`} (solo cuenta en las señas, `es_sena`).
- `RevisionSena` — FK→RecursoVisual (`revisiones`, CASCADE); `accion` ∈ {`aprobada`,
  `rechazada`, `reenviada`}, `comentario`, `usuario` FK→User (SET_NULL), `archivo`, `fecha`.
- `Curso` — `nombre` es **SlugField único y es el slug que usa el frontend en
  las URLs**; `titulo`, `portada_curso`, `icono_curso`, `insignia` (CharField con
  ruta/nombre de archivo), `insignia_100` FK→RecursoVisual (SET_NULL, limitado a
  `curso_100`), `preguntas_por_evaluacion` (null = todas), `creado_por` FK→User,
  `activo`.
- `Pregunta` — FK→Curso (`preguntas`), `texto`, `video` (nombre de gif o URL `/media/...`).
- `OpcionPregunta` — FK→Pregunta (`opciones`), `texto`, `es_correcta`.
  Solo una correcta por pregunta (lo fuerza `OpcionViewSet`, no la BD).
- `PalabraDiccionario` — FK→Curso (`diccionario`), `titulo`, `imagen_frontal`,
  `video_gif`, `orden` (ordering por `orden`, `titulo`).
- `ProgresoUsuario` — FK→User (`progresos`), FK→Curso; `unique_together
  (usuario, curso)`; resultado del último intento terminado + `insignia_100_ganada`.
- `IntentoEvaluacion` — FK→User (`intentos`), FK→Curso; estado de la evaluación
  en BD (antes vivía en `request.session`): `orden` (JSON de IDs de pregunta),
  `indice_actual`, `aciertos`, `errores`, `falladas` (JSON), `respuestas` (JSON), `finalizado`.

**evaluacion_camara**
- `EvaluacionCamara` — FK→User (`evaluaciones_camara`), FK→Curso opcional;
  `total`, `correctas`, `porcentaje`, `aprobado`, `umbral_aplicado`.
- `IntentoCamara` — FK→EvaluacionCamara (`intentos`); `orden`, `letra_objetivo`,
  `acerto`, `tiempo_ms`, `confianza` (0–1).

Todas las FK hacia Curso/User son `CASCADE` salvo las indicadas como SET_NULL.

### Reglas de negocio que viven en el código
- Un solo `IntentoEvaluacion` abierto por usuario+curso; `iniciar` borra el anterior.
- Si se borran preguntas de un intento abierto, el intento se descarta (`_intento_activo`).
- Se conservan solo los **5** intentos finalizados más recientes por usuario+curso
  y las **5** `EvaluacionCamara` más recientes por usuario.
- `PerfilUsuario.estrellas` = número de `ProgresoUsuario` con `completado=True`.
- Evaluación con cámara: el reconocimiento ocurre en el navegador; el servidor
  recibe los intentos (incluido `acerto`) y calcula porcentaje/aprobado con
  `EVALUACION_CAMARA_UMBRAL_APROBACION` (70) y `EVALUACION_CAMARA_MAX_INTENTOS` (50).
  El backend **no** restringe a qué curso se asocia la sesión (el frontend
  limita a `abecedario`).

## Endpoints

Rutas raíz en [config/urls.py](config/urls.py). Permiso por defecto de DRF:
`IsAuthenticated`.

**Auth** — `/api/auth/` ([apps/usuarios/urls.py](apps/usuarios/urls.py))

| Método | Ruta | Permiso |
|---|---|---|
| POST | `registro/` (`nombre`, `correo`, `password`) | AllowAny |
| POST | `login/` (`username`, `password`) → `access`, `refresh`, `usuario` | AllowAny |
| POST | `refresh/` (simplejwt) | AllowAny |
| POST | `verify/` (simplejwt) | AllowAny |
| GET, PATCH | `perfil/` | IsAuthenticated |
| POST | `cambiar-password/` | IsAuthenticated |
| POST | `recuperar/solicitar/` (el enlace solo va por correo; nunca en la respuesta) | AllowAny |
| POST | `recuperar/confirmar/` (`uid`, `token`, `password_nueva`) | AllowAny |

**Catálogo y evaluación** — `/api/` ([apps/cursos/urls.py](apps/cursos/urls.py))

| Método | Ruta | Permiso |
|---|---|---|
| GET | `cursos/` | AllowAny |
| GET | `cursos/<slug>/` | AllowAny |
| GET | `cursos/<slug>/diccionario/` | IsAuthenticated |
| GET | `progreso/` | IsAuthenticated |
| POST | `cursos/<slug>/evaluacion/iniciar/` | IsAuthenticated |
| GET | `cursos/<slug>/evaluacion/actual/` | IsAuthenticated |
| POST | `cursos/<slug>/evaluacion/responder/` (`opcion_id`) | IsAuthenticated |
| GET | `cursos/<slug>/evaluacion/resultado/` | IsAuthenticated |
| GET | `cursos/<slug>/evaluacion/historial/` (últimos 5) | IsAuthenticated |
| GET, POST | `evaluacion-camara/` (`?curso=<slug>`; últimas 5) | IsAuthenticated |

**Panel** — `/api/panel/` ([apps/cursos/views_panel.py](apps/cursos/views_panel.py))

| Método | Ruta | Permiso |
|---|---|---|
| CRUD | `cursos/` | Admin, Creador, Profesor (🔸 solo los suyos) |
| CRUD | `preguntas/` (`?curso=<id>`, sin paginar) | Admin, Creador, Profesor 🔸 |
| CRUD | `opciones/` (`?pregunta=<id>`) | Admin, Creador, Profesor 🔸 |
| CRUD | `diccionario/` (`?curso=<id>`, sin paginar) | Admin, Creador, Profesor 🔸 |
| POST | `diccionario/reordenar/` (`curso`, `ids`) | Admin, Creador, Profesor 🔸 |
| GET | `recursos/` (`?q=`, `?extension=`, `?categoria=`, `?estado=`, pagina solo con `?page=`) | IsAuthenticated (sin rol de contenido: solo ve `avatar`; Profesor y Creador: solo señas aprobadas) |
| POST/PUT/PATCH/DELETE | `recursos/` | Interprete o Admin (DELETE → 409 si el recurso está en uso) |
| POST | `recursos/<id>/validar/` (`decision`: `aprobar`/`rechazar`, `comentario`) | **Solo Validador** |
| GET | `recursos/<id>/revisiones/` | Validador, Interprete o Admin |
| GET | `resumen/` | Admin, Creador, Profesor |
| GET | `estudiantes/estrellas/` | Admin, Creador, Profesor |
| POST | `diccionario/<id>/gif/` (campo `gif`) | Admin, Creador, Interprete, Profesor 🔸 |
| POST | `preguntas/<id>/gif/` (campo `gif`) | Admin, Creador, Interprete, Profesor 🔸 |
| POST | `archivos/` (campo `archivo`, imagen ≤10 MB → `media/contenido/`) | Admin, Creador, Interprete, Profesor |

Las rutas de aprendizaje (`diccionario`, `progreso`, `evaluacion/*`,
`evaluacion-camara/`) exigen `PUEDE_APRENDER`, es decir, cualquier rol: un
usuario autenticado sin rol recibe 403.

Además: `/admin/` (admin de Django) y `/media/`, servido por `config/media.py` en desarrollo y en
producción (`SERVIR_MEDIA`, con `Content-Security-Policy: sandbox` para que un archivo subido no
ejecute código en el dominio del admin).

### Documentación OpenAPI (drf-spectacular 0.30.0)

- Rutas públicas: `/api/schema/` (YAML), `/api/docs/` (Swagger UI) y `/api/redoc/`.
  Configuración en `SPECTACULAR_SETTINGS` (`settings.py`). Swagger UI y ReDoc
  cargan versiones fijas del CDN, y `persistAuthorization` conserva el JWT.
- Piezas comunes en [config/openapi.py](config/openapi.py): `ok()`,
  `error_400/401/403/404()`, `respuestas()`, `PARAM_SLUG`, `filtro()` y
  ejemplos. Las etiquetas están en [config/etiquetas_api.py](config/etiquetas_api.py),
  sin dependencias porque las importa `settings.py`: Autenticación, Cursos,
  Evaluación, Panel y Reportes.
- **Todo endpoint nuevo lleva `@extend_schema`** (encima de `@api_view`) o
  `@extend_schema_view` en los viewsets (en el panel, `_doc_crud(...)` genera
  las 6 acciones). Debe tener una etiqueta de la lista, resumen, descripción
  con los roles y ejemplos. Los endpoints públicos llevan `auth=[]`.
- En listados paginados, el ejemplo va como lista simple: drf-spectacular lo
  envuelve en `{count, next, previous, results}`.
- [apps/usuarios/tests_documentacion.py](apps/usuarios/tests_documentacion.py)
  falla si un endpoint no tiene resumen, descripción o etiqueta, si uno
  protegido no pide el JWT, o si la generación produce avisos
  (`spectacular --validate --fail-on-warn`).

## Roles y cómo se verifican

Los roles son **grupos de Django**: `Estudiante`, `Profesor`, `Interprete`,
`Validador`, `CreadorDeCursos`, `Administrador`. La tabla completa de rol contra endpoint
está en [README.md](README.md) ("Roles y permisos").

- **Nombres:** solo en [apps/usuarios/roles.py](apps/usuarios/roles.py)
  (`ROL_*`, `TODOS_LOS_ROLES`). Nunca escribir el nombre de un grupo como string
  en otro archivo, ni en migraciones, pruebas o comandos.
- **Creación de grupos:** migración de datos
  [usuarios/0003_grupos_de_roles.py](apps/usuarios/migrations/0003_grupos_de_roles.py).
  También pasó los `is_staff` existentes a Administrador y las cuentas sin rol
  a Estudiante. `usuarios/0005_grupo_validador` agrega el grupo Validador a las bases
  existentes; **un rol nuevo necesita su propia migración igual**.
- **Helpers:** `roles_de(usuario)` (superusuario ⇒ incluye Administrador;
  `is_staff` solo NO da rol), `tiene_rol(usuario, *roles)`, `asignar_rol`.
- **Registro:** `RegistroSerializer.create` asigna `Estudiante`. Los demás
  roles se asignan desde `/admin/`.
- **Permisos DRF** en [apps/cursos/permissions.py](apps/cursos/permissions.py):
  una clase por rol (`EsEstudiante`, `EsProfesor`, `EsInterprete`, `EsValidador`,
  `EsCreadorDeCursos`, `EsAdministrador`) y combinaciones `PUEDE_APRENDER`,
  `PUEDE_GESTIONAR_CONTENIDO`, `PUEDE_GESTIONAR_BIBLIOTECA`, `PUEDE_SUBIR_GIF`,
  `PUEDE_VER_REVISIONES`.
- **Validación de señas** ([apps/cursos/validacion.py](apps/cursos/validacion.py), README
  "Validación de señas"):
  - Una seña es un gif de categoría `recurso` (`RecursoVisual.es_sena`). Su
    `estado_validacion` lo cambia **solo** `POST panel/recursos/<id>/validar/` (`EsValidador`;
    ni el Administrador ni un superusuario).
  - Al subirla o reemplazar su archivo queda `pendiente`; el historial va en `RevisionSena`.
  - Profesor y Creador no ven señas sin aprobar.
  - `PalabraPanelSerializer` y `PreguntaPanelSerializer` rechazan un gif nuevo que no sea una
    seña aprobada de la biblioteca.
  - `palabras_visibles()` oculta del diccionario del estudiante las palabras con seña sin aprobar.
  - Pruebas: [tests/test_validacion.py](tests/test_validacion.py).
- **Nivel de objeto:** `EsDuenoDelCurso` + `puede_editar_curso` /
  `exigir_curso_editable`. Administrador y CreadorDeCursos editan cualquier
  curso; Profesor solo los que tienen `creado_por = él`. En `list` el Profesor
  solo ve lo suyo; en detalle se responde 403, no 404. Los `perform_create` /
  `perform_update` validan también el curso **destino**, para que nadie pueda
  mover contenido a un curso ajeno.
- **Toda vista declara `permission_classes`.** La prueba
  `PermisosExplicitosTests` en [apps/cursos/tests_roles.py](apps/cursos/tests_roles.py)
  recorre las URLs y falla si alguna usa el permiso por defecto. Por eso el
  router es `SimpleRouter` y no `DefaultRouter`.
- **Al cliente:** `PerfilSerializer` devuelve `"roles": [...]` (ya no existen
  `es_creador`/`es_profesor`/`es_interprete`).
- **Cuentas demo:** `poblar_datos` crea `admin_demo`, `creador_demo`,
  `profesor_demo`, `profesor2_demo`, `interprete_demo`, `validador_demo` y `estudiante_demo` con la
  contraseña `Ensenarte2026!`. Solo lo hace con `DEBUG=True` o con `--usuarios-demo`.

## Autenticación del frontend contra esta API

Explicación en lenguaje llano: [docs/SEGURIDAD.md](docs/SEGURIDAD.md).

- JWT con SimpleJWT, header `Authorization: Bearer <access>`. Sin sesión ni
  cookies (`CORS_ALLOW_CREDENTIALS = False`); CSRF no aplica a la API.
- `access` 15 min (`JWT_ACCESO_MINUTOS`), `refresh` 7 días (`JWT_REFRESCO_DIAS`).
  `ROTATE_REFRESH_TOKENS` y `BLACKLIST_AFTER_ROTATION` están activos, con la app
  `rest_framework_simplejwt.token_blacklist`: `refresh/` devuelve access **y**
  refresh nuevos, y el refresh viejo queda inválido.
- `POST /api/auth/logout/` (`TokenBlacklistView`, AllowAny) recibe `{"refresh"}`
  y lo invalida.
- CORS: `CORS_ALLOWED_ORIGINS` sale de la variable de entorno (por defecto los
  dos orígenes de `:5500`; en Docker, el dominio `.ts.net`, el mismo de la API).
  `validar_origenes_cors` en `settings.py` detiene el arranque si hay `*`,
  `null`, ruta o barra final. `CORS_ALLOW_ALL_ORIGINS = False` y no hay regexes.
- Pruebas: [apps/usuarios/tests_seguridad.py](apps/usuarios/tests_seguridad.py).
- **Login, registro y recuperación** ([apps/usuarios/seguridad.py](apps/usuarios/seguridad.py),
  docs/SEGURIDAD.md §8):
  - límite por IP con `ScopedRateThrottle` (scopes `login`, `registro`, `recuperar_*`;
    `NUM_PROXIES=1` en producción);
  - bloqueo por cuenta tras `LOGIN_MAX_FALLOS` fallos, también para usuarios inexistentes;
  - campo trampa `sitio_web` en el registro;
  - recuperación por correo: enlace `recuperar.html#uid=&token=`, 1 hora, un solo uso,
    enviado en segundo plano;
  - restablecer o cambiar la contraseña cierra todas las sesiones y envía el aviso.

  Los contadores viven en la caché de base de datos (`cache_ensenarte`, migración
  `usuarios/0004`); las pruebas usan LocMem y `conftest.py` la limpia en cada prueba.
  Las tasas de DRF se leen al importar: en pruebas se cambian con
  `monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", ...)`.
- **Límite general:** `AnonRateThrottle` (300/min) y `UserRateThrottle` (600/min) para
  toda la API. `settings_pruebas.py` los sube para que no interfieran en las pruebas.
- **Subidas de archivos:** todas pasan por [apps/cursos/archivos.py](apps/cursos/archivos.py)
  (`validar_imagen` + `nombre_seguro`): solo PNG/GIF/JPG/WEBP/BMP (gifs: solo GIF), tamaño
  máximo, contenido verificado con Pillow y nombre UUID. Nunca guardes un archivo con el
  nombre que manda el usuario.
- El login devuelve también `usuario` (perfil + arreglo `roles`) para que el
  frontend decida a qué página redirigir. La autorización real es siempre la
  de este backend.

## Archivos e imágenes

- Campos como `portada_curso`, `imagen_frontal`, `video_gif`, `video`, `avatar`
  guardan un **string**: o un nombre relativo a `assets/` del frontend, o una
  ruta absoluta `/media/...` de este backend. El frontend resuelve ambos casos.
- Subidas: `media/biblioteca/` (RecursoVisual), `media/contenido/` (archivos
  puntuales), `media/diccionario_gifs/`, `media/evaluacion_gifs/`,
  `media/fotos_perfil/` (estas tres últimas no se versionan).

## Convenciones

- **Idioma:** código, comentarios, docstrings, mensajes de error y de commit en
  español.
- **Nombres en español**, siguiendo lo que ya existe: modelos (`Curso`,
  `PalabraDiccionario`, `IntentoEvaluacion`), campos (`fecha_creacion`,
  `es_correcta`, `creado_por`), funciones y variables (`iniciar_evaluacion`,
  `_cerrar_intento`, `puede_ver_todo`), `related_name` (`preguntas`,
  `opciones`, `progresos`). Las únicas palabras en inglés son las impuestas por
  Django/DRF (`user`, `get_queryset`, `perform_create`, etc.).
- Hoy los `.py` escriben sin tildes ni ñ en identificadores y en la mayoría de
  comentarios (`senas`, `Contrasena`); la ñ nunca va en nombres de módulos ni
  identificadores.
- **Migraciones siempre versionadas.** Todo cambio de modelo va acompañado de su
  migración generada con `makemigrations` y commiteada en el mismo commit. No
  editar migraciones ya aplicadas/publicadas; no borrar ni regenerar las
  existentes. (El README aún dice que no están versionadas: es un texto
  desactualizado, las 14 migraciones actuales sí están en git.)
- Cambios de contenido (cursos, preguntas, diccionario) se comparten con
  `exportar_contenido` + commit de `contenido.json` y `media/biblioteca|contenido`,
  no con migraciones de datos ni con `db.sqlite3`.
- No commitear `.env`, `db.sqlite3`, `db.sqlite3.backup-*`, ni `media/` fuera de
  `biblioteca/` y `contenido/`.

## Despliegue

**Docker** (README, "Despliegue con Docker"): `Dockerfile` (python:3.12-slim en dos etapas,
gunicorn, `collectstatic` en el build, usuario sin root), `despliegue/docker-compose.yml`
(se copia a la carpeta que contiene los dos repos) y `despliegue/docker.env.example`.
- **Una sola entrada:** el nginx del frontend (`127.0.0.1:8080`, Tailscale Funnel) reenvía
  `/api/ /admin/ /media/ /static/` al backend (`127.0.0.1:8000`); todo en el mismo dominio.
- **MySQL** de la miniPC por `DB_HOST=host.docker.internal`.
- **Configuración:** `DB_*` tiene prioridad sobre `DATABASE_URL` (`settings_pruebas.py` vacía
  `DB_NAME` para que las pruebas nunca la usen). `NUM_PROXIES=2` (Funnel + nginx).
- **Archivos subidos:** `media` es un volumen.

El despliegue con systemd (`despliegue/desplegar.sh`, `docs/DESPLIEGUE.md`) está obsoleto. WhiteNoise sirve `/static/` (`CompressedManifestStaticFilesStorage`:
exige `collectstatic`; `settings_pruebas.py` usa el almacenamiento normal). Con `DEBUG=False` los logs
van a la salida estándar (journal). Actualizar: `sudo bash despliegue/desplegar.sh`.
Pruebas de esta configuración: [tests/test_despliegue.py](tests/test_despliegue.py).

## Integración continua

La CI instala `requirements-ci.txt` (generado con `uv pip compile` desde `requirements-ci.in`):
todas las dependencias con hash, solo ruedas precompiladas y sin `mysqlclient`.
`scripts/verificar_requirements_ci.py` falla si no coincide con `requirements.txt` /
`requirements-dev.txt`: **al cambiar una versión, regenera `requirements-ci.txt`** (comando en
la cabecera de `requirements-ci.in`) **y `requirements-docker.txt`** (cabecera de
`requirements-docker.in`). El script también revisa esos dos.

**Dockerfiles (reglas de SonarQube):**
- **Backend:** instala `requirements-compilacion.txt` (setuptools) y después
  `requirements-docker.txt`, con `--require-hashes --only-binary :all:`. Solo `mysqlclient` se
  compila (`--no-binary mysqlclient --no-build-isolation`), porque no tiene versión
  precompilada para Linux.
- **Backend:** copia carpeta por carpeta (`manage.py`, `config/`, `apps/`,
  `media/biblioteca|contenido`), nunca `COPY . .`.
- **Frontend:** usa `nginxinc/nginx-unprivileged` (sin root, escucha en el 8080 del contenedor).

SonarQube Cloud analiza `main`. Reglas que ya nos marcó y conviene no repetir:
- Sin contraseñas escritas en el código, ni en pruebas: usa `secrets.token_urlsafe()`.
- Nada de SQL armado con f-strings: ORM, `%s` o `cursor.callproc` (lista `PROCEDIMIENTOS`).
- Las vistas Django sin DRF declaran métodos (`@require_safe`, `@require_POST`).
- Los scripts no reciben rutas por argumento para escribir archivos.

[.github/workflows/ci.yml](.github/workflows/ci.yml) corre en cada push y PR (todas las ramas):
Python 3.12, `check`, `makemigrations --check`, `pytest` (umbral 70 %) y sube `htmlcov/` como
artifact (`actions/*@v7`, Node 24). Sin servidor de base de datos: SQLite en memoria, igual que
en local, así que las 40 pruebas que necesitan MySQL (triggers, procedimientos y el reporte de
plataforma) se saltan; córrelas a mano con `PRUEBAS_DATABASE_URL` (README). Único secret:
`CI_SECRET_KEY`; nunca escribir valores en el YAML. Si cambias un modelo, genera y commitea
la migración o la CI falla.

## Reglas en la base de datos (MySQL)

Migraciones de `cursos`: `0010_auditoria_curso` (modelo `AuditoriaCurso`, normal),
`0011_procedimientos_mysql` (solo procedimientos), `0012_triggers_mysql` (solo triggers) y
`0014_triggers_validacion` (triggers de la validación de señas).
Usan `RunSQLSoloMySQL` ([apps/cursos/operaciones_mysql.py](apps/cursos/operaciones_mysql.py)):
en SQLite (pruebas en local y en la CI) y PostgreSQL no ejecutan nada.

- **Al escribir SQL de MySQL en migraciones:** una sentencia por elemento de la lista `sql`
  (sin `DELIMITER`), sin `DEFINER`, `SIGNAL SQLSTATE '45000'`, `JSON` y `UTC_TIMESTAMP(6)`.
  Cada `CREATE` va precedido de `DROP ... IF EXISTS` y lleva un comentario con la regla.
  Ningún procedimiento abre una transacción.
- **Procedimientos** (se llaman desde [apps/cursos/procedimientos.py](apps/cursos/procedimientos.py)):
  `cerrar_intento_evaluacion`, `estadisticas_curso`, `ranking_estudiantes`, `clonar_curso`
  (comparte los recursos de la biblioteca y deja el clon inactivo),
  `purgar_intentos_abandonados` y `marcar_opcion_correcta`.
- **Triggers:** una sola opción correcta, máximo `MAXIMO_OPCIONES_POR_PREGUNTA` opciones,
  auditoría de cursos (alta, cambio y baja en JSON), estrellas al completar un progreso
  e intento finalizado inmutable.
- **Triggers de la validación de señas** (`0014_triggers_validacion`):
  - `recurso_estado_con_historial`: el estado cambia solo si coincide con la última
    `RevisionSena`. Por eso `validacion.decidir()` y `volver_a_revision()` crean **primero**
    la revisión y después guardan el estado: no inviertas ese orden.
  - `revision_sena_reglas`: solo un usuario del grupo Validador aprueba o rechaza, y rechazar
    exige comentario.
  - `revision_sena_inmutable`: el historial no se edita. Se permite borrarlo y poner el
    usuario en NULL.
- **Opción correcta:** MySQL no deja que un trigger modifique su propia tabla (error 1442).
  El trigger RECHAZA la segunda correcta y, para cambiar la correcta, se usa siempre
  `marcar_opcion_correcta()`, como hace el panel. No marques una opción con `save()`.
  Excepción: el inline del admin (`OpcionInlineFormSet` en `apps/cursos/admin.py`) valida
  antes (máx. 1 correcta y 4 opciones) y `PreguntaAdmin.save_formset` guarda borrados,
  luego no correctas y al final la correcta, para que el trigger no salte en cambios válidos.
- **Auditoría:** para que registre el usuario de la aplicación, envuelve los cambios
  de cursos en `with usuario_auditoria(request.user):`.
- **Pruebas:** [tests/test_reglas_mysql.py](tests/test_reglas_mysql.py) solo corren contra MySQL:
  `PRUEBAS_DATABASE_URL=mysql://.../proyecto_pruebas pytest` (Django crea y borra
  `test_proyecto_pruebas`). **Nunca apuntar nada a `proyecto_v2`** (base compartida del equipo).

## Correos (apps/correos)

- [apps/correos/servicio.py](apps/correos/servicio.py): `enviar_bienvenida`, `enviar_resultados`
  `avisar_curso_completado`, `enviar_recuperacion` y `avisar_recuperacion_sin_cuenta` (con `en_segundo_plano`)
  y `avisar_password_cambiado`. Todas llevan `@sin_romper`, que registra cualquier error en el
  log y devuelve False. Se disparan con `al_confirmar(funcion, ...)`, es decir,
  `transaction.on_commit(robust=True)`, desde `RegistroView`, `_finalizar`/`_cerrar_intento`
  (cursos/views.py) y el serializer de cámara.
- **Plantillas** en `apps/correos/templates/correos/`: `base.html` más un `.html` y un `.txt`
  por correo. **Reglas:** maquetación con tablas, estilos SOLO en línea (nada de `<style>`,
  flexbox, grid ni `var(--...)`), ancho máximo de 600px. Los colores vienen del dict `COLORES`
  (los mismos valores de tokens.css) y el logo se referencia como `src="cid:logo-ensenarte"`.
- `CorreoConLogo` incrusta el logo. En Django 5.2 usa `mixed_subtype="related"` con un
  `MIMEImage`; en Django 6 eso lanza `AttributeError`, así que usa `add_related()` sobre la
  parte HTML. [tests/test_correos.py](tests/test_correos.py) comprueba las reglas en cada correo.
- `DEBUG=True` usa el backend de consola; `DEBUG=False`, SMTP con las variables `EMAIL_*`
  (Django 6.1 avisa que `EMAIL_*` pasará a `MAILERS` en Django 7).

## Reportes (apps/reportes)

- **Historial de intentos** ([apps/reportes/historial.py](apps/reportes/historial.py)): PDF propio
  (no usa `datos.py`) que replica la tarjeta "Tu progreso" del frontend con dibujos de ReportLab
  (anillo, gráfica y tarjetas). Si cambias el diseño de `js/lib/historial-intentos.js` o sus
  estilos en `css/extra.css`, actualiza también este PDF. Los puntajes usan `_redondear()`
  (como `Math.round` de JS). Botón "Exportar PDF" en `historial-intentos.js` (opción `exportar`).

- `datos.py` arma un `Reporte` neutro (`modelo.py`: `Tabla` con `formatos` por columna) y
  `pdf.py`/`excel.py` lo dibujan. Para un reporte nuevo: una función en `datos.py` y un
  endpoint en `views.py`; no se toca el dibujo.
- PDF: `CanvasNumerado` dibuja el encabezado (logo y título) y el pie "Página X de Y" en una
  segunda pasada. Todo texto dinámico pasa por `_p()`, que lo escapa (ReportLab interpreta
  etiquetas). La constancia usa `KeepInFrame(mode="shrink")` para caber en una página.
- Excel: cada `Tabla` en su propia hoja; los valores van con su tipo nativo y `number_format`.
- Marca compartida con los correos en [config/marca.py](config/marca.py): `COLORES`, fuentes
  y `RUTA_LOGO` (`config/recursos/logo.png`).
- El reporte de plataforma usa SOLO los procedimientos almacenados; fuera de MySQL responde 503.
- Pruebas: [tests/test_reportes.py](tests/test_reportes.py) (texto del PDF descomprimiendo
  ASCII85+Flate y Excel con openpyxl).
- `config/settings_pruebas.py` se niega a correr si la base es `proyecto_v2`
  (`BASES_PROTEGIDAS`).
