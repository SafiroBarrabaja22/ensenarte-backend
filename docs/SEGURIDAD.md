# Seguridad de enSEÑArte

Este documento explica, sin tecnicismos innecesarios, dos piezas de seguridad
del proyecto: **CORS**, que decide qué páginas web pueden usar nuestra API, y
los **tokens JWT**, que mantienen la sesión del usuario.

---

## 1. CORS en una frase

CORS es la lista de sitios web a los que el navegador les permite hablar con
nuestra API. Si una página no está en la lista, el navegador no la deja leer
las respuestas de la API.

## 2. Por qué lo necesitamos

enSEÑArte tiene dos partes que viven en lugares distintos:

| Parte | Dónde vive |
|---|---|
| Frontend (las páginas que ve el usuario) | `https://safirobarrabaja22.github.io` (GitHub Pages); en desarrollo, `http://localhost:5500` |
| Backend (la API con los datos) | Otro servidor; en desarrollo, `http://127.0.0.1:8000` |

Para el navegador, cada combinación de **esquema + dominio + puerto** es un
"origen" distinto. `http://localhost:5500` y `http://127.0.0.1:8000` son dos
orígenes diferentes, aunque estén en el mismo computador.

Por regla general, los navegadores no dejan que una página lea datos de otro
origen. Esa regla existe para que, por ejemplo, una página cualquiera que
abras no pueda leer tu correo o tu banco usando tu navegador. CORS es la forma
en que un servidor dice: "a estos orígenes concretos sí les permito leerme".

## 3. Cómo está configurado en este proyecto

- La lista se lee de la variable de entorno `CORS_ALLOWED_ORIGINS`, separada
  por comas. No está escrita en el código.
- Desarrollo: `http://localhost:5500,http://127.0.0.1:5500`
- Producción: `https://safirobarrabaja22.github.io`
- `CORS_ALLOW_ALL_ORIGINS = False` y no se usan expresiones regulares.
- `CORS_ALLOW_CREDENTIALS = False`. La API no usa cookies: el usuario se
  identifica con un token en la cabecera `Authorization`.
- **El backend se niega a arrancar** si la lista está vacía o trae `*`,
  `null`, un origen sin `http://` o `https://`, o un origen con ruta o barra
  final. Así un error de configuración no abre la API sin que nadie lo note.

> Ojo con GitHub Pages: la página se ve en
> `https://safirobarrabaja22.github.io/ensenarte-frontend/`, pero el **origen**
> es solo `https://safirobarrabaja22.github.io`. La ruta no forma parte del
> origen; si la incluyes, el backend no arranca y te dice por qué.

### Agregar un origen nuevo

1. Edita `CORS_ALLOWED_ORIGINS` en el `.env` del servidor (o en las variables
   de entorno del proveedor de hosting). Ejemplo:
   `CORS_ALLOWED_ORIGINS=https://safirobarrabaja22.github.io,http://localhost:5500`
2. Reinicia el backend.

## 4. Por qué el navegador bloquea la petición

Esto es lo que pasa cuando la página de cursos pide datos a la API:

1. El navegador agrega automáticamente a la petición la cabecera
   `Origin: https://safirobarrabaja22.github.io`. La página no puede falsificar
   ese dato: lo pone el navegador.
2. Como nuestras peticiones llevan `Authorization` y JSON, antes de la petición
   real el navegador hace una **consulta previa** (`OPTIONS`, llamada
   *preflight*): "¿Me dejas enviar un POST con estas cabeceras desde este
   origen?".
3. El backend revisa su lista:
   - **Si el origen está en la lista**, responde con
     `Access-Control-Allow-Origin: https://safirobarrabaja22.github.io` y el
     navegador sigue adelante.
   - **Si no está**, responde sin esa cabecera.
4. Si falta la cabecera, el navegador **no envía la petición real**, o si ya la
   envió, **no deja que el JavaScript lea la respuesta**. En la consola aparece
   un error como:
   `Access to fetch at '…' from origin '…' has been blocked by CORS policy`.

Quien bloquea es el **navegador**, no el servidor. El servidor solo informa a
quién autoriza, y el navegador hace cumplir esa decisión para proteger a su
usuario.

### Causas típicas del error en desarrollo

| Síntoma | Causa |
|---|---|
| Funciona en `localhost:5500` pero no en `127.0.0.1:5500` | Son orígenes distintos: deben estar los dos en la lista |
| Cambiaste el puerto de Live Server | El nuevo puerto no está en la lista |
| Abriste el HTML con doble clic (`file://`) | El origen es `null` y nunca se permite. Usa un servidor (`python -m http.server 5500`) |
| En producción falla todo | Falta `https://safirobarrabaja22.github.io` en el `.env` del servidor, o se escribió con la ruta o la barra final |

## 5. Qué pasaría si se abriera a todos los orígenes

Abrir CORS a todos (`CORS_ALLOW_ALL_ORIGINS = True` o `*`) significa decirle al
navegador: "cualquier página de internet puede usar esta API y leer sus
respuestas". Las consecuencias concretas para enSEÑArte:

1. **Clones falsos que parecen reales.** Alguien podría publicar
   `ensenarte-gratis.com`, una copia del sitio que usa **nuestra API de
   verdad**. Como mostraría los cursos reales y el login funcionaría, sería
   muy creíble, y mientras tanto podría guardar en silencio las contraseñas
   que escriben los estudiantes. Con CORS cerrado, ese clon no puede hablar con
   la API desde el navegador de la víctima; tendría que montar su propio
   servidor intermediario, que es más trabajo y más fácil de rastrear.
2. **Usar a los visitantes como atacantes.** Una página con mucho tráfico
   podría hacer que el navegador de cada visitante llame a nuestra API (por
   ejemplo, crear cuentas basura o saturar el servidor). Las peticiones
   llegarían desde miles de computadores reales, no desde uno solo, y serían
   difíciles de bloquear.
3. **Un problema que hoy es pequeño y mañana sería grave.** Hoy los tokens se
   guardan en el `localStorage` del frontend, y otra página no puede leerlos.
   Pero si algún día la sesión pasa a cookies (es un cambio habitual para
   protegerse de otros ataques), tener CORS abierto permitiría que cualquier
   sitio actuara **como el usuario conectado**: ver su progreso, cambiar su
   perfil, o, si es profesor, borrar cursos. Mantener la lista cerrada desde
   ahora evita que un cambio futuro abra ese hueco sin que nadie lo note.

### Lo que CORS **no** protege

CORS es una regla de los **navegadores**. Programas como `curl`, Postman, un
script de Python u otro servidor no la aplican y pueden llamar a la API
igual. La protección real de los datos está en otro lado:

- **La autenticación JWT:** sin un token válido solo se ve el catálogo
  público.
- **Los permisos por rol** (`apps/cursos/permissions.py`): un estudiante no
  puede editar cursos aunque llame a la API directamente.

CORS protege a **nuestros usuarios mientras navegan**. No reemplaza la
autenticación ni los permisos.

---

## 6. Sesiones con JWT

Al iniciar sesión, la API entrega dos tokens que el frontend guarda en el
navegador (`localStorage`):

| Token | Para qué sirve | Duración |
|---|---|---|
| **access** | Va en cada petición (`Authorization: Bearer …`) | 15 minutos (`JWT_ACCESO_MINUTOS`) |
| **refresh** | Solo sirve para pedir un access nuevo | 7 días (`JWT_REFRESCO_DIAS`) |

- **Por qué el access es corto:** es el que viaja todo el tiempo. Si alguien lo
  roba, le sirve como mucho 15 minutos.
- **Renovación sin que el usuario lo note:** cuando la API responde 401 porque
  el access venció, `js/api.js` pide uno nuevo con el refresh y repite la
  petición. Si varias peticiones vencen a la vez, comparten **un solo**
  refresco. Un corte de red no cierra la sesión.
- **Rotación:** cada renovación entrega también un refresh nuevo, y el anterior
  queda en una lista negra. Si alguien copia un refresh viejo, deja de servirle
  en cuanto el usuario real renueva. La sesión solo vence después de 7 días
  **sin usar** la aplicación.
- **Cerrar sesión** borra ambos tokens del navegador **y** avisa al servidor
  (`POST /api/auth/logout/`), que agrega el refresh a la lista negra. Borrarlo
  solo del navegador no basta, porque una copia seguiría sirviendo hasta 7 días.
- Si la sesión ya no se puede renovar, el usuario vuelve al login con el
  mensaje "Tu sesión expiró".

### Riesgo conocido

Guardar los tokens en `localStorage` es práctico, pero cualquier JavaScript que
corra en nuestro propio dominio puede leerlos. Por eso es importante no
insertar en las páginas texto de usuarios sin escaparlo (el panel usa la
función `esc` de `js/pages/panel/layout-panel.js`) y no cargar scripts de
sitios desconocidos.

### Mantenimiento

La lista negra guarda una fila por cada refresh emitido. De vez en cuando
conviene limpiar los que ya vencieron:

```bash
python manage.py flushexpiredtokens
```

---

## 7. Inyección SQL y validación de entradas

### Qué es

Una inyección SQL ocurre cuando el texto que escribe un usuario termina **pegado
dentro** de una consulta. Si el login armara la consulta así:

```python
# MAL: nunca se hace así en este proyecto
f"SELECT * FROM auth_user WHERE username = '{usuario}' AND password = '{clave}'"
```

escribir `' OR '1'='1` como usuario cambiaría la consulta y daría acceso sin
contraseña.

### Por qué aquí no es posible

1. **ORM de Django.** Casi todo el acceso a la base pasa por el ORM
   (`Curso.objects.filter(...)`, `serializer.save()`). El ORM envía el texto del
   usuario a MySQL como un **parámetro separado** de la consulta, así que MySQL
   lo trata siempre como un dato, nunca como código SQL. `'; DROP TABLE cursos_curso; --`
   se guarda tal cual como título.
2. **El SQL escrito a mano también va parametrizado.** Solo hay SQL escrito a
   mano en `apps/cursos/procedimientos.py`, para llamar a los procedimientos
   almacenados. Usa `cursor.execute("CALL nombre(%s, %s)", [valores])`: los
   valores van como parámetros. Lo único que se pega en el texto es el nombre
   del procedimiento, que está escrito en el código y nunca viene del usuario.
   No se usan `.raw()`, `.extra()` ni consultas armadas concatenando texto.
3. **Las contraseñas no se comparan en SQL.** Django guarda un hash (PBKDF2) y
   compara en Python. El login nunca busca "usuario y contraseña" en una consulta.
4. **El usuario de MySQL de la aplicación** solo tiene permisos sobre su base
   (`proyecto_v2`). Aunque hubiera un error, no podría tocar otras bases.

> **Limitar la longitud NO protege contra inyección SQL:** `' OR 1=1--` tiene
> 10 caracteres. La protección real son los parámetros (puntos 1 y 2).

### Límites de longitud (validación de entradas)

Aun así, todos los textos tienen un máximo, por dos motivos:

- Responder **400** con un mensaje claro en lugar de un error 500 de MySQL
  (*Data too long*).
- Evitar abusos: hashear una "contraseña" de varios megabytes consume mucha CPU.

El **backend es el que manda**: valida cada campo aunque alguien se salte el
formulario (desde *Inspeccionar* o llamando a la API directamente). El
**frontend** tiene los mismos valores en el atributo `maxlength` de cada campo,
para que el usuario no pueda escribir de más y no le llegue un error.

| Campo | Máximo | Dónde se define en el backend |
|---|---|---|
| Nombre de usuario (registro, login, perfil) | 150 | `config/limites.py` |
| Correo | 254 | `config/limites.py` |
| Contraseña (registro, login, cambio, recuperación) | 128 (mínimo 8) | `config/limites.py` |
| Token de recuperación | 100 | `config/limites.py` |
| Descripción del curso | 1000 | `config/limites.py` |
| Título del curso | 100 | `Curso.titulo` (models.py) |
| Slug del curso | 50 | `Curso.nombre` (SlugField) |
| Portada, icono e insignia del curso | 255 | models.py |
| Enunciado de pregunta | 200 | `Pregunta.texto` |
| Gif de la pregunta | 255 | `Pregunta.video` |
| Texto de una opción | 100 | `OpcionPregunta.texto` |
| Título de una palabra | 100 | `PalabraDiccionario.titulo` |
| Imagen y gif de una palabra | 200 | `PalabraDiccionario` |
| Nombre de un recurso de la biblioteca | 120 | `RecursoVisual.nombre` |
| Búsquedas | 100 | solo en el frontend; la búsqueda usa el ORM |

Si se cambia un límite, hay que cambiarlo en los dos lados: en el backend (en
`config/limites.py` o en el modelo, con su migración) y en el `maxlength` del
frontend.

### Cómo se comprueba

`tests/test_validacion_entradas.py` (41 pruebas; pasan en SQLite y en MySQL):

- Ocho ataques clásicos (`' OR '1'='1`, `admin'--`, `'; DROP TABLE ...`,
  `UNION SELECT ...`, etc.) en el login: siempre **401**, nunca un token.
- Los mismos textos en el registro, en cursos, preguntas y opciones se guardan
  **literalmente**. La tabla sigue existiendo y no se borra ni se crea nada de más.
- En la búsqueda de la biblioteca, `' OR 1=1 --` devuelve **0 resultados**, no
  todos.
- Cada campo que pasa de su límite responde **400** indicando el campo, nunca 500.

```bash
pytest tests/test_validacion_entradas.py --no-cov
```

---

## 8. Inicio de sesión, registro y recuperación de contraseña

Código en `apps/usuarios/seguridad.py` y `apps/usuarios/views.py`. Pruebas en
`tests/test_seguridad_acceso.py` (24 pruebas).

### Contra quien adivina contraseñas (fuerza bruta)

| Protección | Qué hace | Por qué |
|---|---|---|
| **Bloqueo por cuenta** | 5 contraseñas incorrectas seguidas para un usuario → login rechazado (429) durante 15 min desde el último fallo, **aunque luego acierte** | Un atacante que cambia de IP sigue frenado: el contador es de la cuenta |
| **Igual para usuarios que no existen** | El bloqueo también se aplica a nombres que no existen | Si solo se bloquearan cuentas reales, el 429 revelaría cuáles existen |
| **Límite por IP** | 30 logins por minuto por IP | Frena a quien prueba muchas cuentas desde una máquina. Es generoso: un salón entero puede compartir una IP |
| **IP real detrás del proxy** | `NUM_PROXIES=1` en producción: cuenta la IP que agrega Tailscale Funnel | Sin esto, un atacante podría inventar `X-Forwarded-For` para parecer otra IP en cada intento |
| **Mensaje de login genérico** | "No se encontró una cuenta activa para las credenciales dadas" | No dice si falló el usuario o la contraseña |

Una persona bloqueada puede esperar 15 minutos o usar "¿Olvidaste tu
contraseña?": restablecerla levanta el bloqueo de inmediato.

### Contra bots en el registro

- **Campo trampa (honeypot):** el formulario tiene un campo `sitio_web` que la
  persona no ve (fuera de la pantalla, oculto también para lectores de
  pantalla y sin foco con Tab). Los bots que rellenan todos los campos lo
  llenan, y el backend rechaza ese registro.
- **Límite por IP:** 30 registros por hora.
- **No se puede elegir rol:** el registro solo lee `nombre`, `correo` y
  `password`. Enviar `roles`, `is_staff` o `is_superuser` no tiene efecto:
  siempre se crea un Estudiante.
- La contraseña pasa por los validadores de Django (mínimo 8, no común, no solo
  números, distinta del usuario) y se guarda como hash PBKDF2.

> Un CAPTCHA (Cloudflare Turnstile o reCAPTCHA) detendría bots más avanzados,
> pero exige registrarse en un servicio externo y cargar su script. Para el
> tamaño del proyecto, campo trampa + límite por IP es suficiente.

### Recuperación de contraseña por correo

1. En "¿Olvidaste tu contraseña?" el usuario escribe su correo.
2. Si es de una cuenta activa, recibe el correo **"Restablece tu contraseña de
   enSEÑArte"** con un botón **"Sí, fui yo: restablecer contraseña"**. El correo
   explica que, si no fue él, lo ignore y su contraseña no cambia.
3. El botón abre `pages/recuperar.html#uid=...&token=...`, donde elige la
   contraseña nueva.
4. Al guardarla:
   - se cierran todas sus sesiones;
   - se levanta el bloqueo de login;
   - recibe otro correo: **"Tu contraseña cambió"**, con un enlace para
     recuperar la cuenta si no fue él.

Cómo se protege:

| Riesgo | Protección |
|---|---|
| Averiguar qué correos están registrados | Siempre la misma respuesta. El correo sale en segundo plano, así que la respuesta tampoco tarda más cuando la cuenta existe |
| Robar el enlace | Solo llega al buzón del dueño. Vence en **1 hora** y sirve **una sola vez** (el token depende del hash de la contraseña: al cambiarla deja de valer). Va después de `#`, así que nunca se envía a un servidor ni queda en registros, y la página lo borra de la barra de direcciones en cuanto lo lee |
| Inventar un token | Está firmado con la `SECRET_KEY`: sin ella no se puede fabricar uno válido |
| Llenar el buzón de alguien | Máximo 3 correos de recuperación por hora a la misma dirección, y 10 solicitudes por hora por IP |
| Que alguien siga dentro tras el cambio | Al restablecer o cambiar la contraseña, todos los refresh tokens pasan a la lista negra. Los access ya emitidos duran 15 minutos como máximo |
| Que el dueño no se entere | El aviso "Tu contraseña cambió" llega siempre, también al cambiarla desde el perfil |

Cuentas desactivadas o sin contraseña utilizable no reciben enlace.

### Dónde viven los contadores

Los contadores (límite por IP, bloqueo de cuenta, correos por dirección) se
guardan en la caché de Django, que en este proyecto es una **tabla de MySQL**
(`cache_ensenarte`, creada por la migración `usuarios/0004_tabla_cache`). Tiene
que ser compartida: gunicorn corre 3 procesos, y una caché en memoria le daría
a cada uno su propio contador, lo que triplicaría los límites.

### Configuración (`.env`)

| Variable | Por defecto | |
|---|---|---|
| `NUM_PROXIES` | `0` | **`1` en producción** (Tailscale Funnel) |
| `LOGIN_MAX_FALLOS` | `5` | Fallos seguidos antes de bloquear la cuenta |
| `LOGIN_BLOQUEO_MINUTOS` | `15` | Duración del bloqueo |
| `PASSWORD_RESET_TIMEOUT` | `3600` | Vigencia del enlace de recuperación, en segundos |
| `RECUPERAR_MAX_POR_CORREO` | `3` | Correos de recuperación por hora a una misma dirección |
| `LIMITE_ANONIMO` | `300/min` | Toda la API, por IP sin sesión |
| `LIMITE_USUARIO` | `600/min` | Toda la API, por usuario |
| `LIMITE_LOGIN` | `30/min` | Logins por IP |
| `LIMITE_REGISTRO` | `30/hour` | Registros por IP |
| `LIMITE_RECUPERAR_SOLICITAR` | `10/hour` | Solicitudes de recuperación por IP |
| `LIMITE_RECUPERAR_CONFIRMAR` | `20/hour` | Confirmaciones de recuperación por IP |

Para que el correo salga de verdad hay que configurar el SMTP (con Gmail, ver
`docs/DESPLIEGUE.md`). Sin SMTP la API funciona igual, pero el correo falla y
queda en el log.

Además del límite de login y registro, **toda la API** tiene un límite general:
300 peticiones por minuto por IP sin sesión y 600 por usuario. Es alto a
propósito (una persona usando la página nunca llega), pero frena scripts que
intenten descargar o saturar la API.

---

## 9. Subida de archivos

Código: `apps/cursos/archivos.py`. Pruebas: `tests/test_archivos.py` (38).

Todas las subidas (biblioteca, imágenes de contenido, gifs de palabras y
preguntas, foto de perfil) pasan por la misma validación:

| Comprobación | Por qué |
|---|---|
| Extensión permitida: PNG, GIF, JPG/JPEG/JFIF, WEBP, BMP (los gifs de señas: solo GIF) | **No se admite SVG ni HTML:** pueden llevar JavaScript |
| Tamaño máximo: 10 MB (foto de perfil: 5 MB) | Llenar el disco o la memoria |
| **El contenido se abre y verifica con Pillow** | Un `.html` o un `.exe` renombrado a `.png` se rechaza; un archivo que dice ser `.jpg` pero es PNG también. Pillow frena además las "bombas de descompresión" |
| **El nombre lo genera el servidor** (UUID) | El nombre original no llega al disco: nada de `../../config/settings.py`, espacios ni extensiones dobles |

Antes, los gifs de palabras y preguntas aceptaban **cualquier archivo con
cualquier nombre**. Como segunda barrera, `/media/` se sirve con
`Content-Security-Policy: sandbox` y `nosniff` (`config/media.py`): aunque un
archivo malicioso llegara al disco, el navegador no ejecutaría su código.

---

## 10. El frontend: escape de HTML y CSP

### Escapar los datos antes de pintarlos

Si una página mete en `innerHTML` un texto que escribió un usuario, ese texto
puede traer HTML con código (XSS) que se ejecutaría en el navegador de quien lo
vea y podría robar sus tokens. Se revisaron todas las páginas y se corrigieron
los sitios que pintaban datos de la API sin escapar:

- la **cabecera**: el nombre de usuario y el avatar (lo ven todos los que entran);
- el **diccionario**: título e imágenes de cada palabra;
- el **perfil**: la insignia de cada curso;
- **editar perfil**: los avatares.

Todos usan ahora `escaparHtml()` (`js/config.js`). También se escapan las rutas de
imagen dentro de `src="..."`: un valor con comillas podría romper el atributo.

### Content Security Policy (CSP)

GitHub Pages no deja enviar cabeceras, así que la política va en una etiqueta
`<meta>` en cada página. La genera `scripts/aplicar_csp.py` del frontend, que es la
única fuente. Lo principal:

| Directiva | Valor | Efecto |
|---|---|---|
| `script-src` | el propio sitio y `cdn.jsdelivr.net` (MediaPipe) | **No se ejecuta ningún script en línea ni inyectado.** Si un XSS lograra meter `<img onerror=...>`, el navegador lo bloquea |
| `connect-src` | el sitio, la API (`.ts.net` y local), jsdelivr, storage.googleapis.com | Aunque corriera código, no podría enviar los tokens a otro servidor |
| `img-src` / `media-src` | el sitio, la API, `data:` y `blob:` | |
| `form-action` | el sitio y formsubmit.co | Un formulario inyectado no puede enviar datos a otro sitio |
| `object-src 'none'`, `base-uri 'self'` | | Sin plugins; no se puede cambiar la base de los enlaces |

Para que la política funcionara, los tres scripts que había en línea (portada,
contacto, sobre nosotros) pasaron a archivos. El de contacto y sobre nosotros
tenía un error de sintaxis desde el commit "ola", por lo que esas páginas no
mostraban la cabecera; quedó corregido.

**Comprobado en Chrome**, recorriendo las 21 páginas con sesión de administrador:

- **Uso normal:** ni una violación de la CSP ni un error de JavaScript. MediaPipe
  carga y la cámara funciona con la política activa.
- **Ataque:** un `<img onerror>` inyectado a propósito quedó bloqueado.

Limitación: el atributo `frame-ancestors` (que impide meter la página en un
iframe) no funciona en `<meta>`; necesitaría un servidor que envíe cabeceras.

---

## 11. Dependencias

- `pip-audit` encontró vulnerabilidades conocidas en **Django 5.2.8** (55),
  **Pillow 10.4.0** (69), **DRF 3.15.2** (5) y **simplejwt 5.3.1** (2). Se subieron
  a Django 5.2.19, Pillow 13.0.0, DRF 3.18.3 y simplejwt 5.5.1. La suite completa
  pasa con esas versiones en Python 3.12.
- La CI corre `pip-audit` en cada push sobre todo lo instalado (incluidas las
  dependencias indirectas) y falla si aparece una vulnerabilidad.
- Dependabot (`.github/dependabot.yml`) propone las actualizaciones cada semana.
- El script de despliegue actualiza también `pip`, cuyas versiones viejas tienen
  vulnerabilidades.

---

## 12. Lista de verificación

| # | Punto | Estado | Dónde |
|---|---|---|---|
| 1 | Ocultar API keys | ✅ No hay claves en el frontend; los secretos solo están en el `.env` del servidor | §3, DESPLIEGUE.md |
| 2 | Secretos fuera de Git | ✅ Historia reescrita; `.gitignore` bloquea `.env`, volcados y bases | `.gitignore` |
| 3 | Key pública para la base | No aplica: el navegador nunca habla con MySQL, solo con la API | — |
| 4 | Row-Level Security | Equivalente en la API: permisos por rol y por objeto (el profesor solo ve sus cursos; cada quien, su progreso) | `apps/cursos/permissions.py` |
| 5 | Encriptar datos sensibles | ✅ Contraseñas con hash y todo el tráfico por HTTPS. No se guardan datos que pidan cifrado en reposo | §6, §8 |
| 6 | Forzar autenticación | ✅ Todo exige token por defecto y una prueba falla si una vista no declara permisos | `tests_roles.py` |
| 7 | Restringir acceso a registros | ✅ Roles más permiso por objeto, con pruebas de 403 por rol | `tests/test_permisos.py` |
| 8 | Bloquear manipulación de campos | ✅ `creado_por`, roles e `is_staff` no se pueden enviar. *Límite:* en la evaluación con cámara, el acierto lo decide el navegador | §8 |
| 9 | Cookies de sesión | La API no usa cookies (JWT). El admin de Django, en producción: Secure, HttpOnly y CSRF | settings.py |
| 10 | Hashear contraseñas | ✅ PBKDF2 (Django) | — |
| 11 | Rate limiting | ✅ Login, registro, recuperación y límite general de la API | §8 |
| 12 | Protección contra bots | ✅ Campo trampa más límites | §8 |
| 13 | Parametrizar queries | ✅ ORM y `%s` (41 pruebas) | §7 |
| 14 | Validar inputs | ✅ Longitudes y formatos en backend y frontend | §7, §9 |
| 15 | Sanitizar contenido | ✅ Escape en el frontend, autoescape en correos y PDF | §10 |
| 16 | Restringir archivos | ✅ Tipo verificado por contenido, tamaño y nombre del servidor | §9 |
| 17 | Devolver solo lo necesario | ✅ Serializers con campos explícitos; nunca hashes. Mensajes que no revelan qué cuentas existen | §8 |
| 18 | Security headers | ✅ API: HSTS, X-Frame-Options, nosniff, Referrer-Policy, CSP en `/media/`. Frontend: CSP por `<meta>` | §10 |
| 19 | Forzar HTTPS | ✅ Redirección y HSTS; Funnel y GitHub Pages solo sirven HTTPS | DESPLIEGUE.md |
| 20 | Escanear dependencias | ✅ `pip-audit` en la CI y Dependabot | §11 |
