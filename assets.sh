#!/bin/bash
# Empacota os assets do PPSSPP do commit atual (compat.ini, atlas, shaders...) em /out/<nome>/ppsspp-assets.zip.
set -euo pipefail
OUT=/out/$1; mkdir -p "$OUT"; rm -f "$OUT/ppsspp-assets.zip"
cd /work/ppsspp/assets
zip -q -r "$OUT/ppsspp-assets.zip" . -x '*.git*'
ls -la "$OUT/ppsspp-assets.zip"; grep -c ReadbackShadow compat.ini
du -sh .; ls | head -30
