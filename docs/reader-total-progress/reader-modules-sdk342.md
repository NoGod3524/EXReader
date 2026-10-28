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

The follow-up [Actions 40642363736/1](https://github.com/NoGod3524/EXReader/actions/runs/40642363736)
tested `4dd7f76142915d6ae27fe956f71e7f50b5235666`. Both platforms repeated
the installed-module checks and built an independently installed raw-selector
family. Its installed TXT progress consumer passed all 16 checks on each
platform, including capture, persistence, conflict and pending cases.
The 3.43 refusal remained in effect.

- Linux: 12795923936, 108,837 bytes, SHA-256
  `68e2367fa77d278b2fe577e1e532ed9488549fdd6a3eabd6a2beac308cabf53d`.
- Windows: 12795319332, 109,887 bytes, SHA-256
  `24b2da72ba9568db4d15de3e16858c2a458f4add7506217e03d5b047ff3c4848`.

Neither run validates an integrated host, migration compatibility, or the
whole reader. The original migration candidate gate remains failed on Linux
and Windows, with macOS queued. This evidence-only commit is not either
tested source.
