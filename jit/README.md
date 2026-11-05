# JIT de IR para WebAssembly (fora do core publicado)

Porte do `IRWasmJit` de [xandps/ppsspp-wasm](https://github.com/xandps/ppsspp-wasm) (GPL, commit `aa60f45`) para o PPSSPP
de `versions.env`. Fica aqui como experimento: **perdeu do interpretador** nas medições (decisão D100 da documentação do
EmuFlow), então o core do site não o usa.

- `port.py`, `port_opt.py`: aplicam o porte a partir do clone em `/work/xandps` (`git clone --depth 1` do repositório acima).
- `port_rtc.py`: a correção da espera ativa em `sceRtcGetCurrentTick`, que **está** no core publicado (e no patch).
- `port_remote.py`: a leitura do disco sob demanda, que também **está** no core publicado (e no patch).
- `../variant-jit.sh`: deixa o volume com o JIT. Depois: `run.sh build-core.sh` e `run.sh link.sh <nome> minasync jit`.
- `../variant-final.sh`: levou a leitura sob demanda ao histórico do volume e gerou o patch. Já rodou; para voltar ao código publicado depois de `variant-jit.sh`, desfaça os arquivos do JIT com `git checkout`.

Controles no console, com o core do JIT: `Module._emuflow_wasmjit_mode(0|1|2|3)` (desligado, ligado, verificando contra o
interpretador, sem encadeamento), `_emuflow_wasmjit_threshold(n)`, `_emuflow_wasmjit_stat(i)` e a tabela de tempo por chamada
de sistema (`_emuflow_wasmjit_sys_*`), que foi o que achou a espera ativa.
