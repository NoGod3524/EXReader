# EXReaderTTSApple

Optional, independent Apple speech module for EXReader. It implements the frozen
common C ABI in [`docs/handoffs/reader-next-wave/tts-contract.md`](../../docs/handoffs/reader-next-wave/tts-contract.md)
on top of AVFoundation `AVSpeechSynthesizer` and cannot be enabled by accident:
nothing in the reading core, library, or hosts references it.

```
cmake -S extras/reader-tts-apple -B build/tts-apple -DCMAKE_BUILD_TYPE=Release
cmake --build build/tts-apple
cmake --install build/tts-apple --prefix <prefix>
# consumer
find_package(EXReaderTTSApple 0.1.0 CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderTTSApple::reader_tts)
```

Files: `include/reader_tts.h` (installed, frozen ABI), `src/core.cpp` (state
machine), `src/apple_engine.mm` (AVFoundation backend), `examples/` (an
installed-package consumer). Behaviour, thread rules, limits, and uncovered
scope are documented in [`docs/READER-TTS-APPLE.md`](../../docs/READER-TTS-APPLE.md).

Nothing here downloads a voice, calls a cloud service, reads a book, or keeps an
SDK handle. All builds and probes run in GitHub Actions.
