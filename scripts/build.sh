#!/usr/bin/env bash
# Build the Catala Python package and the Lean bridge.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${CATALA:=catala}"
: "${CATALA_STDLIB:=_build/libcatala}"
: "${CATALA_PY_RUNTIME:=/tmp/catala-root/usr/lib/x86_64-linux-gnu/ocaml/5.3.0/catala/runtime/python/src/catala}"
RT_SRC="${CATALA_RUNTIME_SRC:-/tmp/catala-root/usr/lib/x86_64-linux-gnu/ocaml/5.3.0/catala/runtime}"

echo "== Catala =="
grep -hv '^> Module\|^> Using' contracts/schema.catala_en contracts/property_xol_v1.catala_en \
  > build/combined.catala_en
"$CATALA" typecheck --stdlib="$CATALA_STDLIB" build/combined.catala_en
mkdir -p build/pkg
touch build/pkg/__init__.py
for f in "$RT_SRC"/*.catala_en; do
  name=$(grep -m1 '^> Module ' "$f" | awk '{print $3}')
  [ -z "$name" ] && continue
  "$CATALA" python --stdlib="$CATALA_STDLIB" --no-stdlib -o "build/pkg/$name.py" "$f" 2>/dev/null \
    || printf '# stub for external module %s\n' "$name" > "build/pkg/$name.py"
done
"$CATALA" python --stdlib="$CATALA_STDLIB" -o build/pkg/property_xol_v1.py build/combined.catala_en

echo "== Lean =="
lake build

echo "== done =="
