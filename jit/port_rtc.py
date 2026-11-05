#!/usr/bin/env python3
# Espera ativa no relógio: alguns jogos (Dante's Inferno) chamam sceRtcGetCurrentTick centenas de milhares de vezes por
# segundo só para esperar o tempo passar. Cada volta custa um syscall e um reagendamento no navegador.
import sys

p = "/work/ppsspp/Core/HLE/sceRtc.cpp"
s = open(p, encoding="utf8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
s = s.replace("\r\n", "\n")
a = """	if (Memory::IsValid4AlignedRange(tickPtr, 8)) {
		Memory::WriteUnchecked_U64(curTick, tickPtr);
	}
	hleEatCycles(300);
	hleReSchedule("rtc current tick");
"""
b = """	if (Memory::IsValid4AlignedRange(tickPtr, 8)) {
		Memory::WriteUnchecked_U64(curTick, tickPtr);
	}
	hleEatCycles(RtcSpinCycles());
	hleReSchedule("rtc current tick");
"""
assert a in s
s = s.replace(a, b)
a = "static u32 sceRtcGetCurrentTick(u32 tickPtr)\n"
assert a in s
s = s.replace(a, """// EmuFlow: um jogo em espera ativa no relógio passa mais tempo emulado por chamada, e o emulador dá menos voltas até o
// mesmo instante. Só vale depois de muitas chamadas seguidas, muito próximas: quem lê o relógio de vez em quando não muda.
int g_rtcSpinExtraCycles = 2700;

static int RtcSpinCycles() {
	const int NORMAL_CYCLES = 300;
	const int NEAR_CYCLES = 2000;
	const int STREAK = 32;
	static u64 lastTicks = 0;
	static int lastCycles = 0;
	static int streak = 0;

	const u64 ticks = CoreTiming::GetTicks(currentMIPS);
	streak = ticks - lastTicks - lastCycles < (u64)NEAR_CYCLES ? streak + 1 : 0;
	lastTicks = ticks;
	lastCycles = streak > STREAK ? NORMAL_CYCLES + g_rtcSpinExtraCycles : NORMAL_CYCLES;
	return lastCycles;
}

""" + a)
open(p, "w", encoding="utf8", newline="").write(s.replace("\n", nl))
print("rtc ok")
