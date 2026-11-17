#!/usr/bin/env bash
# Despliega la ultima version del backend en la miniPC (Arch Linux).
# Guia completa: docs/DESPLIEGUE.md
#
# Uso:   sudo bash /srv/ensenarte/ensenarte-backend/despliegue/desplegar.sh
#
# Pasos: git pull -> pip install -> check --deploy -> respaldo de la base (solo
# si hay migraciones pendientes) -> migrate -> collectstatic -> reiniciar el
# servicio -> comprobar que responde.
#
# Variables opcionales (con su valor por defecto):
#   DIR_APP=/srv/ensenarte/ensenarte-backend   USUARIO_APP=ensenarte
#   SERVICIO=ensenarte-backend   RAMA=main   PUERTO=8000
#   DIR_RESPALDOS=/srv/ensenarte/respaldos   RESPALDAR=1 (0 = sin respaldo)
#
# Todo va dentro de main(): bash lee el archivo completo antes de ejecutarlo,
# asi que el `git pull` puede cambiar este mismo script sin romper la ejecucion.

set -Eeuo pipefail

main() {
    local DIR_APP="${DIR_APP:-/srv/ensenarte/ensenarte-backend}"
    local USUARIO_APP="${USUARIO_APP:-ensenarte}"
    local SERVICIO="${SERVICIO:-ensenarte-backend}"
    local RAMA="${RAMA:-main}"
    local PUERTO="${PUERTO:-8000}"
    local DIR_RESPALDOS="${DIR_RESPALDOS:-/srv/ensenarte/respaldos}"
    local RESPALDAR="${RESPALDAR:-1}"

    paso() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
    falla() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
    # Todo lo de la aplicacion corre como su usuario, nunca como root.
    como_app() { runuser -u "$USUARIO_APP" -- "$@"; }
    manage() { como_app "$DIR_APP/.venv/bin/python" "$DIR_APP/manage.py" "$@"; }

    [[ $EUID -eq 0 ]] || falla "Ejecuta el script con sudo."
    id "$USUARIO_APP" >/dev/null 2>&1 || falla "No existe el usuario $USUARIO_APP."
    [[ -d "$DIR_APP/.git" ]] || falla "$DIR_APP no es un repositorio git."
    [[ -f "$DIR_APP/.env" ]] || falla "Falta $DIR_APP/.env (ver docs/DESPLIEGUE.md)."
    [[ -x "$DIR_APP/.venv/bin/python" ]] || falla "Falta el entorno $DIR_APP/.venv (ver docs/DESPLIEGUE.md)."
    cd "$DIR_APP"

    paso "1/7 Actualizando el codigo (rama $RAMA)"
    # Cambios locales en archivos versionados se perderian o romperian el pull.
    # (Los archivos nuevos sin versionar, como las subidas en media/, no cuentan.)
    if [[ -n "$(como_app git status --porcelain --untracked-files=no)" ]]; then
        como_app git status --short --untracked-files=no
        falla "Hay cambios locales en archivos versionados. Revisalos antes de desplegar."
    fi
    local antes
    antes="$(como_app git rev-parse --short HEAD)"
    como_app git fetch --prune origin
    como_app git checkout --quiet "$RAMA"
    como_app git merge --ff-only "origin/$RAMA"
    echo "Version: $antes -> $(como_app git rev-parse --short HEAD)"

    paso "2/7 Instalando dependencias"
    # pip primero: las versiones viejas de pip tienen vulnerabilidades conocidas.
    como_app "$DIR_APP/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
    como_app "$DIR_APP/.venv/bin/python" -m pip install --quiet --disable-pip-version-check \
        -r requirements.txt

    paso "3/7 Revisando la configuracion de produccion"
    # Falla solo con errores; los avisos (p. ej. HSTS preload) se muestran y sigue.
    manage check --deploy

    paso "4/7 Migraciones"
    if manage migrate --check >/dev/null 2>&1; then
        echo "No hay migraciones pendientes."
    else
        manage showmigrations --plan | grep '\[ \]' || true
        if [[ "$RESPALDAR" == "1" ]]; then
            install -d -m 700 -o "$USUARIO_APP" -g "$USUARIO_APP" "$DIR_RESPALDOS"
            como_app "$DIR_APP/.venv/bin/python" despliegue/respaldar_bd.py "$DIR_RESPALDOS" \
                || falla "No se pudo respaldar la base; no se migra. (RESPALDAR=0 para omitirlo)"
        fi
        manage migrate --noinput
    fi

    paso "5/7 Archivos estaticos"
    manage collectstatic --noinput --clear | tail -n 1

    paso "6/7 Reiniciando $SERVICIO"
    systemctl restart "$SERVICIO"

    paso "7/7 Comprobando que responde"
    # Se simula la cabecera que agrega Tailscale Funnel; sin ella Django
    # redirige a https (301).
    local intento
    for intento in $(seq 1 20); do
        if curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" \
                "http://127.0.0.1:$PUERTO/api/cursos/"; then
            printf '\n\033[1;32mDespliegue terminado: %s responde.\033[0m\n' "$SERVICIO"
            return 0
        fi
        sleep 1
    done
    journalctl -u "$SERVICIO" -n 40 --no-pager >&2 || true
    falla "$SERVICIO no responde en 127.0.0.1:$PUERTO despues de 20 s."
}

main "$@"
exit
