#!/usr/bin/env bash
# Запуск одной командой: спрашивает ключ LLM (если нет .env), поднимает сервис,
# прогоняет messages.txt и печатает адрес интерфейса.
#
#   ./start.sh            Docker, а если его нет — локально через venv
#   ./start.sh --local    принудительно без Docker
#   ./start.sh stop       остановить контейнер
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }

ask() { # ask <переменная> <вопрос> <значение по умолчанию>
  local answer
  read -r -p "$2 [$3]: " answer
  printf -v "$1" '%s' "${answer:-$3}"
}

create_env() {
  local key="${LLM_API_KEY:-}" base_url="${LLM_BASE_URL:-https://api.openai.com/v1}" model="${LLM_MODEL:-gpt-5-mini}"
  if [ -t 0 ]; then
    say "Первый запуск: настроим доступ к LLM"
    echo "Подойдёт ключ любого OpenAI-совместимого API (OpenAI, LiteLLM, OpenRouter…)."
    echo "Ввод скрыт. Пустой ввод — запуск без ИИ, на запасных правилах."
    if [ -z "$key" ]; then
      read -r -s -p "LLM_API_KEY: " key
      echo
    fi
    if [ -n "$key" ]; then
      ask base_url "Адрес API (LLM_BASE_URL)" "$base_url"
      ask model "Модель (LLM_MODEL)" "$model"
    fi
  elif [ -z "$key" ]; then
    warn "Терминал не интерактивный, а LLM_API_KEY не задан — запускаю на правилах."
  fi

  # Значения идут через окружение awk, поэтому спецсимволы в ключе ничего не ломают.
  # umask 077: в .env лежит секрет, читать его может только владелец.
  ( umask 077
    KEY="$key" BASE="$base_url" MODEL="$model" awk '
      /^LLM_API_KEY=/  { print "LLM_API_KEY=" ENVIRON["KEY"]; next }
      /^LLM_BASE_URL=/ { print "LLM_BASE_URL=" ENVIRON["BASE"]; next }
      /^LLM_MODEL=/    { print "LLM_MODEL=" ENVIRON["MODEL"]; next }
      { print }' .env.example > .env )
  echo "Настройки записаны в .env (файл в .gitignore). Чтобы сменить ключ, отредактируйте его или удалите."
}

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

# Зависший демон (бывает у Docker Desktop) не должен вешать запуск: ждём ответа не дольше 15 с.
limited() { if command -v timeout >/dev/null; then timeout 15 "$@"; else "$@"; fi; }
have_docker() {
  command -v docker >/dev/null \
    && limited docker compose version >/dev/null 2>&1 \
    && limited docker info >/dev/null 2>&1
}

run_docker() {
  say "Собираю и запускаю контейнер…"
  if ! docker compose up -d --build --wait; then
    warn "Контейнер не поднялся. Логи: docker compose logs app"
    warn "Если занят порт ${PORT}, поменяйте PORT в .env и запустите снова."
    exit 1
  fi
  say "Разбор messages.txt"
  docker compose exec -T app python -m app.cli messages.txt
  say "Готово: http://localhost:${PORT}  (API: http://localhost:${PORT}/docs)"
  echo "Остановить: ./start.sh stop    Логи: docker compose logs -f app"
}

run_local() {
  command -v python3 >/dev/null || { warn "Нужен Docker или Python 3.10+."; exit 1; }
  if [ ! -x .venv/bin/python ]; then
    say "Создаю окружение .venv и ставлю зависимости…"
    python3 -m venv .venv 2>/dev/null || { command -v uv >/dev/null && uv venv .venv --seed; } || {
      warn "Не удалось создать venv. На Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
  fi
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
  say "Разбор messages.txt"
  .venv/bin/python -m app.cli messages.txt
  say "Интерфейс: http://localhost:${PORT}  (API: http://localhost:${PORT}/docs). Остановить: Ctrl+C"
  exec .venv/bin/python -m uvicorn app.main:app_from_env --factory --host 127.0.0.1 --port "${PORT}"
}

if [ "${1:-}" = "stop" ]; then
  docker compose down
  exit 0
fi

[ -f .env ] || create_env
PORT="$(env_value PORT)"; PORT="${PORT:-8000}"
export PORT

if [ "${1:-}" != "--local" ] && have_docker; then
  run_docker
else
  [ "${1:-}" = "--local" ] || warn "Docker не найден или не запущен — запускаю локально."
  run_local
fi
