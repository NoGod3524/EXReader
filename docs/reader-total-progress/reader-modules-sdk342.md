# Installed reader modules and transaction SDK candidate

Source `ef206652e556fa120e1302ecb9b1a2082335e02e`,
[Actions 40641881557/1](https://github.com/NoGod3524/EXReader/actions/runs/40641881557),
completed successfully on Ubuntu 22.04 and Windows 2022.

The job verified that the SDK source tree matches transaction candidate
`8357eafa28423a7ab93ba08b823af80f01ad1505`, built and installed SDK
3.42.0, and built and installed these eleven packages against that exact SDK:

batch import, book information, cloud import, font library, local downloads,
navigation, original export, reading state, search, thumbnails and TXT
progress. The default module selection remains SDK 3.40.0; 3.42.0 must be
selected explicitly. The SDK dependency in installed package configs remains
exact. Both platforms compiled and ran the independent installed C search and
navigation consumers and refused unsupported SDK 3.43.0.

Artifacts, run 40641881557 attempt 1:

- Linux: 12795469209, 80,169 bytes, SHA-256
  `2670c6d320d5555840bcaf5a292dd1b2a60eaf4dbadc831c446c8f0f72eb0af4`.
- Windows: 12795368523, 80,962 bytes, SHA-256
  `8bad90d3b9faddef4afe1a41cbf0a7a943bfd662551857d64e41ce1025d127a2`.

This result uses the default legacy selector family. Raw-selector TXT
progress is separately being exercised in
[Actions 40642363736](https://github.com/NoGod3524/EXReader/actions/runs/40642363736)
on `4dd7f76142915d6ae27fe956f71e7f50b5235666`, pending its result.
Neither run validates an integrated host, migration compatibility, or the
whole reader. The original migration candidate gate remains failed on Linux
and Windows, with macOS queued. This evidence-only commit is not the tested
source.
