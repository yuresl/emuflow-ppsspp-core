#!/bin/bash
set -uo pipefail
cd /work/ppsspp/libretro
emmake make platform=emscripten clean > /dev/null 2>&1
find .. -name '*.o' -not -path '../ffmpeg/*' -delete
rm -f ./*.bc
echo limpo
