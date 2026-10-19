# Original PDF security fixtures

Regenerate from the repository root with:

```text
python tools/generate_pdf_crypto_fixtures.py
```

Generated with pypdf 6.16.1 and cryptography 50.0.2. These are development
dependencies, not SDK or test-run dependencies. All text, graphics and metadata
are original test content (MIT); no third-party PDF is bundled.
The generator deliberately replaces entropy with a deterministic sequence only
while creating fixtures. Never use that sequence to encrypt real documents.

Ordinary user password: `reader`. Owner password: `owner`. `*-empty` has an
empty user password. R6 Unicode user: `I\u00adX\u2168\u00aa\u00a0\u1100\u1161\u11a8\u00e9`
(Python escape notation); normalized: `IXIXa 각é`. Unicode owner: `اب`.
`r6-long` uses 140 ASCII `x` characters, truncated to 127 per the PDF algorithm.

R2/R3 exercise RC4; R4 AES-128; R5/R6 AES-256. Cases cover object generation
17, encrypted object streams and unencrypted xref streams, raw and compressed
content, encrypted and clear XMP, string/stream Identity, explicit Crypt,
unencrypted signature Contents in direct nested dictionaries (with and without
Type), and incremental revision inheritance with a changed second document ID.
Page 0 includes green vector graphics and invisible selectable text. Page 1 is
deliberately invalid to test lazy reader recovery using a retained derived key.
Malformed cases include altered permissions, AES padding and unsupported PubSec.
