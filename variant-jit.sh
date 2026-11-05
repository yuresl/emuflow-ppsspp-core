#!/bin/bash
set -euo pipefail
cd /work/ppsspp
git checkout -q -- Core/MIPS/IR/IRJit.h Core/MIPS/IR/IRJit.cpp libretro/Makefile.common Core/HLE/sceRtc.cpp
tr -d '' < /src/jit/port_rtc.py > /tmp/port_rtc.py
python3 /tmp/port_rtc.py
rm -f Core/HLE/sceRtc.o
tr -d '\r' < /src/jit/port.py > /tmp/port.py
tr -d '\r' < /src/jit/port_opt.py > /tmp/port_opt.py
python3 /tmp/port.py
git status --short Core/MIPS/IR libretro/Makefile.common
grep -n "bool IsValid\|class JitBlock \|int FindByEntry\|GetEntry\|DepthMirroredSlow" Core/MIPS/IR/IRJit.h Core/MemMap.h | head
find Core/MIPS/IR Core/MIPS/MIPS.o -name '*.o' -delete 2>/dev/null || true
rm -f Core/MIPS/IR/*.o Core/MIPS/MIPS.o Core/MIPS/JitCommon/JitCommon.o libretro/ppsspp_libretro_emscripten.bc
