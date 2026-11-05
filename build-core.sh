#!/bin/bash
# Etapa 1: compila o PPSSPP (com o FFmpeg de ext/ffmpeg) em ppsspp_libretro_emscripten.bc.
# Mesmos passos de libretro/emscripten/build_emscripten.sh, sem baixar nada de novo.
set -euo pipefail
cd /work/ppsspp
JOBS=$(nproc)

# Desde o merge do oficial o FFmpeg (ext/ffmpeg) é compilado junto com o core, dentro do .bc.

sed -i 's|return getauxval(hwcap_type);|return 1;|g' ext/cpu_features/src/hwcaps.c
sed -i 's|#include <sys/auxv.h>||g' ext/cpu_features/src/hwcaps.c
if [ -f ext/aemu_postoffice/client/sock_impl_linux.c ]; then
  sed -i 's|#ifndef __linux__|#ifdef SO_NOSIGPIPE|g' ext/aemu_postoffice/client/sock_impl_linux.c
fi
if [ -f ext/aemu_postoffice/server_cpp/native_socket_linux.cpp ]; then
  sed -i 's|#ifndef __linux__|#ifdef SO_NOSIGPIPE|g' ext/aemu_postoffice/server_cpp/native_socket_linux.cpp
fi
if [ ! -f ext/armips/ext/filesystem/.emuflow ]; then
  rm -rf ext/armips/ext/filesystem
  git clone -q https://github.com/gulrak/filesystem.git ext/armips/ext/filesystem
  touch ext/armips/ext/filesystem/.emuflow
fi

cd libretro
emmake make platform=emscripten -j"$JOBS"
mkdir -p emscripten/build
rm -rf emscripten/build; mkdir -p emscripten/build; cp ./*.bc emscripten/build/
ls -la emscripten/build | head
