Original synthetic EPUB/crypto vectors, MIT, EXReader contributors.

Regenerate with `tools/generate_lcp_fixtures.py` and the **public test**
certificate/private key from Readium's LCP server test/cert directory.
Python cryptography supplies AES and RSA independently of the SDK's Mbed TLS.
The public test certificate is embedded in the generated license documents;
the private key is neither embedded in the EPUBs nor linked into the SDK.

Passphrase: `LCP café 口令`. `clear.epub` is the original resource comparison.
`normal.epub` uses arbitrary XML Encryption pad octets, both compression
methods, an empty compressed resource, an escaped path and JSON Unicode escapes.
The other vectors exercise the named error cases. `adept-marker.epub` is only
a detection fixture, **not** an Adobe ADEPT interoperability sample.
SHA-256 values are listed in `sha256.json`. CTest needs no download or Python
crypto dependency. Public EDRLab interoperability is tested separately by
`tests/lcp_acceptance.py`; see `docs/DRM.md` for results and trust boundaries.
