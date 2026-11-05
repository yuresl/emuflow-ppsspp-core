# Otimizações sobre o porte: importado por port.py logo antes de gravar os arquivos.
# Saídas encadeadas, operações sem efeito no wasm e produto escalar direto.


def apply(cpp, hdr, rep):
    # Operações rápidas que deixam de passar pelo interpretador.
    cpp = rep(cpp, "	case IROp::FSat0_1: case IROp::FSatMinus1_1:\n	case IROp::Vec4VfpuDot: case IROp::Vec4VfpuMultiDot:\n", "")
    cpp = rep(cpp, "	case IROp::ApplyRoundingMode: case IROp::RestoreRoundingMode:\n", "")
    cpp = rep(cpp, "	TYPE_MIRROR = 3,    // Memory::DepthMirroredSlow(address) -> address\n",
              "	TYPE_MIRROR = 3,    // Memory::DepthMirroredSlow(address) -> address\n	TYPE_DOT = 4,       // vfpu_dot(a, b) -> float\n	TYPE_MULTI_DOT = 5, // vfpu_multi_dot(out, block, v, terms, transposed)\n")
    cpp = rep(cpp, "		s.uleb(4);\n		s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_I32);\n",
              "		s.uleb(6);\n		s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_I32);\n")
    cpp = rep(cpp, "		s.u8(0x60); s.uleb(1); s.u8(T_I32); s.uleb(1); s.u8(T_I32);\n",
              "		s.u8(0x60); s.uleb(1); s.u8(T_I32); s.uleb(1); s.u8(T_I32);\n		s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_F32);\n		s.u8(0x60); s.uleb(5); s.u8(T_I32); s.u8(T_I32); s.u8(T_I32); s.u8(T_I32); s.u8(T_I32); s.uleb(0);\n")
    cpp = rep(cpp, '#include "Core/MIPS/IR/IRJit.h"\n', '#include "Core/MIPS/IR/IRJit.h"\n#include "Core/MIPS/MIPSVFPUUtils.h"\n')
    cpp = rep(cpp, "		case IROp::Nop: return true;\n", """		case IROp::Nop: return true;
		// fesetround does nothing in wasm, and there's no flush-to-zero: these only cost time.
		case IROp::ApplyRoundingMode: case IROp::RestoreRoundingMode: return true;
		case IROp::FSat0_1: clampF(inst, 0x00000000, 0.0f); return true;
		case IROp::FSatMinus1_1: clampF(inst, 0xBF800000, -1.0f); return true;
		case IROp::Vec4VfpuDot:
			// The arguments are read from MIPSState, so it only needs to be current. The cache stays.
			Flush();
			e_.get(L_MIPS); e_.i32c(SF(inst.src1) * 4); e_.op(OP_I32_ADD);
			e_.get(L_MIPS); e_.i32c(SF(inst.src2) * 4); e_.op(OP_I32_ADD);
			e_.i32c((uint32_t)(uintptr_t)&vfpu_dot);
			e_.op(OP_CALL_INDIRECT); e_.uleb(TYPE_DOT); e_.uleb(0);
			putF(SF(inst.dest));
			return true;
		case IROp::Vec4VfpuMultiDot:
			Flush();
			for (uint32_t i = 0; i < 4; i++) Forget(SF(inst.dest + i));
			e_.get(L_MIPS); e_.i32c(SF(inst.dest) * 4); e_.op(OP_I32_ADD);
			e_.get(L_MIPS); e_.i32c(SF(inst.src1) * 4); e_.op(OP_I32_ADD);
			e_.get(L_MIPS); e_.i32c(SF(inst.src2) * 4); e_.op(OP_I32_ADD);
			e_.i32c(IRMULTIDOT_TERMS(inst.constant));
			e_.i32c((inst.constant & IRMULTIDOT_TRANSPOSED) != 0 ? 1 : 0);
			e_.i32c((uint32_t)(uintptr_t)&vfpu_multi_dot);
			e_.op(OP_CALL_INDIRECT); e_.uleb(TYPE_MULTI_DOT); e_.uleb(0);
			return true;
""")
    cpp = rep(cpp, "	// The interpreter may change anything in MIPSState (a syscall can even switch threads): write back, forget the cache.\n",
              """	// Drop a slot from the cache. Call Flush first, so that MIPSState holds its value.
	void Forget(uint32_t slot) {
		if (slot >= NUM_SLOTS || !local_[slot])
			return;
		local_[slot] = 0;
		dirty_[slot] = false;
		cached_.erase(std::find(cached_.begin(), cached_.end(), slot));
	}
	// vfpu_clamp(v, min, 1.0f): NaN stays, and -0.0 becomes +0.0 when min is +0.0.
	void clampF(const IRInst &inst, uint32_t minBits, float minValue) {
		get(SF(inst.src1)); e_.set(L_I0);
		e_.i32c(0x3F800000);
		e_.i32c(minBits); e_.get(L_I0);
		e_.get(L_I0); e_.op(OP_F32_REINTERPRET_I32); F32Const(minValue); e_.op(OP_F32_LE);
		e_.op(OP_SELECT);
		e_.get(L_I0); e_.op(OP_F32_REINTERPRET_I32); F32Const(1.0f); e_.op(OP_F32_GE);
		e_.op(OP_SELECT);
		put(SF(inst.dest));
	}

	// The interpreter may change anything in MIPSState (a syscall can even switch threads): write back, forget the cache.
""")
    cpp = rep(cpp, "#include <cstring>\n", "#include <algorithm>\n#include <cstdlib>\n#include <cstring>\n")

    # Saídas encadeadas: como o IR_EXIT do interpretador, o bloco de destino roda sem voltar ao despacho em C. A tabela é
    # consultada na hora da saída, então vale também para blocos compilados depois deste.
    i = cpp.index("	// Table slot of the compiled block at a PSP address (and the emuhack word it was compiled for), or 0.\n")
    j = cpp.index("	BlockCompiler(Emitter &e,")
    cpp = cpp[:i] + cpp[j:]
    cpp = rep(cpp, "uint32_t journal, LinkResolver link)\n		: out_(e), space_(space), base_(memBase), interp_(interpIdx), journal_(journal), link_(link) {",
              "uint32_t journal, uint32_t entries)\n		: out_(e), space_(space), base_(memBase), interp_(interpIdx), journal_(journal), entries_(entries) {")
    cpp = rep(cpp, "	LinkResolver link_;\n", "	uint32_t entries_;  // Address of IRWasmJit's table by arena offset, or 0 for no chaining.\n")
    i = cpp.index("	// Leave the block for a fixed PSP address.")
    j = cpp.index("	void exitIf(const IRInst &inst, uint8_t cmp, bool withZero) {")
    cpp = cpp[:i] + """	// Run the block at the PC in L_I0 right away if it's compiled and downcount lasts, like IR_EXIT in the interpreter.
	// shadowAddr: address of its block shadow entry when the target is known here, or 0.
	void chain(uint32_t shadowAddr) {
		get(S_DOWNCOUNT); e_.i32c(0); e_.op(OP_I32_GE_S);
		If();
		if (shadowAddr) {
			e_.i32c(0); e_.mem(OP_I32_LOAD, 2, shadowAddr);
		} else {
			e_.get(L_I0); e_.i32c(Memory::BLOCK_SHADOW_ENTRY_MASK); e_.op(OP_I32_AND);
			e_.mem(OP_I32_LOAD, 2, (uint32_t)(uintptr_t)space_.blockShadow);
		}
		e_.i32c(2); e_.op(OP_I32_SHL); e_.i32c((IRWasmJit::ENTRIES - 1) << 2); e_.op(OP_I32_AND);
		e_.mem(OP_I32_LOAD, 2, entries_);
		e_.tee(L_I1); e_.i32c(0); e_.op(OP_I32_GT_S);
		If();
		e_.get(L_MIPS); e_.get(L_I0); e_.mem(OP_I32_STORE, 2, S_PC * 4);
		e_.get(L_MIPS); e_.get(L_ARENA); e_.get(L_I1);
		e_.op(OP_RETURN_CALL_INDIRECT); e_.uleb(TYPE_BLOCK); e_.uleb(0);
		End();
		End();
	}
	void exitTo(u32 target) {
		Flush();
		if (entries_ && space_.IsValid4AlignedAddress(target)) {
			e_.i32c(target); e_.set(L_I0);
			chain((uint32_t)(uintptr_t)space_.GetBlockShadowEntry(target));
		}
		e_.i32c(target); e_.op(OP_RETURN);
	}
	// Leave for the PC on the stack. A bad one goes back to the dispatcher, which raises the exception.
	void exitToStack() {
		e_.set(L_I0);
		Flush();
		if (entries_) {
			e_.get(L_I0); e_.i32c(3); e_.op(OP_I32_AND); e_.op(OP_I32_EQZ);
			If();
			chain(0);
			End();
		}
		e_.get(L_I0); e_.op(OP_RETURN);
	}
""" + cpp[j:]
    cpp = rep(cpp, "case IROp::ExitToReg: Flush(); get(SR(inst.src1)); e_.op(OP_RETURN); endsWithExit_ = true; return true;",
              "case IROp::ExitToReg: get(SR(inst.src1)); exitToStack(); endsWithExit_ = true; return true;")
    cpp = rep(cpp, "case IROp::ExitToPC: Flush(); get(S_PC); e_.op(OP_RETURN); endsWithExit_ = true; return true;",
              "case IROp::ExitToPC: get(S_PC); exitToStack(); endsWithExit_ = true; return true;")

    # A tabela por posição na arena fica num endereço fixo, para o código gerado poder lê-la.
    hdr = rep(hdr, "	std::vector<int32_t> entries_;     // by IR arena offset: >0 table index, <=0 -executions, NEVER\n",
              "	int32_t *entries_ = nullptr;       // by IR arena offset: >0 table index, <=0 -executions, NEVER\n	size_t entriesUsed_ = 0;\n	void ClearEntries();\n")
    hdr = rep(hdr, "	u32 Run(int func, MIPSState *mips, const IRInst *arena, u32 offset);\n",
              "	u32 Run(int func, MIPSState *mips, const IRInst *arena, u32 offset);\n\n	// Size of the table by arena offset, a power of two above the arena's limit of 4M instructions.\n	static constexpr u32 ENTRIES = 1 << 23;\n")
    hdr = rep(hdr, "		if (offset >= entries_.size())\n			return 0;\n		int32_t &e = entries_[offset];", "		int32_t &e = entries_[offset];")
    cpp = rep(cpp, "void IRWasmJit::Reset() {\n	entries_.clear();\n", """void IRWasmJit::ClearEntries() {
	if (entries_)
		memset(entries_, 0, entriesUsed_ * sizeof(int32_t));
	entriesUsed_ = 0;
}

void IRWasmJit::Reset() {
	ClearEntries();
""")
    cpp = rep(cpp, "		token_ = token;\n		entries_.clear();\n", "		token_ = token;\n		ClearEntries();\n")
    cpp = rep(cpp, "	sliceMode_ = mode;\n	if (sliceMode_ != lastMode_) {", "	if (!entries_)\n		entries_ = (int32_t *)calloc(ENTRIES, sizeof(int32_t));\n	sliceMode_ = mode;\n	if (sliceMode_ != lastMode_) {")
    cpp = rep(cpp, "	if (entries_.size() < arenaSize)\n		entries_.resize(arenaSize + 4096, 0);\n", "	if (arenaSize > entriesUsed_)\n		entriesUsed_ = arenaSize;\n")
    cpp = rep(cpp, "		if (ok[i].offset < entries_.size())\n			entries_[ok[i].offset] = slots[i];\n", "		entries_[ok[i].offset] = slots[i];\n")
    i = cpp.index("	std::unordered_map<u32, int> batch;\n")
    j = cpp.index("	// Pass 2: the real code.\n")
    cpp = cpp[:i] + "	// Chaining only in normal mode: verify mode checks one block at a time.\n	const uint32_t chainEntries = sliceMode_ == 1 ? (uint32_t)(uintptr_t)entries_ : 0;\n\n" + cpp[j:]
    cpp = rep(cpp, "BlockCompiler bc(fn, space, memBase, interpIdx, journal, BlockCompiler::LinkResolver());", "BlockCompiler bc(fn, space, memBase, interpIdx, journal, 0);")
    cpp = rep(cpp, "BlockCompiler bc(fn, space, memBase, interpIdx, journal, resolver);", "BlockCompiler bc(fn, space, memBase, interpIdx, journal, chainEntries);")
    cpp = rep(cpp, "	// Table slots up front, so blocks of the same batch can link to each other.\n", "	// Table slots up front.\n")

    # Medição: tempo em chamadas de sistema, onde a GPU emulada processa as listas.
    hdr = rep(hdr, "	static double cpuMs;\n", "	static double cpuMs;\n	static double syscallMs;\n")
    cpp = rep(cpp, "double IRWasmJit::cpuMs = 0.0;\n", "double IRWasmJit::cpuMs = 0.0;\ndouble IRWasmJit::syscallMs = 0.0;\n")
    cpp = rep(cpp, "	prog[1].op = IROp::ExitToPC;\n	IRInterpret(mips, prog);\n", """	prog[1].op = IROp::ExitToPC;
	if (inst->op == IROp::Syscall || inst->op == IROp::CallReplacement) {
		const double start = emscripten_get_now();
		IRInterpret(mips, prog);
		IRWasmJit::syscallMs += emscripten_get_now() - start;
		return;
	}
	IRInterpret(mips, prog);
""")
    i = cpp.rindex("#endif")
    cpp = cpp[:i] + 'extern "C" EMSCRIPTEN_KEEPALIVE double emuflow_wasmjit_syscall_ms() { return MIPSComp::IRWasmJit::syscallMs; }\n\n' + cpp[i:]

    # Medição: tempo e contagem por chamada de sistema e por função substituída.
    cpp = rep(cpp, "namespace MIPSComp {\n\nstatic int g_opCounts[256];\n", """struct SysStat { int count = 0; double ms = 0.0; };
static std::unordered_map<u32, SysStat> g_sysStats;
static std::vector<std::pair<u32, SysStat>> g_sysSnapshot;

namespace MIPSComp {

static int g_opCounts[256];
""")
    cpp = rep(cpp, """		IRInterpret(mips, prog);
		IRWasmJit::syscallMs += emscripten_get_now() - start;
		return;
""", """		IRInterpret(mips, prog);
		const double elapsed = emscripten_get_now() - start;
		IRWasmJit::syscallMs += elapsed;
		SysStat &stat = g_sysStats[inst->op == IROp::Syscall ? inst->constant : (0x80000000 | inst->constant)];
		stat.count++;
		stat.ms += elapsed;
		return;
""")
    cpp = rep(cpp, '#include "Core/MIPS/MIPSVFPUUtils.h"\n', '#include "Core/MIPS/MIPSVFPUUtils.h"\n#include "Core/HLE/HLE.h"\n#include "Core/HLE/ReplaceTables.h"\n')
    i = cpp.rindex("#endif")
    cpp = cpp[:i] + """extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_sys_snapshot() {
	g_sysSnapshot.assign(g_sysStats.begin(), g_sysStats.end());
	return (int)g_sysSnapshot.size();
}
extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_sys_count(int i) { return g_sysSnapshot[i].second.count; }
extern "C" EMSCRIPTEN_KEEPALIVE double emuflow_wasmjit_sys_ms(int i) { return g_sysSnapshot[i].second.ms; }
extern "C" EMSCRIPTEN_KEEPALIVE const char *emuflow_wasmjit_sys_name(int i) {
	const u32 key = g_sysSnapshot[i].first;
	if (key & 0x80000000) {
		const ReplacementTableEntry *f = GetReplacementFunc(key & 0x7FFFFFFF);
		return f ? f->name : "?";
	}
	const u32 callno = (key >> 6) & 0xFFFFF;
	const char *name = GetHLEFuncName((int)((callno & 0xFF000) >> 12), (int)(callno & 0xFFF));
	return name ? name : "?";
}

""" + cpp[i:]

    # Só blocos muito executados viram código nativo: o resto roda no interpretador, que já está otimizado, e não passa
    # pela camada básica do V8, mais lenta que ele.
    hdr = rep(hdr, "	static constexpr int THRESHOLD = 50;\n", "")
    hdr = rep(hdr, "	static int stats[8];\n", "	static int stats[8];\n	static int threshold;\n")
    hdr = rep(hdr, "		if (e > -THRESHOLD) {\n			e--;\n		} else if (e == -THRESHOLD) {", "		if (e > -threshold) {\n			e--;\n		} else if (e <= -threshold && e != NEVER) {")
    cpp = rep(cpp, "int IRWasmJit::mode = 1;\n", "int IRWasmJit::mode = 1;\nint IRWasmJit::threshold = 50;\n")
    i = cpp.rindex("#endif")
    cpp = cpp[:i] + 'extern int g_rtcSpinExtraCycles;\nextern "C" EMSCRIPTEN_KEEPALIVE void emuflow_rtc_extra(int n) { g_rtcSpinExtraCycles = n; }\n\n' + cpp[i:]
    i = cpp.rindex("#endif")
    cpp = cpp[:i] + 'extern "C" EMSCRIPTEN_KEEPALIVE void emuflow_wasmjit_threshold(int t) { MIPSComp::IRWasmJit::threshold = t; }\n\n' + cpp[i:]
    return cpp, hdr
