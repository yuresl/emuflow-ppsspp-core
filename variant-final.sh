#!/bin/bash
# Leva ao histórico do volume a leitura do disco sob demanda (a correção da espera ativa já está lá) e gera o patch.
# Rodar uma vez só: de novo, não haveria o que commitar.
set -euo pipefail
cd /work/ppsspp
git checkout -q -- Core/Loaders.cpp libretro/Makefile.common
rm -f Core/FileLoaders/RemoteFileLoader.*
tr -d '\r' < /src/jit/port_remote.py > /tmp/port_remote.py
python3 /tmp/port_remote.py
git add Core/Loaders.cpp libretro/Makefile.common Core/FileLoaders/RemoteFileLoader.h Core/FileLoaders/RemoteFileLoader.cpp
git -c user.email=build@emuflow.local -c user.name="EmuFlow build" commit -q -m "EmuFlow: disco do PSP lido sob demanda por um worker do navegador"
git diff upstream/master HEAD -- . ':!ffmpeg' > /out/patches/emuflow-sobre-oficial.patch
git log --oneline -3 | cut -c1-90
wc -l /out/patches/emuflow-sobre-oficial.patch
git status --short Core libretro | head
rm -f Core/Loaders.o libretro/ppsspp_libretro_emscripten.bc
