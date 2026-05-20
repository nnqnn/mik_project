#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CI_DIR="${ROOT_DIR}/.ci"
VENV_DIR="${CI_DIR}/venv"
COMPOSE_FILE="${ROOT_DIR}/services/docker-compose.yml"
export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"

compose_cmd() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi

  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi

  echo "Neither docker-compose nor docker compose is available." >&2
  exit 1
}

ensure_venv() {
  mkdir -p "${CI_DIR}"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
  fi
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  python -m pip install --upgrade pip
}

check() {
  ensure_venv
  cd "${ROOT_DIR}"

  python -m pip install -r "${ROOT_DIR}/requirements.txt"
  python manage.py test

  python -m pip install --upgrade -r "${ROOT_DIR}/services/auth_service/requirements.txt"
  PYTHONPATH="${ROOT_DIR}/services/auth_service" pytest "${ROOT_DIR}/services/auth_service/tests"

  python -m pip install -r "${ROOT_DIR}/services/payment_service/requirements.txt"
  PYTHONPATH="${ROOT_DIR}/services/payment_service" DATABASE_URL="postgresql+asyncpg://payment:payment@localhost/payment" pytest "${ROOT_DIR}/services/payment_service/tests"

  python -m pip install --upgrade -r "${ROOT_DIR}/services/ticketing_service/ticketing_fastapi/requirements.txt"
  PYTHONPATH="${ROOT_DIR}/services/ticketing_service/ticketing_fastapi" pytest "${ROOT_DIR}/services/ticketing_service/ticketing_fastapi/tests"

  compose_cmd -f "${COMPOSE_FILE}" config >/dev/null
}

build() {
  compose_cmd -f "${COMPOSE_FILE}" build
}

deploy() {
  compose_cmd -f "${COMPOSE_FILE}" up -d --build
}

down() {
  compose_cmd -f "${COMPOSE_FILE}" down
}

all() {
  check
  build
  deploy
}

command="${1:-check}"

case "${command}" in
  check|build|deploy|down|all)
    "${command}"
    ;;
  *)
    echo "Usage: $0 {check|build|deploy|down|all}" >&2
    exit 2
    ;;
esac
