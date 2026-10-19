# Default CMYK ICC profile

`default_cmyk.icc.zlib` contains the complete public-domain Argyll fallback CMYK
profile by Graeme Gill. It is not a sampled replacement LUT. The original notice
is retained in `licenses/default-cmyk-profile.txt` and installed with ICC-enabled SDKs.

- Source: https://raw.githubusercontent.com/imbo/imbo/main/data/profiles/argyllcms_cmyk.icm
- Notice: https://raw.githubusercontent.com/imbo/imbo/main/data/profiles/argyllcms_cmyk.LICENSE
- Original: 961,644 bytes; SHA-256 `156e7c14f244cfc4ed83a755ca4803d80e15dd249b40fae82cb127d3902e15c7`
- Compressed: 414,609 bytes; SHA-256 `20f63c910decd30bf87d7ce2461f133d0305f552279ccdc388cdcfc8762753b2`
- Notice SHA-256: `45d3e9b11893bcae1724cd0e6d377c2ed842269de495307ba6153e1b0b80e1da`

Reproduce from a downloaded original profile:

```python
from pathlib import Path
import hashlib, zlib
raw = Path('argyllcms_cmyk.icm').read_bytes()
assert hashlib.sha256(raw).hexdigest() == '156e7c14f244cfc4ed83a755ca4803d80e15dd249b40fae82cb127d3902e15c7'
packed = zlib.compress(raw, 9)
assert hashlib.sha256(packed).hexdigest() == '20f63c910decd30bf87d7ce2461f133d0305f552279ccdc388cdcfc8762753b2'
Path('src/profiles/default_cmyk.icc.zlib').write_bytes(packed)
```

CMake verifies the compressed hash and creates the private C array without a Python
build dependency. `EXR_ENABLE_ICC=OFF` excludes both LittleCMS and this payload.
ICC-enabled contexts create four forward rendering intents and a relative inverse
transform on first CMYK use. The raw decompressed data are then freed. Transforms
are owned by each context, not a mutable global cache. The 16 MiB ICC allocation
ceiling applies per context; canvas memory reporting includes its retained transform.
The temporary decompression buffer is 961,644 bytes.

This fallback differs from SWOP profiles used by other readers. Comparisons must
use the same profile or identify profile differences separately. It is not a
substitute for a document OutputIntent or a complete print-color implementation.
