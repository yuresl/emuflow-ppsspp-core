#!/bin/bash
# Acrescenta ao PPSSPP do volume a leitura do disco sob demanda (jit/port_remote.py).
set -euo pipefail
cd /work/ppsspp
git checkout -q -- Core/Loaders.cpp libretro/Makefile.common
rm -f Core/FileLoaders/RemoteFileLoader.*
tr -d '\r' < /src/jit/port_remote.py > /tmp/port_remote.py
python3 /tmp/port_remote.py
rm -f Core/Loaders.o libretro/ppsspp_libretro_emscripten.bc
git status --short Core libretro | head
