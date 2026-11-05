# Mesma versão do Emscripten do EmulatorJS/build (build_env.sh).
FROM emscripten/emsdk:3.1.74
RUN apt-get update && apt-get install -y --no-install-recommends p7zip-full zip jq pkg-config binutils-mips-linux-gnu git
ENV EM_CACHE=/work/.emcache
WORKDIR /work
