#!/bin/bash
# Etapa 2: liga o .bc no RetroArch do EmulatorJS e empacota ppsspp-thread-wasm.data em /out/<nome>.
# Uso: link.sh <nome> [profiling] [minasync] [jit]
#   profiling: mantém os nomes das funções no wasm (o código é o mesmo), para perfilar.
#   minasync:  Asyncify só no laço principal (MIN_ASYNC), em vez de em quase todo o wasm.
set -euo pipefail
NAME=$1; shift
PROFILING=0; JIT=0; EJS_ASYNC=1; EXTRA_MAKE=""
for opt in "$@"; do
  case "$opt" in
    profiling) PROFILING=1 ;;
    jit) JIT=1 ;;
    minasync) EJS_ASYNC=0; EXTRA_MAKE="$EXTRA_MAKE MIN_ASYNC=1" ;;
    *) echo "opção desconhecida: $opt"; exit 1 ;;
  esac
done

cd /work/RetroArch
git checkout -q -- Makefile.emulatorjs emulatorjs/build-emulatorjs.sh audio/audio_driver.c
# Controle de taxa do áudio com o tom suavizado.
tr -d '' < /src/patches/retroarch-audio-suave.patch | git apply
rm -rf ffmpeg emulatorjs/*.bc
cp -r /work/ppsspp/libretro/emscripten/build ffmpeg
cp /work/ppsspp/libretro/emscripten/build/*.bc emulatorjs/

# O script fixa ASYNC para o ppsspp; aqui vira variável, e o Makefile aceita flags extras de ligação.
sed -i 's/^\( *\)async=1$/\1async=${EJS_ASYNC:-1}/' emulatorjs/build-emulatorjs.sh
printf '\nLDFLAGS += $(EXTRA_LDFLAGS)\n' >> Makefile.emulatorjs
# Desde o merge do PPSSPP oficial o FFmpeg vem dentro do .bc.
sed -i '/additional_libs = ffmpeg/d' Makefile.emulatorjs

EXTRA_LDFLAGS=""
# A tabela de funções cresce: o JIT (jit/, fora do core publicado) instala nela as funções que gera.
[ "$JIT" = 1 ] && EXTRA_LDFLAGS="-sALLOW_TABLE_GROWTH=1"
[ "$PROFILING" = 1 ] && EXTRA_LDFLAGS="$EXTRA_LDFLAGS --profiling-funcs"

rm -f EmulatorJS/data/cores/ppsspp-thread-wasm.data ../EmulatorJS/data/cores/ppsspp-thread-wasm.data
(cd emulatorjs && EJS_ASYNC=$EJS_ASYNC EXTRA_LDFLAGS="$EXTRA_LDFLAGS" MAKEFLAGS="$EXTRA_MAKE" emmake bash ./build-emulatorjs.sh --clean --threads)

DATA=/work/EmulatorJS/data/cores/ppsspp-thread-wasm.data
[ -f "$DATA" ] || DATA=/work/RetroArch/EmulatorJS/data/cores/ppsspp-thread-wasm.data

OUT=/out/$NAME
mkdir -p "$OUT"
rm -f "$OUT/ppsspp-thread-wasm.data"
cp "$DATA" "$OUT/ppsspp-thread-wasm.data"

META=$(mktemp -d)
cp /work/ppsspp/LICENSE.TXT "$META/license.txt"
cat > "$META/core.json" <<'EOF'
{"name":"ppsspp","extensions":["elf","iso","cso","prx","pbp"],"options":{"defaultWebGL2":true,"requireThreads":true},"save":false,"license":"LICENSE.TXT","repo":"https://github.com/EmulatorJS/ppsspp"}
EOF
printf '{\n    "minimumEJSVersion": "4.3.0",\n    "version": "2.0.3"\n}\n' > "$META/build.json"
(cd "$META" && 7z a -bd -t7z "$OUT/ppsspp-thread-wasm.data" core.json license.txt build.json > /dev/null)
rm -rf "$META"

{
  git -C /work/ppsspp log -1 --format='ppsspp %H'
  git -C /work/RetroArch log -1 --format='retroarch %H'
  echo "emscripten $(emcc --version | head -1)"
  echo "opcoes $*"
} > "$OUT/versions.txt"
ls -la "$OUT"
sha256sum "$OUT/ppsspp-thread-wasm.data"
