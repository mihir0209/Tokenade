#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.1.4}"
SESSIONS_DIR="${TOKENADE_VERIFY_SESSIONS_DIR:-/tmp/real-sessions}"
WORKDIR="${TOKENADE_VERIFY_WORKDIR:-$(mktemp -d /tmp/tokenade-pypi-verify.XXXXXX)}"
VENV="$WORKDIR/venv"
HOME_DIR="$WORKDIR/home"

cleanup() {
  if [[ "${TOKENADE_VERIFY_KEEP_WORKDIR:-0}" != "1" ]]; then
    rm -rf "$WORKDIR"
  else
    printf 'Keeping workdir: %s\n' "$WORKDIR"
  fi
}
trap cleanup EXIT

run() {
  printf '\n==> %s\n' "$*"
  "$@"
}

run_capture() {
  local output_file="$1"
  shift
  printf '\n==> %s\n' "$*"
  "$@" 2>&1 | tee "$output_file"
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    printf 'Missing required file: %s\n' "$path" >&2
    exit 1
  fi
}

printf 'Tokenade PyPI verification\n'
printf 'Version: %s\n' "$VERSION"
printf 'Workdir: %s\n' "$WORKDIR"

mkdir -p "$HOME_DIR"

run python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

run python -m pip install --upgrade pip
run python -m pip install --no-cache-dir "tokenade==$VERSION"

export HOME="$HOME_DIR"

run tokenade --version

actual_version="$(tokenade --version | awk '{print $2}')"
if [[ "$actual_version" != "$VERSION" ]]; then
  printf 'Expected tokenade %s, got %s\n' "$VERSION" "$actual_version" >&2
  exit 1
fi

run tokenade plugin registry list
run tokenade plugin search discord
run tokenade plugin search telegram

run tokenade plugin sync
run tokenade plugin list

for plugin in discord-handler telegram-handler generic-handler google-flow-handler; do
  run tokenade plugin test "$plugin"
done

run tokenade recommend --url https://discord.com
run tokenade recommend --url https://github.com
CLOAK_INFO="$WORKDIR/cloak-info.out"
run_capture "$CLOAK_INFO" tokenade cloak info

if [[ -d "$SESSIONS_DIR" ]]; then
  run tokenade validate -d "$SESSIONS_DIR"
  run tokenade sessions list -d "$SESSIONS_DIR"

  if [[ -f "$SESSIONS_DIR/discord-fixed.tokenade" ]]; then
    SESSION="$SESSIONS_DIR/discord-fixed.tokenade"
  elif [[ -f "$SESSIONS_DIR/discord.tokenade" ]]; then
    SESSION="$SESSIONS_DIR/discord.tokenade"
  else
    SESSION=""
  fi

  if [[ -n "$SESSION" ]]; then
    require_file "$SESSION"
    run tokenade health -s "$SESSION"

    ENC="$WORKDIR/session.tokenade.enc"
    DEC="$WORKDIR/session.tokenade"
    run tokenade encrypt -i "$SESSION" -o "$ENC" -p tokenade-verify-password
    run tokenade decrypt -i "$ENC" -o "$DEC" -p tokenade-verify-password
    run diff "$SESSION" "$DEC"
    if grep -q "Binary installed:  Yes" "$CLOAK_INFO"; then
      LOAD_OUT="$WORKDIR/load.out"
      run_capture "$LOAD_OUT" tokenade load --file "$SESSION" --stealth-level maximum
      if ! grep -q "Session loaded successfully" "$LOAD_OUT"; then
        printf 'tokenade load did not report success.\n' >&2
        exit 1
      fi
    else
      printf '\nCloakBrowser binary is not installed in isolated HOME; skipping tokenade load.\n'
      printf 'Run `tokenade cloak install` in that HOME to enable browser-backed load checks.\n'
    fi

    TEST_OUT="$WORKDIR/test.out"
    run_capture "$TEST_OUT" tokenade test -s "$SESSION"
    if grep -q "No handler found" "$TEST_OUT"; then
      printf 'tokenade test failed to resolve a handler.\n' >&2
      exit 1
    fi
    if ! grep -q "PORTABILITY TEST REPORT" "$TEST_OUT"; then
      printf 'tokenade test did not produce a portability report.\n' >&2
      exit 1
    fi
  else
    printf '\nNo Discord fixture found in %s; skipping health/encrypt/load/test fixture checks.\n' "$SESSIONS_DIR"
  fi
else
  printf '\nSessions directory not found: %s\n' "$SESSIONS_DIR"
  printf 'Skipping fixture-backed validate/sessions/health/encrypt/load/test checks.\n'
fi

printf '\nPyPI verification passed for tokenade==%s\n' "$VERSION"
