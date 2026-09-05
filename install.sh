#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FOLDERS=(trakt_core trakt_schedule trakt_month trakt_releases)

usage() {
  echo "Usage: $0 [--copy] <tesserae-plugins-dir>" >&2
  echo "Symlinks the four trakt_* folders into Tesserae's plugin code dir." >&2
  echo "Bare-metal:  /path/to/tesserae/plugins" >&2
  echo "Docker:      /opt/tesserae/data/marketplace   (not data/plugins)" >&2
  exit 1
}

copy=0
dest=""
for arg in "$@"; do
  case "$arg" in
    --copy) copy=1 ;;
    -h|--help) usage ;;
    *) dest="$arg" ;;
  esac
done

[[ -n "$dest" ]] || usage
[[ -d "$dest" ]] || { echo "Not a directory: $dest" >&2; exit 1; }
dest="$(cd "$dest" && pwd)"

for folder in "${FOLDERS[@]}"; do
  src="$ROOT/$folder"
  target="$dest/$folder"
  [[ -d "$src" ]] || { echo "Missing $src" >&2; exit 1; }
  if [[ -e "$target" && ! -L "$target" ]]; then
    echo "Already exists (not a symlink): $target" >&2
    echo "Remove it first, or pass another plugins dir." >&2
    exit 1
  fi
  rm -f "$target"
  if [[ "$copy" -eq 1 ]]; then
    cp -R "$src" "$target"
    echo "copied $folder"
  else
    ln -s "$src" "$target"
    echo "linked $folder -> $src"
  fi
done

echo
echo "Restart Tesserae so the loader picks them up."
echo "Updates: git pull in this repo (symlinks) or re-run with --copy."
