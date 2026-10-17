# Original audio fixtures

`pcm.wav` is an original short generated waveform, GPL-3.0-only,
copyright 2026 EXReader contributors. `metadata.m4b` encodes that waveform as AAC
and copies the original geometric JPEG from `pdf-images/baseline.jpg`; it adds
UTF-8 title/artist, a JPEG cover, Nero chpl and QuickTime chapter track metadata.
The metadata inspector currently reads chpl, independently of the AAC codec.

Regenerate with `python tools/generate_m4b_metadata_fixture.py` (development-only
FFmpeg). The committed 4009-byte fixture has SHA-256
`c92c42c2c195deb2b5c46ec743656ff19938730a9612846b40cf91cb121a3ffe`.
Encoder/container versions can change output bytes. FFprobe independently reports
0.200 seconds, chapters One [0,100) and Two [100,200) milliseconds, and the same
Unicode title/artist; native/JVM/Swift smoke tests consume the committed file.
