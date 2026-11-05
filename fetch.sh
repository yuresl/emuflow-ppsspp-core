#!/bin/bash
# Baixa os fontes nos commits de versions.env e aplica o patch do EmuFlow, dentro do volume /work.
set -euo pipefail
tr -d '\r' < /src/versions.env > /tmp/v.env; . /tmp/v.env
cd /work
[ -d ppsspp/.git ] || git clone --filter=blob:none "$PPSSPP_REPO" ppsspp
git -C ppsspp fetch -q origin
git -C ppsspp checkout -q -f "$PPSSPP_COMMIT"
git -C ppsspp submodule update --init --recursive --depth 1 --jobs 8
git -C ppsspp apply --exclude='ext/*' /src/patches/emuflow-sobre-oficial.patch || true
git -C ppsspp apply --include='ext/xxhash.h' /src/patches/emuflow-sobre-oficial.patch || true
# Ad hoc do PSP pelo site (D107): relay fixo, sem DNS, e MSG_PEEK que o Emscripten não tem.
git -C ppsspp apply /src/patches/emuflow-adhoc.patch
git -C ppsspp/ext/aemu_postoffice apply /src/patches/aemu-postoffice-peek.patch
# Tamanho do Memory Stick que não zera a conta de espaço livre em 32 bits.
git -C ppsspp apply /src/patches/emuflow-memstick.patch
[ -d RetroArch/.git ] || git clone --filter=blob:none -b "$RETROARCH_BRANCH" "$RETROARCH_REPO" RetroArch
git -C RetroArch fetch -q origin
git -C RetroArch checkout -q "$RETROARCH_COMMIT"
mkdir -p RetroArch/EmulatorJS/data/cores
git -C ppsspp log -1 --format='ppsspp %h %cI %s'
git -C RetroArch log -1 --format='retroarch %h %cI %s'
