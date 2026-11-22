# syntax=docker/dockerfile:1
#
# Imagen del backend de enSEÑArte (Django + gunicorn).
# Guia de despliegue: README.md, seccion "Despliegue con Docker".
#
# Dos etapas: la primera compila mysqlclient (necesita compilador y las
# cabeceras de MySQL/MariaDB); la imagen final solo lleva lo necesario para
# ejecutar, sin compilador.

# ------------------------------------------------------------------ 1. Compilacion
FROM python:3.12-slim AS compilacion

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential + pkg-config + cabeceras del cliente MySQL/MariaDB: los pide
# mysqlclient (requirements.txt) para compilarse. Las demas dependencias
# traen ruedas precompiladas.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ------------------------------------------------------------------ 2. Ejecucion
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # gunicorn lee el numero de procesos de esta variable (se puede cambiar en el .env).
    WEB_CONCURRENCY=3

# libmariadb3: la libreria de cliente que usa mysqlclient en tiempo de ejecucion.
# Usuario sin privilegios: la aplicacion nunca corre como root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /app --shell /usr/sbin/nologin ensenarte

WORKDIR /app
COPY --from=compilacion /opt/venv /opt/venv
COPY --chown=ensenarte:ensenarte . .

# Estaticos del admin, DRF y Swagger (los sirve WhiteNoise). collectstatic no
# toca la base de datos; SECRET_KEY y DATABASE_URL solo existen en este paso
# para que settings.py cargue. Los valores reales llegan por el .env al correr.
# media/ trae la biblioteca y el contenido versionados: el volumen de Docker se
# llena con ellos la primera vez y despues conserva lo que suben los docentes.
RUN SECRET_KEY=solo-para-collectstatic DEBUG=False DATABASE_URL=sqlite:////tmp/collectstatic.sqlite3 \
        python manage.py collectstatic --noinput \
    && rm -f /tmp/collectstatic.sqlite3 \
    && mkdir -p media \
    && chown -R ensenarte:ensenarte media staticfiles

USER ensenarte
EXPOSE 8000

# El access log incluye X-Forwarded-For: asi se ve la IP real del visitante
# (la conexion directa siempre viene del nginx del frontend).
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--access-logformat", "%({x-forwarded-for}i)s \"%(r)s\" %(s)s %(b)s %(M)sms"]
