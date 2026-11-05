# Core de PSP do EmuFlow

Receita do core de PSP usado no [EmuFlow](https://emuflow.com.br): o [PPSSPP](https://github.com/hrydgard/ppsspp) oficial, com os patches desta pasta, ligado ao [RetroArch do EmulatorJS](https://github.com/EmulatorJS/RetroArch). O código é publicado para cumprir a licença do PPSSPP (GPL-2.0 ou posterior, em `LICENSE.TXT`). Os patches seguem a mesma licença.

## O que muda em relação ao oficial

| Patch | O que faz |
|---|---|
| `patches/emuflow-sobre-oficial.patch` | Ajustes para o navegador: disco lido sob demanda, sem despacho por tabela, espera ativa no relógio |
| `patches/emuflow-adhoc.patch` | Ad hoc por relay local, sem DNS nem tabela de rotas |
| `patches/aemu-postoffice-peek.patch` | `MSG_PEEK`, que o Emscripten ignora |
| `patches/emuflow-memstick.patch` | Memory Stick de 9 GB: com 16 GB, jogos antigos veem 0 livre |
| `patches/retroarch-audio-suave.patch` | Controle da taxa de áudio com o tom suavizado (RetroArch) |

`versions.env` fixa os commits usados.

## Como compilar

Precisa de Docker, com a imagem do `Dockerfile` e o volume `emuflow-ppsspp-work`:

```bash
docker build -t emuflow-ppsspp-build .
./run.sh fetch.sh
./run.sh build-core.sh
./run.sh link.sh <nome> minasync
./run.sh assets.sh <nome>
```

O resultado fica em `out/<nome>/`. Sem `minasync`, o core funciona, mas fica mais lento.

`jit/` e `variant-*.sh` registram testes que não entram no core publicado.
