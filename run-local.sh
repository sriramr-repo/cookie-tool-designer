#!/bin/zsh
# Launch Cookie Tool Designer with Homebrew's Cairo library available to Python.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  print -u2 "uv is required. Install it from https://docs.astral.sh/uv/"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  print -u2 "Homebrew and Cairo are required for SVG uploads on macOS."
  print -u2 "Install Homebrew, then run: brew install cairo"
  exit 1
fi

cairo_prefix="$(brew --prefix cairo 2>/dev/null || true)"
if [[ -z "$cairo_prefix" || ! -d "$cairo_prefix/lib" ]]; then
  print -u2 "Cairo is not installed. Run: brew install cairo"
  exit 1
fi

export DYLD_FALLBACK_LIBRARY_PATH="$cairo_prefix/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
export DYLD_LIBRARY_PATH="$cairo_prefix/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
exec uv run streamlit run app.py "$@"
