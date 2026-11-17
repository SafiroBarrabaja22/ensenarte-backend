# Despliegue de enSEÑArte

Esta guía publica enSEÑArte en dos partes:

| Parte | Dónde | URL pública |
|---|---|---|
| Backend (Django + gunicorn) | MiniPC con Arch Linux (CachyOS), expuesta con **Tailscale Funnel** | `https://cachyos-x8664.tailb93c3e.ts.net` |
| Frontend (HTML/JS estático) | **GitHub Pages**, desde la raíz del repositorio | `https://safirobarrabaja22.github.io/ensenarte-frontend/` |
| Base de datos | MySQL/MariaDB **en la misma miniPC**, conexión por `localhost` | (no se expone) |

```
Navegador ──https──▶ GitHub Pages (frontend)
    │
    └──https (fetch + JWT)──▶ Tailscale Funnel :443 ──http──▶ gunicorn 127.0.0.1:8000 ──▶ MySQL localhost
                                cachyos-x8664.tailb93c3e.ts.net       (servicio systemd)
```

> **El dominio `.ts.net`** sale de `tailscale status`: el nodo `cachyos-x8664` de la
> tailnet `tailb93c3e`. Si se renombra la máquina o cambia de tailnet, hay que
> actualizarlo en cuatro sitios: `js/config.js` del frontend (`BACKEND_PRODUCCION`),
> `scripts/aplicar_csp.py` del frontend (y correrlo), y `ALLOWED_HOSTS` y
> `CSRF_TRUSTED_ORIGINS` del `.env`. Para confirmarlo, en la miniPC:
> `tailscale status --json | grep -m1 '"DNSName"'`.

Convenciones de esta guía:

- El proyecto vive en `/srv/ensenarte/ensenarte-backend` y lo ejecuta el usuario
  de sistema `ensenarte` (sin contraseña ni shell). Si usas otras rutas, ajústalas
  también en `despliegue/ensenarte-backend.service` y en las variables de
  `despliegue/desplegar.sh`.
- Lo que va entre `<ángulos>` lo tienes que poner tú. **Ningún archivo del
  repositorio lleva credenciales**: viven solo en el `.env` de la miniPC.

---

## Parte 1. Backend en la miniPC

### 1.1 Paquetes del sistema

```bash
sudo pacman -Syu --needed git base-devel pkgconf curl uv
```

- `base-devel` y `pkgconf` hacen falta para compilar `mysqlclient`.
- `mysqlclient` también necesita las cabeceras del cliente de MySQL. Si el
  servidor es **MariaDB** (lo habitual en Arch) ya vienen con `mariadb-libs`.
  Para comprobar cuál tienes: `mysql --version`. Si es MySQL de Oracle (AUR),
  las cabeceras vienen con ese paquete.
- `uv` crea el entorno con **Python 3.12** aunque Arch traiga uno más nuevo.
  Es la misma versión que la CI. Además, con un Python más nuevo, `Pillow 10.4.0`
  y `psycopg2-binary 2.9.9` (fijados en `requirements.txt`) no tienen paquetes
  precompilados y la instalación falla.

### 1.2 Usuario y carpeta

```bash
sudo useradd --system --create-home --home-dir /srv/ensenarte \
     --shell /usr/bin/nologin ensenarte
sudo -u ensenarte -H git clone https://github.com/SafiroBarrabaja22/ensenarte-backend.git \
     /srv/ensenarte/ensenarte-backend
```

### 1.3 Entorno de Python

```bash
cd /srv/ensenarte/ensenarte-backend
sudo -u ensenarte -H uv venv --python 3.12 --seed .venv
sudo -u ensenarte -H .venv/bin/python -m pip install -r requirements.txt
sudo -u ensenarte -H .venv/bin/python -c "import MySQLdb, django; print('ok', django.get_version())"
```

`uv` descarga Python 3.12 en `/srv/ensenarte/.local/share/uv/` si no está
instalado. `--seed` agrega `pip` al entorno; el script de despliegue lo usa.

### 1.4 Base de datos

El backend usa la base que ya existe en el MySQL de la miniPC (`proyecto_v2`)
y se conecta por **`localhost`**, no por la IP de Tailscale. Con `mysqlclient`,
`localhost` usa el socket de Unix (`/run/mysqld/mysqld.sock`), sin pasar por la red.

Comprueba que el usuario de la aplicación puede entrar por `localhost` y tiene
los permisos que piden las migraciones (tablas, procedimientos y triggers):

```bash
mysql -u <usuario_bd> -p -h localhost proyecto_v2 -e "SHOW GRANTS;"
```

Si hiciera falta darlos (como administrador de MySQL):

```sql
GRANT ALL PRIVILEGES ON proyecto_v2.* TO '<usuario_bd>'@'localhost';
FLUSH PRIVILEGES;
```

> **Atención:** `proyecto_v2` es también la base que usa el equipo para
> desarrollar. Desplegar ejecuta `migrate` sobre ella. El script respalda la base
> antes de cada migración (ver 1.8), pero lo recomendable es separar más adelante
> desarrollo y producción.

### 1.5 Archivo `.env` de producción

```bash
sudo -u ensenarte -H nano /srv/ensenarte/ensenarte-backend/.env
sudo chmod 600 /srv/ensenarte/ensenarte-backend/.env
```

Contenido (los valores entre `<>` los pones tú; la tabla completa está al final):

```ini
SECRET_KEY=<clave_larga_aleatoria>
DEBUG=False
ALLOWED_HOSTS=cachyos-x8664.tailb93c3e.ts.net,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://cachyos-x8664.tailb93c3e.ts.net
CORS_ALLOWED_ORIGINS=https://safirobarrabaja22.github.io
DATABASE_URL=mysql://<usuario_bd>:<clave_bd>@localhost:3306/proyecto_v2
URL_FRONTEND=https://safirobarrabaja22.github.io/ensenarte-frontend
# Funnel es 1 proxy delante de Django: el limite de intentos usa la IP real.
NUM_PROXIES=1

# Correo con Gmail (ver 1.5.1)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=<cuenta>@gmail.com
EMAIL_HOST_PASSWORD=<contraseña_de_aplicacion>
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=enSEÑArte <<cuenta>@gmail.com>
```

Para generar la `SECRET_KEY` (cópiala en el `.env`, no la guardes en otro sitio):

```bash
/srv/ensenarte/ensenarte-backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
```

- Si la clave de la base tiene caracteres especiales (`@ : / # ? %`), escríbelos
  codificados en la URL: `@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`, `%` → `%25`.
- `localhost` debe estar en `ALLOWED_HOSTS`: el script de despliegue comprueba el
  servicio en `127.0.0.1:8000`.
- `CORS_ALLOWED_ORIGINS` va **sin** `/ensenarte-frontend` y sin barra final. El
  backend no arranca si lleva ruta, `*` o `null`.

### 1.5.1 Correo con Gmail (recuperación de contraseña y avisos)

La recuperación de contraseña **solo funciona si el correo sale**: el enlace
llega únicamente por correo. Con una cuenta de Gmail del equipo:

1. Activa la **verificación en dos pasos** en esa cuenta de Google (Gmail no
   deja usar SMTP con la contraseña normal).
2. Entra a https://myaccount.google.com/apppasswords, crea una **contraseña de
   aplicación** (nombre: "enSEÑArte") y copia los 16 caracteres **sin espacios**
   en `EMAIL_HOST_PASSWORD`. No es la contraseña de la cuenta; si se filtra, se
   revoca desde esa misma página sin tocar la cuenta.
3. `DEFAULT_FROM_EMAIL` debe usar **la misma dirección** de `EMAIL_HOST_USER`:
   Gmail reemplaza cualquier otro remitente.
4. Prueba el envío (con el `.env` ya configurado):
   ```bash
   cd /srv/ensenarte/ensenarte-backend
   sudo -u ensenarte -H .venv/bin/python manage.py sendtestemail <tu_correo>
   ```
   Si no llega, revisa la carpeta de spam y `journalctl -u ensenarte-backend`.

Gmail permite unos 500 correos al día desde una cuenta personal, de sobra para
el proyecto.

**En desarrollo es igual:** pon las mismas variables `EMAIL_*` en el `.env` de tu
equipo. Si `EMAIL_HOST_USER` tiene valor, el correo sale por SMTP aunque
`DEBUG=True`. Sin esas variables los correos solo se imprimen en la consola de
`runserver` y no llegan a Gmail. `runserver` y `manage.py check` lo avisan con
`correos.W001`.

### 1.6 Primera puesta en marcha

```bash
cd /srv/ensenarte/ensenarte-backend
sudo -u ensenarte -H .venv/bin/python manage.py check --deploy
sudo -u ensenarte -H .venv/bin/python manage.py migrate
sudo -u ensenarte -H .venv/bin/python manage.py collectstatic --noinput
sudo -u ensenarte -H .venv/bin/python manage.py createsuperuser
```

`check --deploy` deja un único aviso esperado: `security.W021` (HSTS preload), que
no aplica a un dominio `.ts.net`. Cualquier **error** hay que corregirlo antes de seguir.

Las cuentas demo no se crean en producción: `poblar_datos` solo las crea con
`DEBUG=True` o con `--usuarios-demo`. Las contraseñas demo están publicadas en el
README, así que **no** uses esa opción aquí.

### 1.7 Servicio de systemd (gunicorn)

```bash
sudo cp /srv/ensenarte/ensenarte-backend/despliegue/ensenarte-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ensenarte-backend
systemctl status ensenarte-backend
```

Qué hace [`despliegue/ensenarte-backend.service`](../despliegue/ensenarte-backend.service):

- Arranca con el sistema (`enable`), después de la red y de MySQL/MariaDB.
- Se reinicia solo si el proceso muere (`Restart=always`, a los 5 s). Si falla 5
  veces en 2 minutos deja de insistir; revisa los logs y luego
  `sudo systemctl reset-failed ensenarte-backend && sudo systemctl start ensenarte-backend`.
- gunicorn escucha **solo en `127.0.0.1:8000`**. Desde fuera se llega únicamente
  por Funnel.
- Corre como `ensenarte`, sin poder escribir fuera de `media/`.

Prueba local (simulando la cabecera que pone Funnel):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/api/cursos/
# 200
```

### 1.8 Tailscale Funnel

Requisitos, en la consola de administración de la tailnet **dueña de la miniPC**
(`tailb93c3e`, https://login.tailscale.com/admin):

1. **DNS:** MagicDNS y *HTTPS Certificates* activados.
2. **Access controls:** permitir Funnel al nodo, por ejemplo:
   ```json
   "nodeAttrs": [{ "target": ["autogroup:member"], "attr": ["funnel"] }]
   ```
   (Con la política por defecto suele estar; si falta, `tailscale funnel` lo avisa
   y muestra un enlace para activarlo.)

En la miniPC:

```bash
sudo tailscale funnel --bg 8000
tailscale funnel status
# https://cachyos-x8664.tailb93c3e.ts.net (Funnel on)
# |-- / proxy http://127.0.0.1:8000
```

- `--bg` deja la configuración guardada: sobrevive a reinicios de la miniPC.
- Funnel atiende el HTTPS (con un certificado válido que gestiona Tailscale) y
  reenvía a gunicorn por http, agregando `X-Forwarded-Proto: https`. Django confía
  en esa cabecera (`SECURE_PROXY_SSL_HEADER`) porque gunicorn solo escucha en 127.0.0.1.
- Para apagarlo: `sudo tailscale funnel reset`.

### 1.9 Verificación desde fuera

Desde otra red (por ejemplo, el celular sin Wi-Fi, o un equipo fuera de la tailnet):

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://cachyos-x8664.tailb93c3e.ts.net/api/cursos/
# 200
curl -sI https://cachyos-x8664.tailb93c3e.ts.net/admin/login/ | head -1
# HTTP/2 200   (si sale 301 hacia la misma URL, Funnel no está enviando X-Forwarded-Proto)
```

Abre también `https://cachyos-x8664.tailb93c3e.ts.net/admin/`: debe verse **con
estilos**, porque WhiteNoise sirve `/static/`. Swagger está en `/api/docs/`.

### 1.10 Actualizar (cada nuevo despliegue)

```bash
sudo bash /srv/ensenarte/ensenarte-backend/despliegue/desplegar.sh
```

[`despliegue/desplegar.sh`](../despliegue/desplegar.sh) hace, en orden, y se
detiene en el primer error:

1. Comprueba que no haya cambios locales en archivos versionados, y luego
   `git fetch` y `git merge --ff-only origin/main`.
2. `pip install -r requirements.txt`.
3. `manage.py check --deploy`.
4. Si hay migraciones pendientes, **respalda la base**
   ([`despliegue/respaldar_bd.py`](../despliegue/respaldar_bd.py) →
   `/srv/ensenarte/respaldos/proyecto_v2-<fecha>.sql.gz`, guarda los 10 últimos e
   incluye procedimientos y triggers) y luego ejecuta `migrate`. Si el respaldo
   falla, no migra.
5. `collectstatic --clear`.
6. `systemctl restart ensenarte-backend`.
7. Espera hasta 20 s a que `/api/cursos/` responda; si no responde, muestra los
   últimos logs.

Variables opcionales: `RAMA=otra-rama`, `RESPALDAR=0`, `DIR_APP=...`, por ejemplo
`sudo RAMA=main bash despliegue/desplegar.sh`.

Restaurar un respaldo (con el servicio detenido):

```bash
sudo systemctl stop ensenarte-backend
gunzip -c /srv/ensenarte/respaldos/proyecto_v2-<fecha>.sql.gz | mysql -u <usuario_bd> -p proyecto_v2
sudo systemctl start ensenarte-backend
```

### 1.10.1 Dependencias con vulnerabilidades

- La CI corre `pip-audit` en cada push y falla si una dependencia (directa o
  indirecta) tiene una vulnerabilidad conocida.
- `.github/dependabot.yml` abre cada lunes un PR por cada versión nueva. Activa
  además *Settings → Code security → Dependabot alerts* y *Dependabot security
  updates* en GitHub.
- Si un PR de Dependabot pasa la CI, se hace merge y se despliega con
  `desplegar.sh`.

### 1.11 Operación diaria

| Para | Comando |
|---|---|
| Ver logs en vivo (peticiones y errores 500) | `journalctl -u ensenarte-backend -f` |
| Estado | `systemctl status ensenarte-backend` |
| Reiniciar | `sudo systemctl restart ensenarte-backend` |
| Recargar código sin cortar conexiones | `sudo systemctl reload ensenarte-backend` |
| Estado de Funnel | `tailscale funnel status` |

---

## Parte 2. Frontend en GitHub Pages

### 2.1 URL del backend

Está en [`js/config.js`](https://github.com/SafiroBarrabaja22/ensenarte-frontend/blob/main/js/config.js) del frontend:

```js
BACKEND_PRODUCCION: "https://cachyos-x8664.tailb93c3e.ts.net",
BACKEND_LOCAL: "http://127.0.0.1:8000",
```

`API_BASE_URL` se arma solo: si la página se abre en `localhost` o `127.0.0.1`
usa `BACKEND_LOCAL`; en cualquier otro dominio (GitHub Pages) usa
`BACKEND_PRODUCCION`. Así el mismo código sirve para desarrollar y para publicar
sin tocar nada. Si cambias `config.js`, sube el número de `config.js?v=` en los
HTML para que los navegadores no usen la versión en caché.

El dominio también está autorizado en la política de seguridad (CSP) de las
páginas. Si cambia, edita `BACKEND_PRODUCCION` en `scripts/aplicar_csp.py` y corre
`python scripts/aplicar_csp.py`; si no, el navegador bloqueará las llamadas a la API.

### 2.2 Activar GitHub Pages

1. Lleva los cambios a la rama `main` del repositorio `ensenarte-frontend`.
2. En GitHub: *Settings → Pages → Build and deployment → Source: Deploy from a
   branch → Branch: `main`, carpeta `/ (root)` → Save*.
3. A los 1–2 minutos queda en `https://safirobarrabaja22.github.io/ensenarte-frontend/`.

El repositorio incluye un `.nojekyll` vacío para que GitHub publique los archivos
tal cual, sin procesarlos con Jekyll.

### 2.3 Rutas bajo `/ensenarte-frontend/`

GitHub Pages sirve el sitio en un subdirectorio, así que una ruta que empiece por
`/` (por ejemplo `/css/style.css`) se saldría del sitio. Lo verificado:

- Ningún `href`, `src`, `url()` ni `import` empieza por `/`. Todas las rutas son
  relativas (`css/…`, `../js/…`, `../../assets/…`).
- Las rutas que arma el JavaScript usan `prefijoRaiz()` (`config.js`), que calcula
  los `../` según la carpeta de la página (`/`, `pages/`, `pages/panel/`), sin
  importar el subdirectorio.
- **Mayúsculas:** GitHub Pages las distingue y Windows no. Las 295 referencias de
  los HTML y CSS y las 45 rutas armadas en JS existen con las mayúsculas exactas,
  igual que todas las imágenes y gifs que nombra `contenido.json`.
- Las imágenes subidas (`/media/...`) se piden al backend: `config.js` las resuelve
  contra `BACKEND_PRODUCCION`.

Problema que ya existía (no lo causa el despliegue):
`assets/imagenes/imgPredeterminadaUsuario.png` (avatar por defecto) no está en el
repositorio, así que esa imagen sale rota tanto en local como en Pages.

### 2.4 Verificación

1. Abre `https://safirobarrabaja22.github.io/ensenarte-frontend/` y entra con una
   cuenta.
2. En las herramientas del navegador (F12 → Red), las peticiones deben ir a
   `https://cachyos-x8664.tailb93c3e.ts.net/api/...` con respuesta 200, sin errores de CORS.
3. Si aparece *"blocked by CORS policy"*, revisa que `CORS_ALLOWED_ORIGINS` sea
   exactamente `https://safirobarrabaja22.github.io` y reinicia el servicio.

---

## Variables de entorno del `.env` de producción

Django las lee de `/srv/ensenarte/ensenarte-backend/.env` (permisos 600, dueño
`ensenarte`). Nunca se suben al repositorio.

| Variable | Obligatoria | Valor en producción | Para qué |
|---|---|---|---|
| `SECRET_KEY` | **Sí** | `<clave_larga_aleatoria>` (ver 1.5) | Firma de JWT, sesiones y tokens de recuperación. Si se filtra, hay que cambiarla; eso cierra todas las sesiones. |
| `DEBUG` | **Sí** | `False` | Con `True` se muestran trazas con datos internos. Con `False` se activan HTTPS obligatorio, HSTS, cookies seguras, logs al journal y SMTP. |
| `ALLOWED_HOSTS` | **Sí** | `cachyos-x8664.tailb93c3e.ts.net,localhost,127.0.0.1` | Dominios que el backend acepta. `localhost` y `127.0.0.1` los usa la comprobación del script. |
| `CSRF_TRUSTED_ORIGINS` | **Sí** | `https://cachyos-x8664.tailb93c3e.ts.net` | Formularios con sesión: el login del admin de Django. Esquema y dominio, sin ruta. |
| `CORS_ALLOWED_ORIGINS` | **Sí** | `https://safirobarrabaja22.github.io` | Orígenes que pueden llamar a la API desde el navegador. Sin ruta, sin barra final y sin `*`. |
| `DATABASE_URL` | **Sí** | `mysql://<usuario_bd>:<clave_bd>@localhost:3306/proyecto_v2` | Conexión a MySQL por socket local. Caracteres especiales de la clave, codificados (ver 1.5). Si el socket no está en la ruta por defecto: agrega `?unix_socket=/ruta/mysqld.sock`. |
| `URL_FRONTEND` | **Sí** | `https://safirobarrabaja22.github.io/ensenarte-frontend` | Enlaces de los correos (bienvenida, resultados y **el enlace de recuperación de contraseña**). Con ruta y sin barra final. |
| `NUM_PROXIES` | **Sí** | `1` | Proxies delante de Django (Funnel). Con `1`, el límite de intentos de login usa la IP real del cliente; con `0` todos los usuarios parecerían venir de 127.0.0.1 y compartirían el límite. |
| `EMAIL_HOST` | **Sí** (recuperación) | `smtp.gmail.com` | Servidor SMTP. Sin él los correos fallan (queda en el log): la API sigue funcionando, pero **nadie puede recuperar su contraseña**. |
| `EMAIL_PORT` | No (587) | `587` | Puerto SMTP (465 si usas SSL). |
| `EMAIL_HOST_USER` | **Sí** (recuperación) | `<cuenta>@gmail.com` | Usuario SMTP. |
| `EMAIL_HOST_PASSWORD` | **Sí** (recuperación) | `<contraseña_de_aplicacion>` | Contraseña de aplicación de Gmail (ver 1.5.1), no la de la cuenta. |
| `EMAIL_USE_TLS` | No (`True`) | `True` | STARTTLS en el 587. |
| `EMAIL_USE_SSL` | No (`False`) | `False` | SSL directo en el 465. No puede estar en `True` junto con `EMAIL_USE_TLS`. |
| `EMAIL_TIMEOUT` | No (`10`) | `10` | Segundos máximos esperando al SMTP. |
| `DEFAULT_FROM_EMAIL` | No | `enSEÑArte <<cuenta>@gmail.com>` | Remitente. Con Gmail, la misma dirección de `EMAIL_HOST_USER`. |
| `EMAIL_BACKEND` | No | (sin definir) | Solo para forzar otro backend de correo. |
| `JWT_ACCESO_MINUTOS` | No (`15`) | `15` | Vida del token de acceso. |
| `JWT_REFRESCO_DIAS` | No (`7`) | `7` | Vida del token de refresco. |
| `EVALUACION_CAMARA_MAX_INTENTOS` | No (`50`) | `50` | Máximo de intentos por sesión de cámara. |
| `EVALUACION_CAMARA_UMBRAL_APROBACION` | No (`70`) | `70` | Porcentaje para aprobar la evaluación con cámara. |
| `SERVIR_MEDIA` | No (`True`) | `True` | Django sirve `/media/` (fotos de perfil, biblioteca, gifs) con cabeceras que impiden ejecutar código subido. Ponlo en `False` solo si otro servidor sirve esa carpeta. |
| `NIVEL_LOG` | No (`WARNING`) | `WARNING` | Nivel de los logs que van al journal (`INFO` para más detalle). |
| `LOGIN_MAX_FALLOS` | No (`5`) | `5` | Contraseñas incorrectas seguidas antes de bloquear la cuenta. |
| `LOGIN_BLOQUEO_MINUTOS` | No (`15`) | `15` | Duración del bloqueo de la cuenta. |
| `PASSWORD_RESET_TIMEOUT` | No (`3600`) | `3600` | Vigencia del enlace de recuperación, en segundos. |
| `RECUPERAR_MAX_POR_CORREO` | No (`10`) | `10` | Correos de recuperación por hora a la misma dirección. |
| `LIMITE_LOGIN` / `LIMITE_REGISTRO` / `LIMITE_RECUPERAR_SOLICITAR` / `LIMITE_RECUPERAR_CONFIRMAR` | No | `30/min`, `30/hour`, `10/hour`, `20/hour` | Peticiones por IP. Ver docs/SEGURIDAD.md, sección 8. |
| `LIMITE_ANONIMO` / `LIMITE_USUARIO` | No | `300/min`, `600/min` | Límite general de peticiones a toda la API, por IP (sin sesión) y por usuario. |
| `CORREOS_EN_SEGUNDO_PLANO` | No (`True`) | `True` | Envía el correo de recuperación sin hacer esperar la respuesta. No lo cambies: evita que se pueda saber qué correos existen midiendo el tiempo. |

**No** van en producción: `PRUEBAS_DATABASE_URL` y `BASES_PROTEGIDAS` (solo las
usan las pruebas).

---

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `systemctl status` muestra `ImproperlyConfigured` | Falta una variable obligatoria, o `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` llevan ruta o `*` | `journalctl -u ensenarte-backend -n 50`; corrige el `.env` y reinicia |
| `Can't connect to local server through socket` | MySQL detenido o socket en otra ruta | `systemctl status mariadb` (o `mysqld`); usa `?unix_socket=` en `DATABASE_URL` o `127.0.0.1` en vez de `localhost` |
| `Access denied for user ...@'localhost'` | El usuario de MySQL solo existe para la IP de Tailscale | Crea o da permisos a `'<usuario_bd>'@'localhost'` (ver 1.4) |
| La migración de triggers falla con *"You do not have the SUPER privilege and binary logging is enabled"* | Binlog activo en MySQL | Como administrador: `SET GLOBAL log_bin_trust_function_creators = 1;` (y en `my.cnf` para que dure) |
| Error 400 *Bad Request* en todo | El dominio no está en `ALLOWED_HOSTS` | Agrégalo y reinicia |
| Redirección infinita (301) | No llega `X-Forwarded-Proto` | Verifica que el tráfico entra por Funnel (`tailscale funnel status`), no directo al puerto 8000 |
| Admin sin estilos | No se corrió `collectstatic` | `sudo bash despliegue/desplegar.sh`, o `collectstatic` a mano y reiniciar |
| Error CSRF al entrar al admin | `CSRF_TRUSTED_ORIGINS` mal escrito | Debe ser `https://cachyos-x8664.tailb93c3e.ts.net` exacto |
| CORS en el navegador | Origen mal escrito, o el backend caído (una respuesta 502 no trae cabeceras CORS) | Revisa `CORS_ALLOWED_ORIGINS` y que el servicio esté activo |
| `pip install` falla compilando `mysqlclient` | Faltan `base-devel`, `pkgconf` o las cabeceras de MySQL/MariaDB | Paso 1.1 |
| El sitio deja de responder | La miniPC está apagada o sin internet | El backend depende de que la miniPC esté encendida |
