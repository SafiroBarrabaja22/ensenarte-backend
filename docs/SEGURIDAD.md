# Seguridad: CORS y sesiones (JWT)

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
