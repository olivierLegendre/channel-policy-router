#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: '$PYTHON_BIN' is not available in PATH." >&2
  exit 1
fi

TARGET_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  CURRENT_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' || true)"
  if [[ "$CURRENT_VERSION" != "$TARGET_VERSION" ]]; then
    echo "Existing venv uses Python $CURRENT_VERSION, expected $TARGET_VERSION. Recreating..."
    rm -rf "$VENV_DIR"
  fi
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip

if [[ -f "pyproject.toml" ]]; then
  python -m pip install -e '.[dev]'
elif [[ -f "requirements-dev.txt" ]]; then
  python -m pip install -r requirements-dev.txt
elif [[ -f "requirements.txt" ]]; then
  python -m pip install -r requirements.txt
else
  echo "No dependency manifest found (pyproject.toml / requirements*.txt)."
fi

echo "Environment ready. Activate with: source $VENV_DIR/bin/activate"
