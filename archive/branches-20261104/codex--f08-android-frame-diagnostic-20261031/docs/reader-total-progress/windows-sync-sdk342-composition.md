# SDK 3.42 and Windows sync composition preparation

Source candidate `5b317d5281d6346e4148193d771d20dc116a8af8` combines:

- Reader modules and transaction SDK candidate tested at
  `4dd7f76142915d6ae27fe956f71e7f50b5235666`, Linux/Windows
  [40642363736/1](https://github.com/NoGod3524/EXReader/actions/runs/40642363736).
- Windows account source `42445abd6dfeb312c8803d0a000a32f2a0459a15`,
  whose 32 account checks were independently authenticated by
  [40643169696/1](https://github.com/NoGod3524/EXReader/actions/runs/40643169696).
  Its remaining same-run native suite
  [40642072411/1](https://github.com/NoGod3524/EXReader/actions/runs/40642072411)
  was still running at this record.
- F3 focus-sample correction from `95d2a791`, tested against the preserved
  original executable in [40640538850/1](https://github.com/NoGod3524/EXReader/actions/runs/40640538850).
- Android common history source `36fb8db3c088d665f87aac407f8e3739fa73e0f0`,
  tested in [40640180824/1](https://github.com/NoGod3524/EXReader/actions/runs/40640180824).

The Git merge had no conflicts; the Wave3 file was auto-merged. The combined
source has not been built or tested. Existing SDK 3.41-specific host guards
and parser policies still need explicit 3.42 integration, as described in
`migration-common-prep.md`. Full migration compatibility and each actual
host lifecycle remain open. The listed separate runs do not constitute
same-source acceptance of this composition. Do not replace the frozen SDK,
merge to the product branch, or publish a release based on this preparation.
