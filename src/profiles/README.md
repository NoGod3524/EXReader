# Default CMYK ICC profile

`default_cmyk.icc.zlib` contains Graeme Gill's public-domain Argyll fallback CMYK
profile with the shared characterization text omitted. The transform tables,
white and black points, and all other retained tags are byte-identical to the
original. ICC-enabled SDKs install the original notice from
`licenses/default-cmyk-profile.txt`.

- Source: https://raw.githubusercontent.com/imbo/imbo/main/data/profiles/argyllcms_cmyk.icm
- Notice: https://raw.githubusercontent.com/imbo/imbo/main/data/profiles/argyllcms_cmyk.LICENSE
- Original: 961,644 bytes; SHA-256 `156e7c14f244cfc4ed83a755ca4803d80e15dd249b40fae82cb127d3902e15c7`
- Embedded profile: 227,488 bytes; SHA-256 `85492c07a7125ea25a2478121bdd0bb2149def88fd9372df1b841bd95521fd18`
- Compressed: 170,094 bytes; SHA-256 `8f37c1dc8cb6f112eb3909e1d630c37cb2262482b3b0ced8bc035b357e892642`
- Notice SHA-256: `45d3e9b11893bcae1724cd0e6d377c2ed842269de495307ba6153e1b0b80e1da`

Reproduce from the pinned original profile. The three removed tags share one
trailing text block. All retained tag offsets stay the same.

```python
from pathlib import Path
import hashlib, struct, zlib
raw = Path('argyllcms_cmyk.icm').read_bytes()
assert hashlib.sha256(raw).hexdigest() == '156e7c14f244cfc4ed83a755ca4803d80e15dd249b40fae82cb127d3902e15c7'
count, = struct.unpack_from('>I', raw, 128)
tags = list(struct.iter_unpack('>4sII', raw[132:132 + 12 * count]))
removed = {b'targ', b'DevD', b'CIED'}
offsets = {offset for name, offset, _ in tags if name in removed}
assert len(offsets) == 1
end = offsets.pop()
kept = [entry for entry in tags if entry[0] not in removed]
assert all(offset + size <= end for _, offset, size in kept)
profile = bytearray(raw[:end])
struct.pack_into('>I', profile, 0, end)
struct.pack_into('>I', profile, 128, len(kept))
profile[132:132 + 12 * count] = (
    b''.join(struct.pack('>4sII', *entry) for entry in kept) + bytes(12 * (count - len(kept)))
)
assert hashlib.sha256(profile).hexdigest() == '85492c07a7125ea25a2478121bdd0bb2149def88fd9372df1b841bd95521fd18'
packed = zlib.compress(profile, 9)
assert hashlib.sha256(packed).hexdigest() == '8f37c1dc8cb6f112eb3909e1d630c37cb2262482b3b0ced8bc035b357e892642'
Path('src/profiles/default_cmyk.icc.zlib').write_bytes(packed)
```

CMake verifies the compressed hash and creates the private C array without a Python
build dependency. `EXR_ENABLE_ICC=OFF` excludes both LittleCMS and this payload.
ICC-enabled contexts create four forward rendering intents and a relative inverse
transform on first CMYK use. The raw decompressed data are then freed. Transforms
are owned by each context, not a mutable global cache. The 16 MiB ICC allocation
ceiling applies per context; canvas memory reporting includes its retained transform.
The temporary decompression buffer is 227,488 bytes.

This fallback differs from SWOP profiles used by other readers. Comparisons must
use the same profile or identify profile differences separately. It is not a
substitute for a document OutputIntent or a complete print-color implementation.
