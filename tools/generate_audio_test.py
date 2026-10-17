# SPDX-License-Identifier: GPL-3.0-only
"""Generate the original 400 Hz PCM host-example fixture using only stdlib."""
from pathlib import Path
import math
import struct
import wave
path = Path(__file__).resolve().parents[1] / "tests/fixtures/audio/pcm.wav"
path.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(path), "wb") as output:
    output.setparams((1, 2, 16000, 3200, "NONE", "not compressed"))
    output.writeframes(b"".join(struct.pack("<h", round(16384 * math.sin(2 * math.pi * 400 * i / 16000))) for i in range(3200)))
