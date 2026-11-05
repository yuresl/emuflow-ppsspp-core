#!/usr/bin/env python3
# Leitura do disco sob demanda: o core pede os bytes a um worker do navegador, em vez de ter a ISO inteira na memória.
LOADER_H = '''// EmuFlow: o disco do PSP lido sob demanda pelo worker rom-stream.js, sem a ISO inteira na memória do navegador.
#pragma once

#ifdef __EMSCRIPTEN__

#include <mutex>

#include "Common/File/Path.h"
#include "Core/Loaders.h"

class RemoteFileLoader : public FileLoader {
public:
	RemoteFileLoader(const Path &path, s64 size) : path_(path), size_(size) {}

	bool Exists() override { return true; }
	bool IsDirectory() override { return false; }
	s64 FileSize() override { return size_; }
	Path GetPath() const override { return path_; }
	size_t ReadAt(s64 absolutePos, size_t bytes, size_t count, void *data, Flags flags = Flags::NONE) override;
	using FileLoader::ReadAt;

private:
	Path path_;
	s64 size_;
	std::mutex mutex_;
};

// O loader do disco, se o site pediu leitura sob demanda para este caminho.
FileLoader *ConstructRemoteFileLoader(const Path &path);

#endif
'''

LOADER_CPP = '''// EmuFlow: veja RemoteFileLoader.h. O pedido é uma palavra de estado e quatro de parâmetros na memória compartilhada; o
// worker responde na mesma memória. Esperar aqui não trava o worker, que continua baixando em segundo plano.

#ifdef __EMSCRIPTEN__

#include <cstring>
#include <string>
#include <emscripten/emscripten.h>
#include <emscripten/threading.h>
#include <emscripten/atomic.h>

#include "Common/Log.h"
#include "Core/FileLoaders/RemoteFileLoader.h"

namespace {

enum : int32_t { IDLE = 0, REQUEST = 1, DONE = 2 };

// A disposição é lida por rom-stream.js.
alignas(16) volatile int32_t g_control[8];  // estado, início (baixo, alto), bytes, destino, bytes lidos

std::string g_name;
s64 g_size = 0;

}  // namespace

EM_JS(void, rom_stream_start, (const char *url, double size, const char *cacheKey, int32_t *control), {
	var worker = new Worker(Module.emuflowRomScript);
	worker.postMessage({ memory: wasmMemory, url: UTF8ToString(url), size: size, cacheKey: UTF8ToString(cacheKey), control: control });
	Module.emuflowRomWorker = worker;
});

extern "C" EMSCRIPTEN_KEEPALIVE void emuflow_rom_stream(const char *name, const char *url, double size, const char *cacheKey) {
	g_name = name;
	g_size = (s64)size;
	// Sem nome: o worker não subiu, e o disco volta a ser lido do arquivo baixado.
	if (!g_name.empty())
		rom_stream_start(url, size, cacheKey, (int32_t *)g_control);
}

FileLoader *ConstructRemoteFileLoader(const Path &path) {
	if (g_name.empty() || path.GetFilename() != g_name)
		return nullptr;
	return new RemoteFileLoader(path, g_size);
}

size_t RemoteFileLoader::ReadAt(s64 absolutePos, size_t bytes, size_t count, void *data, Flags flags) {
	if (absolutePos >= size_ || bytes == 0 || count == 0)
		return 0;
	s64 total = (s64)bytes * (s64)count;
	if (absolutePos + total > size_)
		total = size_ - absolutePos;

	std::lock_guard<std::mutex> guard(mutex_);
	int32_t *control = (int32_t *)g_control;
	control[1] = (int32_t)(absolutePos & 0xFFFFFFFF);
	control[2] = (int32_t)(absolutePos >> 32);
	control[3] = (int32_t)total;
	control[4] = (int32_t)(intptr_t)data;
	control[5] = 0;
	emscripten_atomic_store_u32(&control[0], REQUEST);
	emscripten_futex_wake(&control[0], 1);
	while (emscripten_atomic_load_u32(&control[0]) != DONE)
		emscripten_futex_wait(&control[0], REQUEST, 1000.0);
	const int32_t read = control[5];
	emscripten_atomic_store_u32(&control[0], IDLE);
	return read < 0 ? 0 : (size_t)read / bytes;
}

#endif
'''

P = "/work/ppsspp/"
open(P + "Core/FileLoaders/RemoteFileLoader.h", "w", encoding="utf8", newline="\n").write(LOADER_H)
open(P + "Core/FileLoaders/RemoteFileLoader.cpp", "w", encoding="utf8", newline="\n").write(LOADER_CPP)


def patch(path, pairs):
    s = open(path, encoding="utf8", newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert a in s, a[:70]
        s = s.replace(a, b, 1)
    open(path, "w", encoding="utf8", newline="").write(s.replace("\n", nl))


patch(P + "Core/Loaders.cpp", [
    ('FileLoader *ConstructFileLoader(const Path &filename) {\n', 'FileLoader *ConstructFileLoader(const Path &filename) {\n#ifdef __EMSCRIPTEN__\n	if (FileLoader *remote = ConstructRemoteFileLoader(filename))\n		return remote;\n#endif\n'),
    ('#include "Core/Loaders.h"\n', '#include "Core/Loaders.h"\n#include "Core/FileLoaders/RemoteFileLoader.h"\n'),
])
patch(P + "libretro/Makefile.common", [
    ("$(COREDIR)/FileLoaders/LocalFileLoader.cpp \\", "$(COREDIR)/FileLoaders/LocalFileLoader.cpp \\\n	       $(COREDIR)/FileLoaders/RemoteFileLoader.cpp \\"),
])
print("remote ok")
