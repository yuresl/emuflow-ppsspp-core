#!/usr/bin/env python3
# Porta o IRWasmJit de xandps/ppsspp-wasm (GPL, commit aa60f45) para o PPSSPP oficial que usamos, e o liga ao despacho.
# O interpretador atual é a referência de semântica: cada mudança aqui acompanha Core/MIPS/IR/IRInterpreter.cpp.
import re, shutil, sys

SRC = "/work/xandps/Core/MIPS/IR/"
PP = "/work/ppsspp/"
cpp = open(SRC + "IRWasmJit.cpp", encoding="utf8").read()
hdr = open(SRC + "IRWasmJit.h", encoding="utf8").read()


def rep(s, a, b, count=1):
    assert s.count(a) >= 1 and (count == 0 or s.count(a) == count), (s.count(a), a[:90])
    return s.replace(a, b)


def drop_case(s, start, end):
    i = s.index(start)
    j = s.index(end, i)
    return s[:i] + s[j:]


# ---- Cabeçalho ----
hdr = rep(hdr, "(arcavive-psp, P2)", "(portado de xandps/ppsspp-wasm)")
hdr = rep(hdr, "class IRBlockCache;", "class JitBlockTable;")
hdr = rep(hdr, "void BeginSlice(IRBlockCache &blocks);", "void BeginSlice(JitBlockTable &blocks, const IRInst *arena, size_t arenaSize, MIPSState *mips);")
hdr = rep(hdr, "void Flush(IRBlockCache &blocks);", "void Flush(JitBlockTable &blocks, const IRInst *arena, MIPSState *mips);")
hdr = rep(hdr, "// Ops without a native translation call IRInterpret from that instruction on, so a block is always correct even\n// when only a prefix of it is native.",
          "// Ops that are slow anyway run through the interpreter one at a time, and the rest of the block stays native. Control\n// ops without a translation call IRInterpret from that instruction on, so a block is always correct.")

# ---- Inclusões e constantes ----
cpp = rep(cpp, '#include "Core/MemMap.h"\n', '#include "Core/MemMap.h"\n#include "Core/MIPS/IR/IRInterpreter.h"\n')
cpp = rep(cpp, "const uint32_t MEM_MASK = 0x3FFFFFFF;",
          """#ifdef MASKED_PSP_MEMORY
const uint32_t MEM_MASK = Memory::MEMVIEW32_MASK;
#else
const uint32_t MEM_MASK = 0xFFFFFFFF;
#endif

// Types of the generated module.
enum : uint32_t {
	TYPE_BLOCK = 0,     // (mips, arena) -> pc
	TYPE_INTERP = 1,    // IRInterpret(mips, inst, chainArena) -> pc
	TYPE_RUN_OP = 2,    // RunOneOp(mips, inst)
	TYPE_MIRROR = 3,    // Memory::DepthMirroredSlow(address) -> address
};

// One op through the interpreter, whatever it does to the state. The ExitToPC only makes it return.
void RunOneOp(MIPSState *mips, const IRInst *inst) {
	IRInst prog[2] = { *inst, {} };
	prog[1].op = IROp::ExitToPC;
	IRInterpret(mips, prog);
}

// Ops that run that way. All of them continue at the next op, unlike the control ops left to Fallback.
bool RunsThroughInterpreter(IROp op) {
	switch (op) {
	case IROp::ReverseBits:
	case IROp::LoadKernel8: case IROp::LoadKernel8Ext: case IROp::LoadKernel16: case IROp::LoadKernel16Ext: case IROp::LoadKernel32:
	case IROp::StoreKernel8: case IROp::StoreKernel16: case IROp::StoreKernel32:
	case IROp::FMin: case IROp::FMax:
	case IROp::FRound: case IROp::FTrunc: case IROp::FCeil: case IROp::FFloor:
	case IROp::FCvtWS: case IROp::FCvtScaledWS:
	case IROp::FSat0_1: case IROp::FSatMinus1_1:
	case IROp::Vec4VfpuDot: case IROp::Vec4VfpuMultiDot:
	case IROp::Vec4Min: case IROp::Vec4Max: case IROp::Vec4Slt: case IROp::Vec4Sge: case IROp::Vec4CvtScaledSW:
	case IROp::Vec4DuplicateUpperBitsAndShift1:
	case IROp::FSin: case IROp::FCos: case IROp::FRSqrt: case IROp::FRecip: case IROp::FAsin: case IROp::FVSqrt:
	case IROp::FExp2: case IROp::FLog2: case IROp::FHalfToFloat: case IROp::FSinCos:
	case IROp::Syscall: case IROp::SyscallUnresolved: case IROp::CallReplacement: case IROp::Interpret:
	case IROp::ApplyRoundingMode: case IROp::RestoreRoundingMode:
		return true;
	default:
		return false;
	}
}""")

# ---- Compilador ----
cpp = rep(cpp, """	BlockCompiler(Emitter &e, uint32_t memBase, uint32_t interpIdx, uint32_t journal, LinkResolver link)
		: out_(e), base_(memBase), interp_(interpIdx), journal_(journal), link_(link) {""",
          """	BlockCompiler(Emitter &e, const Memory::AddressSpace &space, uint32_t memBase, uint32_t interpIdx, uint32_t journal, LinkResolver link)
		: out_(e), space_(space), base_(memBase), interp_(interpIdx), journal_(journal), link_(link) {""")
cpp = rep(cpp, "	Emitter &out_;\n	Emitter e_;\n", "	Emitter &out_;\n	const Memory::AddressSpace &space_;\n	Emitter e_;\n	uint32_t index_ = 0;\n	bool ranOp_ = false;\n")
cpp = rep(cpp, """			if (IsStore(inst.op) && (!journal_ || ++stores > JOURNAL_MAX))
				isPure = false;
			if (!Op(inst))
				break;
			native++;
		}""", """			if (IsStore(inst.op) && (!journal_ || ++stores > JOURNAL_MAX))
				isPure = false;
			index_ = i;
			if (RunsThroughInterpreter(inst.op)) {
				RunOp();
				isPure = false;
			} else if (!Op(inst)) {
				break;
			}
			native++;
		}""")
cpp = rep(cpp, """		e_.i32c(index * (uint32_t)sizeof(IRInst));
		e_.op(OP_I32_ADD);
		e_.i32c(interp_);
		e_.op(OP_CALL_INDIRECT); e_.uleb(0); e_.uleb(0);
		e_.op(OP_RETURN);
	}
""", """		e_.i32c(index * (uint32_t)sizeof(IRInst));
		e_.op(OP_I32_ADD);
		e_.i32c(0);  // No chaining: the dispatcher decides what runs next.
		e_.i32c(interp_);
		e_.op(OP_CALL_INDIRECT); e_.uleb(TYPE_INTERP); e_.uleb(0);
		e_.op(OP_RETURN);
	}

	// The interpreter may change anything in MIPSState (a syscall can even switch threads): write back, forget the cache.
	void RunOp() {
		endsWithExit_ = false;
		Flush();
		for (uint32_t slot : cached_) {
			local_[slot] = 0;
			dirty_[slot] = false;
		}
		cached_.clear();
		e_.get(L_MIPS);
		e_.get(L_ARENA);
		e_.i32c(index_ * (uint32_t)sizeof(IRInst));
		e_.op(OP_I32_ADD);
		e_.i32c((uint32_t)(uintptr_t)&RunOneOp);
		e_.op(OP_CALL_INDIRECT); e_.uleb(TYPE_RUN_OP); e_.uleb(0);
	}
""")
cpp = rep(cpp, """	void storeAddr(const IRInst &inst) { addr(inst); e_.set(L_I3); Journal(L_I3); e_.get(L_I3); }
""", """	void storeAddr(const IRInst &inst) { addr(inst); e_.set(L_I3); Journal(L_I3); e_.get(L_I3); }
	// Like addr, for 16-bit accesses: VRAM's depth mirrors go through Memory::DepthMirrored16.
	void addr16(const IRInst &inst) {
		get(SR(inst.src1));
		if (inst.constant) { e_.i32c(inst.constant); e_.op(OP_I32_ADD); }
		e_.set(L_I0);
		e_.get(L_I0); e_.i32c(0xBFA00000); e_.op(OP_I32_AND); e_.i32c(0x04200000); e_.op(OP_I32_EQ);
		If(T_I32);
		e_.get(L_I0); e_.i32c((uint32_t)(uintptr_t)&Memory::DepthMirroredSlow);
		e_.op(OP_CALL_INDIRECT); e_.uleb(TYPE_MIRROR); e_.uleb(0);
		Else();
		e_.get(L_I0);
		End();
		e_.i32c(MEM_MASK); e_.op(OP_I32_AND);
	}
	// Bits of the slot, or 0 for a negative lane (the 31-bit packs).
	void clampedLane(uint32_t slot) {
		get(slot); e_.set(L_I0);
		e_.get(L_I0); e_.i32c(0); e_.get(L_I0); e_.i32c(0); e_.op(OP_I32_GE_S); e_.op(OP_SELECT);
	}
""")

# Saídas diretas: agora pelo shadow de blocos, no lugar do emuhack na memória do PSP.
cpp = rep(cpp, """		u32 word = 0;
		int slot = link_ && Memory::IsValid4AlignedAddress(target) ? link_(target, &word) : 0;
""", """		u32 word = 0;
		int slot = link_ && space_.IsValid4AlignedAddress(target) ? link_(target, &word) : 0;
""")
cpp = rep(cpp, "// and the emuhack at the target still being the one the link was made for (the block wasn't invalidated).",
          "// and the block shadow at the target still holding the block the link was made for (it wasn't invalidated).")
cpp = rep(cpp, "e_.i32c(0); e_.mem(OP_I32_LOAD, 0, base_ + (target & MEM_MASK)); e_.i32c(word); e_.op(OP_I32_EQ);",
          "e_.i32c(0); e_.mem(OP_I32_LOAD, 2, (uint32_t)(uintptr_t)space_.GetBlockShadowEntry(target)); e_.i32c(word); e_.op(OP_I32_EQ);")

# Leituras e escritas de 16 bits: Mirrored16.
cpp = rep(cpp, "case IROp::Load16: addr(inst); e_.mem(OP_I32_LOAD16_U, 0, base_);", "case IROp::Load16: addr16(inst); e_.mem(OP_I32_LOAD16_U, 0, base_);")
cpp = rep(cpp, "case IROp::Load16Ext: addr(inst); e_.mem(OP_I32_LOAD16_S, 0, base_);", "case IROp::Load16Ext: addr16(inst); e_.mem(OP_I32_LOAD16_S, 0, base_);")
cpp = rep(cpp, "case IROp::Store16: storeAddr(inst); get(SR(inst.src3));", "case IROp::Store16: addr16(inst); e_.set(L_I3); Journal(L_I3); e_.get(L_I3); get(SR(inst.src3));")

# Operações que saíram ou mudaram no interpretador atual.
cpp = drop_case(cpp, "		case IROp::Vec4Dot:\n", "		case IROp::Vec2Unpack16To31:\n")
cpp = drop_case(cpp, "		case IROp::Vec2ClampToZero:\n", "		case IROp::FCmpVfpuBit:\n")
cpp = drop_case(cpp, "		case IROp::FRSqrt: F32Const", "		case IROp::ShlImm:")
cpp = drop_case(cpp, "		case IROp::FMin:\n		case IROp::FMax:\n", "		case IROp::FMov:")
cpp = rep(cpp, """			get(SF(inst.src1)); e_.i32c(15); e_.op(OP_I32_SHR_U); e_.i32c(0xFFFF); e_.op(OP_I32_AND);
			get(SF(inst.src1 + 1)); e_.i32c(1); e_.op(OP_I32_SHL); e_.i32c(0xFFFF0000); e_.op(OP_I32_AND);
""", """			clampedLane(SF(inst.src1)); e_.i32c(15); e_.op(OP_I32_SHR_U); e_.i32c(0xFFFF); e_.op(OP_I32_AND);
			clampedLane(SF(inst.src1 + 1)); e_.i32c(1); e_.op(OP_I32_SHL); e_.i32c(0xFFFF0000); e_.op(OP_I32_AND);
""")
cpp = rep(cpp, """			get(SF(inst.src1)); e_.i32c(23); e_.op(OP_I32_SHR_U); e_.i32c(0xFF); e_.op(OP_I32_AND);
			get(SF(inst.src1 + 1)); e_.i32c(15); e_.op(OP_I32_SHR_U); e_.i32c(0xFF00); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
			get(SF(inst.src1 + 2)); e_.i32c(7); e_.op(OP_I32_SHR_U); e_.i32c(0xFF0000); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
			get(SF(inst.src1 + 3)); e_.i32c(1); e_.op(OP_I32_SHL); e_.i32c(0xFF000000); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
""", """			clampedLane(SF(inst.src1)); e_.i32c(23); e_.op(OP_I32_SHR_U); e_.i32c(0xFF); e_.op(OP_I32_AND);
			clampedLane(SF(inst.src1 + 1)); e_.i32c(15); e_.op(OP_I32_SHR_U); e_.i32c(0xFF00); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
			clampedLane(SF(inst.src1 + 2)); e_.i32c(7); e_.op(OP_I32_SHR_U); e_.i32c(0xFF0000); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
			clampedLane(SF(inst.src1 + 3)); e_.i32c(1); e_.op(OP_I32_SHL); e_.i32c(0xFF000000); e_.op(OP_I32_AND); e_.op(OP_I32_OR);
""")
# Div: no único estouro, o resto fica em zero (cpu/cpu_alu/cpu_div).
cpp = rep(cpp, """				e_.i32c(0x80000000); put(S_LO);
				e_.i32c(0xFFFFFFFF); put(S_HI);
""", """				e_.i32c(0x80000000); put(S_LO);
				e_.i32c(0); put(S_HI);
""")
# sqrt.s de negativo dá NaN positivo.
cpp = rep(cpp, "		case IROp::FSqrt: unF(inst, OP_F32_SQRT); return true;\n", """		case IROp::FSqrt:
			get(SF(inst.src1)); e_.set(L_I0);
			e_.i32c(0x7FC00000);
			e_.get(L_I0); e_.op(OP_F32_REINTERPRET_I32); e_.op(OP_F32_SQRT); e_.op(OP_I32_REINTERPRET_F32);
			e_.get(L_I0); e_.op(OP_F32_REINTERPRET_I32); F32Const(0.0f); e_.op(OP_F32_LT);
			e_.op(OP_SELECT);
			put(SF(inst.dest));
			return true;
""")
# FSign: denormais dão zero.
cpp = rep(cpp, """			// val == 0 || val == 0x80000000 ? 0 : (val >> 31 ? -1 : 1)
""", """			// (val & 0x7F800000) == 0 ? 0 : (val >> 31 ? -1 : 1)
""")
cpp = rep(cpp, """			e_.i32c(0);
			e_.get(L_I0); e_.i32c(0x7FFFFFFF); e_.op(OP_I32_AND);
			e_.op(OP_SELECT);
			put(SF(inst.dest));""", """			e_.i32c(0);
			e_.get(L_I0); e_.i32c(0x7F800000); e_.op(OP_I32_AND);
			e_.op(OP_SELECT);
			put(SF(inst.dest));""")
# O registrador do FpCondFromReg agora vem em src1.
cpp = rep(cpp, "case IROp::FpCondFromReg: get(SR(inst.dest)); put(S_FPCOND); return true;", "case IROp::FpCondFromReg: get(SR(inst.src1)); put(S_FPCOND); return true;")
# As saídas fundidas: o ExitToConst seguinte, que continua no bloco, é o alvo do outro caminho.
cpp = rep(cpp, "		case IROp::ExitToConstIfEq: exitIf(inst, OP_I32_EQ, false); return true;\n", """		case IROp::OptExitToConstIfEqElse: exitIf(inst, OP_I32_EQ, false); return true;
		case IROp::OptExitToConstIfNeqElse: exitIf(inst, OP_I32_NE, false); return true;
		case IROp::OptExitToConstIfGtZElse: exitIf(inst, OP_I32_GT_S, true); return true;
		case IROp::OptExitToConstIfGeZElse: exitIf(inst, OP_I32_GE_S, true); return true;
		case IROp::OptExitToConstIfLtZElse: exitIf(inst, OP_I32_LT_S, true); return true;
		case IROp::OptExitToConstIfLeZElse: exitIf(inst, OP_I32_LE_S, true); return true;
		case IROp::ExitToConstIfEq: exitIf(inst, OP_I32_EQ, false); return true;
""")
cpp = rep(cpp, "		case IROp::UpdateRoundingMode: return true;\n", "		case IROp::UpdateRoundingMode: return true;\n		case IROp::Nop: return true;\n")

# ---- Medição: tempo da CPU emulada e operações que passam pelo interpretador ----
hdr = rep(hdr, "	static int stats[8];\n", "	static int stats[8];\n	static double cpuMs;\n	static int runs;\n")
hdr = rep(hdr, '#include "Common/CommonTypes.h"\n', '#include "Common/CommonTypes.h"\n\nextern "C" double emscripten_get_now(void);\n')
hdr = rep(hdr, "class IRWasmJit {\npublic:", """// Time spent running the emulated CPU, for emuflow_wasmjit_cpu_ms.
struct IRWasmCpuTimer {
	double start = emscripten_get_now();
	~IRWasmCpuTimer();
};

class IRWasmJit {
public:""")
cpp = rep(cpp, "int IRWasmJit::stats[8];\n", """int IRWasmJit::stats[8];
double IRWasmJit::cpuMs = 0.0;
int IRWasmJit::runs = 0;
static int g_opCounts[256];
IRWasmCpuTimer::~IRWasmCpuTimer() { IRWasmJit::cpuMs += emscripten_get_now() - start; }
""")
cpp = rep(cpp, "void RunOneOp(MIPSState *mips, const IRInst *inst) {\n", "void RunOneOp(MIPSState *mips, const IRInst *inst) {\n	g_opCounts[(int)inst->op]++;\n")
# g_opCounts é usado dentro do namespace anônimo, então a declaração sobe para antes dele.
cpp = rep(cpp, "static int g_opCounts[256];\n", "")
cpp = rep(cpp, "namespace MIPSComp {\n", "namespace MIPSComp {\n\nstatic int g_opCounts[256];\n")
cpp = rep(cpp, "u32 IRWasmJit::Run(int func, MIPSState *mips, const IRInst *arena, u32 offset) {\n", "u32 IRWasmJit::Run(int func, MIPSState *mips, const IRInst *arena, u32 offset) {\n	runs++;\n")
cpp = rep(cpp, '#endif\n', '''extern "C" EMSCRIPTEN_KEEPALIVE double emuflow_wasmjit_cpu_ms() { return MIPSComp::IRWasmJit::cpuMs; }
extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_runs() { return MIPSComp::IRWasmJit::runs; }
extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_op_count(int op) { return op >= 0 && op < 256 ? MIPSComp::g_opCounts[op] : 0; }

#endif
''', 0) if False else cpp
i = cpp.rindex("#endif")
cpp = cpp[:i] + '''extern "C" EMSCRIPTEN_KEEPALIVE double emuflow_wasmjit_cpu_ms() { return MIPSComp::IRWasmJit::cpuMs; }
extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_runs() { return MIPSComp::IRWasmJit::runs; }
extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_op_count(int op) { return op >= 0 && op < 256 ? MIPSComp::g_opCounts[op] : 0; }

''' + cpp[i:]

# ---- Ciclo de vida ----
cpp = rep(cpp, """void IRWasmJit::BeginSlice(IRBlockCache &blocks) {""", """void IRWasmJit::BeginSlice(JitBlockTable &blocks, const IRInst *arena, size_t arenaSize, MIPSState *mips) {""")
cpp = rep(cpp, "	size_t arenaSize = blocks.GetArenaSize();\n", "")
# O modo vem de outra thread: vale do início ao fim da fatia. O código da verificação grava num diário que só o Run
# de verificação esvazia, então não pode rodar por um Run normal.
hdr = rep(hdr, "	int lastMode_ = -1;\n", "	int lastMode_ = -1;\n	int sliceMode_ = 0;\n")
cpp = rep(cpp, """	if (mode != lastMode_) {
		// Switching modes (or the first slice): start from a clean slate.
		lastMode_ = mode;
		Reset();
	}
	if (mode == 0)
		return;
""", """	sliceMode_ = mode;
	if (sliceMode_ != lastMode_) {
		// Switching modes (or the first slice): start from a clean slate.
		lastMode_ = sliceMode_;
		Reset();
	}
	if (sliceMode_ == 0)
		return;
""")
cpp = rep(cpp, "const uint32_t journal = mode == 2 ? (uint32_t)(uintptr_t)g_journal : 0;", "const uint32_t journal = sliceMode_ == 2 ? (uint32_t)(uintptr_t)g_journal : 0;")
cpp = rep(cpp, "	if (mode == 1) {\n		resolver =", "	if (sliceMode_ == 1) {\n		resolver =")
cpp = rep(cpp, "	if (mode != 2)\n		return ((IRWasmBlockFunc)(uintptr_t)func)(mips, arena);", "	if (sliceMode_ != 2)\n		return ((IRWasmBlockFunc)(uintptr_t)func)(mips, arena);")
cpp = rep(cpp, "		Flush(blocks);\n}", "		Flush(blocks, arena, mips);\n}") if False else cpp
cpp = rep(cpp, "if (pending_.size() >= 64 || (!pending_.empty() && slicesSinceFlush_ > 100))\n		Flush(blocks);", "if (pending_.size() >= 64 || (!pending_.empty() && slicesSinceFlush_ > 100))\n		Flush(blocks, arena, mips);")
cpp = rep(cpp, """void IRWasmJit::Flush(IRBlockCache &blocks) {
	slicesSinceFlush_ = 0;
	const IRInst *arena = blocks.GetArenaPtr();
	const uint32_t memBase = (uint32_t)(uintptr_t)Memory::base;
""", """void IRWasmJit::Flush(JitBlockTable &blocks, const IRInst *arena, MIPSState *mips) {
	slicesSinceFlush_ = 0;
	const Memory::AddressSpace &space = *mips->space;
	const uint32_t memBase = (uint32_t)(uintptr_t)space.base;
""")
cpp = rep(cpp, """		int blockNum = blocks.GetBlockNumFromIRArenaOffset((int)offset);
		const IRBlock *block = blocks.GetBlock(blockNum);
""", """		int blockNum = blocks.FindByEntry((int)offset);
		const JitBlock *block = blocks.GetBlock(blockNum);
""")
cpp = rep(cpp, "BlockCompiler bc(fn, memBase, interpIdx, journal, BlockCompiler::LinkResolver());", "BlockCompiler bc(fn, space, memBase, interpIdx, journal, BlockCompiler::LinkResolver());")
cpp = rep(cpp, "BlockCompiler bc(fn, memBase, interpIdx, journal, resolver);", "BlockCompiler bc(fn, space, memBase, interpIdx, journal, resolver);")
cpp = rep(cpp, """			u32 w = Memory::ReadUnchecked_U32(target);
			if ((w & 0xFF000000) != MIPS_EMUHACK_OPCODE)
				return 0;
			u32 off = w & 0x00FFFFFF;
""", """			u32 w = *space.GetBlockShadowEntry(target);
			if (w <= Memory::BLOCK_SHADOW_HOOK_NO_JIT)
				return 0;
			u32 off = w;
""")
cpp = rep(cpp, """		Emitter s;  // type 0: (i32, i32) -> i32, same as IRInterpret
		s.uleb(1); s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_I32);
""", """		Emitter s;  // See TYPE_BLOCK and the others.
		s.uleb(4);
		s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_I32);
		s.u8(0x60); s.uleb(3); s.u8(T_I32); s.u8(T_I32); s.u8(T_I32); s.uleb(1); s.u8(T_I32);
		s.u8(0x60); s.uleb(2); s.u8(T_I32); s.u8(T_I32); s.uleb(0);
		s.u8(0x60); s.uleb(1); s.u8(T_I32); s.uleb(1); s.u8(T_I32);
""")
# Se o navegador não aceitar o módulo, tudo volta ao interpretador, em vez de tentar a cada lote.
cpp = rep(cpp, """	if (!irwasm_install(mod.b.data(), (int)mod.b.size(), slots.data(), (int)n)) {
		stats[2]++;
""", """	if (!irwasm_install(mod.b.data(), (int)mod.b.size(), slots.data(), (int)n)) {
		stats[2]++;
		mode = 0;
""")
cpp = rep(cpp, 'extern "C" __attribute__((used)) void ejs_wasmjit_mode(int m) {', 'extern "C" EMSCRIPTEN_KEEPALIVE void emuflow_wasmjit_mode(int m) {')
cpp = rep(cpp, 'extern "C" __attribute__((used)) int ejs_wasmjit_stat(int i) {', 'extern "C" EMSCRIPTEN_KEEPALIVE int emuflow_wasmjit_stat(int i) {')

# Saídas encadeadas, operações sem efeito no wasm e produto escalar direto.
sys.path.insert(0, "/tmp")
import port_opt
cpp, hdr = port_opt.apply(cpp, hdr, rep)

open(PP + "Core/MIPS/IR/IRWasmJit.cpp", "w", encoding="utf8", newline="\n").write(cpp)
open(PP + "Core/MIPS/IR/IRWasmJit.h", "w", encoding="utf8", newline="\n").write(hdr)

# ---- Ligação ao despacho ----
p = PP + "Core/MIPS/IR/IRJit.h"
s = open(p, encoding="utf8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
s = s.replace("\r\n", "\n")
s = rep(s, '#include "Core/MIPS/JitCommon/JitBlockCache.h"\n', '#include "Core/MIPS/JitCommon/JitBlockCache.h"\n#include "Core/MIPS/IR/IRWasmJit.h"\n')
s = rep(s, "	// The blocks' IR. Offsets 0 and 1 are reserved, see RunBlocks.\n	std::vector<IRInst> arena_;\n",
        "	// The blocks' IR. Offsets 0 and 1 are reserved, see RunBlocks.\n	std::vector<IRInst> arena_;\n#ifdef __EMSCRIPTEN__\n	IRWasmJit wasmJit_;\n#endif\n")
open(p, "w", encoding="utf8", newline="").write(s.replace("\n", nl))

p = PP + "Core/MIPS/IR/IRJit.cpp"
s = open(p, encoding="utf8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
s = s.replace("\r\n", "\n")
s = rep(s, """	IRJit::ClearCache();
	arena_.clear();
""", """	IRJit::ClearCache();
#ifdef __EMSCRIPTEN__
	wasmJit_.Reset();
#endif
	arena_.clear();
""")
s = rep(s, """	MIPSState *mips = mips_;
	while (mips->downcount >= 0) {
		// The block's offset into the IR arena""", """	MIPSState *mips = mips_;
#ifdef __EMSCRIPTEN__
	// The Media Engine has its own memory, and the compiled code is tied to the main CPU's.
	const IRWasmCpuTimer cpuTimer;
	const bool useWasm = !profile && IRWasmJit::mode != 0 && !mips->IsMediaEngine();
	if (useWasm)
		wasmJit_.BeginSlice(blocks_, arena_.data(), arena_.size(), mips);
#endif
	while (mips->downcount >= 0) {
		// The block's offset into the IR arena""")
# Com o JIT, o interpretador não encadeia: cada bloco volta ao despacho, senão um bloco frio levaria toda a fatia.
s = rep(s, """				mips->pc = IRInterpret(mips, instPtr, arena_.data());
""", """#ifdef __EMSCRIPTEN__
				mips->pc = IRInterpret(mips, instPtr, useWasm ? nullptr : arena_.data());
#else
				mips->pc = IRInterpret(mips, instPtr, arena_.data());
#endif
""")
s = rep(s, """			const IRInst *instPtr = arena_.data() + offset;
			// First op is always, except when using breakpoints, downcount""", """#ifdef __EMSCRIPTEN__
			const int wasmFunc = useWasm ? wasmJit_.Lookup(offset) : 0;
			if (wasmFunc > 0) {
				const int entryPC = mips->pc;
				mips->pc = wasmJit_.Run(wasmFunc, mips, arena_.data(), offset);
				if (!mips->space->IsValid4AlignedAddress(mips->pc)) {
					Core_ExecException(mips->pc, entryPC, ExecExceptionType::JUMP);
					return;
				}
				continue;
			}
#endif
			const IRInst *instPtr = arena_.data() + offset;
			// First op is always, except when using breakpoints, downcount""")
open(p, "w", encoding="utf8", newline="").write(s.replace("\n", nl))

p = PP + "libretro/Makefile.common"
s = open(p, encoding="utf8", newline="").read()
if "IRWasmJit.cpp" not in s:
    s = rep(s, "$(COREDIR)/MIPS/IR/IRInterpreter.cpp \\", "$(COREDIR)/MIPS/IR/IRInterpreter.cpp \\\n	       $(COREDIR)/MIPS/IR/IRWasmJit.cpp \\")
    open(p, "w", encoding="utf8", newline="").write(s)
print("portado")
