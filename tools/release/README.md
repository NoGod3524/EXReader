# Release integrity and reproducible builds

Requires Python 3.9+, CMake, and the selected compiler. The scripts use the
Python standard library. Measured results, both hash sets and regression reports:
[C4 evidence](../../evidence/artifact-signing-20261109/README.md).

## Checksums and publication order

1. Build and compare **unsigned** outputs. Authenticode timestamps and detached
   signatures are created after this comparison and are not reproducible inputs.
2. If a certificate is available, Authenticode-sign staged DLL/EXE files, verify
   them, then create the package. Record the final signed bytes in the checksums.
3. Put every downloadable DLL/package, `build_manifest.json`, and the public key
   (if distributing one) into a dedicated release directory.
4. Generate, verify and sign the checksum list. Upload the entire directory with
   the release. Paste the `SHA256SUMS` contents into the release page as well.

```sh
python tools/release/verify_artifacts.py dist/release --write
python tools/release/verify_artifacts.py dist/release
python tools/release/sign_artifacts.py dist/release --dry-run
python tools/release/sign_artifacts.py dist/release --key GPG_KEY_FINGERPRINT
```

The format is GNU-compatible `SHA256  relative/filename`, UTF-8, LF, sorted.
Verification checks **every file**, rejects missing/unlisted/changed files,
duplicate/case-alias entries, unsafe paths and links. Only the root `SHA256SUMS`
and its `.asc`/`.minisig` detached signatures are excluded. Signature files are
verified separately; checksum success alone does not authenticate the publisher.
Regeneration refuses existing detached signatures to avoid silently keeping a
signature for old bytes. Use a new release directory for a new publication.

`tools/reading_release.py` automatically adds checksums beside each candidate
archive and its metadata. `tools/prepare_reading_release.py` includes all six
archives and `plan.json` in the final list. No workflow has been changed here.
The [workflow fragment](workflow-snippet.yml) shows manifest/signature/upload
steps for adoption in CI; it does not dispatch a workflow or publish a release.

## Signing and verifying the publisher

Auto selection uses GPG (including Git for Windows' bundled copy), then minisign,
then explicit `UNSIGNED` SHA256 publication. If a tool exists but its release key
is unavailable, real signing fails; it never picks a user's default private key.
Use `--backend sha256` to deliberately publish hashes without a signature.
The script converts paths through Git's `cygpath` for its MSYS GPG; native Gpg4win
uses ordinary Windows paths. `--gpg-homedir` selects an isolated test keyring.

```sh
python tools/release/sign_artifacts.py dist/release --backend gpg --key GPG_KEY_FINGERPRINT
gpg --batch --verify dist/release/SHA256SUMS.asc dist/release/SHA256SUMS
python tools/release/verify_artifacts.py dist/release

python tools/release/sign_artifacts.py dist/release --backend minisign --key /secure/release.key
minisign -Vm dist/release/SHA256SUMS -P TRUSTED_MINISIGN_PUBLIC_KEY
python tools/release/verify_artifacts.py dist/release

python tools/release/sign_artifacts.py dist/release --backend sha256
```

Publish the expected GPG fingerprint/minisign public key through an independently
trusted project channel. For GPG, import the release public key and compare its
full fingerprint with that trusted value; a “Good signature” from an arbitrary
downloaded key is insufficient. Keep private keys out of the repository and
release assets. Test-only keys used in C4 evidence are not publisher identities.

Windows Authenticode **需要 EV/OV 证书** and access to its private key (certificate
store/token/HSM). Without one, this task supplies executable dry-run templates:

```sh
python tools/release/sign_artifacts.py stage --backend authenticode --dry-run
signtool sign /sha1 EV_OR_OV_CERTIFICATE_THUMBPRINT /fd SHA256 /tr RFC3161_TIMESTAMP_URL /td SHA256 stage/bin/exreader.dll
signtool verify /pa /all /v stage/bin/exreader.dll
```

For a real signing run, pass `--key CERTIFICATE_THUMBPRINT --timestamp-url URL`
and ensure the Windows SDK's `signtool` is on PATH. No certificate, signing key,
or timestamp response is fabricated by dry-run. SHA256-only publication detects
corruption when checked against a trusted published hash; it supplies no private
key proof of origin.

Command references: [Microsoft SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool),
[GPG detached signatures](https://gnupg.org/documentation/manuals/gnupg/Operational-GPG-Commands.html),
[minisign](https://jedisct1.github.io/minisign/).

## Freeze and reproduce a build

Configure a Release build with `-DEXR_REPRODUCIBLE=ON`, recording the exact CMake
argument array in a JSON file outside the source inputs (for example
`build/configure-args.json`). Retain all feature options and dependency overrides.
For MinGW this disables PE timestamps, uses `ar`/`ranlib` deterministic mode for
static libraries and `objcopy --enable-deterministic-archives` for DLL import
libraries. For MSVC it selects `/Brepro` and disables
incremental linking. The checked-in measurement is **MinGW on this Windows
machine**; MSVC, another machine, different build paths and signed bytes are
outside that measurement.

```sh
python tools/release/build_manifest.py --build-dir build/sdk --configure-args build/configure-args.json
python tools/release/build_manifest.py --check tools/release/build_manifest.json
python tools/release/reproduce.py --manifest tools/release/build_manifest.json --output build/repro-proof --jobs 4
```

`build_manifest.json` records source revision/tree plus working-tree override
hashes, an actual source fingerprint, compiler identity/version/binary hash,
CMake version/binary hash, Ninja/linker/archiver hashes, host and Python versions,
the full CMake cache, configure arguments, relevant environment, generated input
hashes, and each populated dependency's URL/tag or commit/archive hash **and
actual source-tree hash**. A local source override is not claimed to have been
validated by the upstream archive hash. Expat, FreeType and miniz are mandatory.
Feature-off dependencies are not silently treated as built features; consult
the recorded `EXR_*` cache values for the measured configuration.

Tree fingerprints sort relative paths and hash `8-byte big-endian UTF-8 path
length + path + raw file SHA256` for every file. Dependency/generated trees omit
`.git`, `__pycache__` and directories starting with `build`. Source inputs use
Git's tracked and unignored files; the manifest records exclusions for output
evidence, archives, workflows, itself and root progress logs. Source revision
and override hashes identify the input snapshot; the content fingerprint remains
valid when the same bytes are committed. Absolute paths are deliberate: this is
a same-machine, same-path test, not a relocatable or hermetic toolchain image.

The reproducer checks frozen inputs before/after each run, invokes CMake
`--clean-first` twice (all objects/libraries relinked), installs to separate empty
stages, embeds the same manifest and internal checksum list, and creates sorted
tar/gzip packages with fixed timestamps, ownership and gzip filename. It verifies
every stage/output file and fails if either installed files or release artifact
hashes differ. The two `run-N.json`, build/install logs, `SHA256SUMS` lists and
`reproducibility.json` are retained. Use a new `--output` directory each time.

To reconfigure the same paths from the recorded recipe, run the manifest's
`cmake.path` with `build.configure_arguments`, using `source.directory` as the
working directory. Restore the recorded toolchain, source contents, dependency
trees and environment before `--check`; recapture for a different configuration.
