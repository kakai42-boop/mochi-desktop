#!/usr/bin/env bash
# Linux cross-build. Requires Python 3.12+, zstd, mingw-w64 GCC/binutils and NSIS.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
output_root="${1:-$project_root/dist/windows}"
mkdir -p "$output_root/Mochi"
python3 "$project_root/packaging/windows/fetch_runtime.py" \
  --cache "$output_root/cache" --out "$output_root/Mochi/runtime"
(
  cd "$project_root/packaging/windows"
  x86_64-w64-mingw32-windres launcher.rc -O coff -o "$output_root/launcher-res.o"
  x86_64-w64-mingw32-gcc -municode -mwindows -O2 -Wall -Wextra -Werror -static \
    launcher.c "$output_root/launcher-res.o" -o "$output_root/Mochi/Mochi.exe"
)
python3 "$project_root/packaging/windows/assemble.py" "$output_root/Mochi"
makensis -V2 "-DBUNDLE=$output_root/Mochi" \
  "-DOUTPUT=$output_root/Mochi-Windows11-Setup.exe" "$project_root/packaging/windows/installer.nsi"
python3 - "$output_root" <<'PY'
from pathlib import Path
import shutil, sys
root = Path(sys.argv[1])
shutil.make_archive(str(root / 'Mochi-Windows11-Portable'), 'zip', root, 'Mochi')
PY
