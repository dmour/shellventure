#!/usr/bin/env bash
# Install shellventure: puts `shellventure` (and the short alias `sv`) in ~/.local/bin. Needs python3 3.9+ and the rich library.
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
python3 -c 'import rich' 2>/dev/null || python3 -m pip install --user rich
mkdir -p ~/.local/bin && ln -sf "$DIR/bin/shellventure" ~/.local/bin/shellventure && ln -sf "$DIR/bin/shellventure" ~/.local/bin/sv
echo "installed: ~/.local/bin/shellventure"
for t in git jq docker kind kubectl helm gcloud openssl; do
  command -v "$t" >/dev/null && printf '  \033[32m✔\033[0m %s\n' "$t" || printf '  \033[33m·\033[0m %s (some worlds need it)\n' "$t"
done
echo "run: shellventure   (or: sv)"
