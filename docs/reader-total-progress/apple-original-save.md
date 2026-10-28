# Apple original save: native picker evidence

Status: incomplete. The host already routes original export through the system
folder picker and the installed original-export module. The focused acceptance
in `tests/apple_native_original` drives that control, uses the system picker,
and compares the selected destination's bytes with the bundled EPUB fixture.
It makes no physical-device or signing claim.

- Source `dd7830e474ff59755df4b5aa3b7460f4c39658f4`, Actions run
  [40627102091](https://github.com/NoGod3524/EXReader/actions/runs/40627102091),
  attempt 1: all three jobs failed. The retained macOS result showed successful
  export but the test read the accessibility label instead of the value. iPad
  reached an empty Files local provider and could not find the presumed app
  directory. These are test-driver failures; they do not establish byte readback.
- Actions diagnostic runs [40628232999](https://github.com/NoGod3524/EXReader/actions/runs/40628232999),
  [40628370172](https://github.com/NoGod3524/EXReader/actions/runs/40628370172),
  [40628531759](https://github.com/NoGod3524/EXReader/actions/runs/40628531759),
  and [40628671724](https://github.com/NoGod3524/EXReader/actions/runs/40628671724)
  inspected the retained failure in Actions; they are not acceptance runs.
- Source `3c485caba11fe23c3e091e03e2bf29fe3a87c535`, Actions run
  [40628829670](https://github.com/NoGod3524/EXReader/actions/runs/40628829670),
  attempt 1: macOS passed the native picker and byte-for-byte readback; 7,724
  source and saved bytes have SHA-256
  `0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb`.
  iPhone and iPad were queued at the time of this record. Check that same run
  for their eventual results before claiming simulator acceptance.

The corrected iOS test creates a folder in the Files local provider, selects it
through the native picker, then locates the unique folder in the simulator's
containers for independent byte comparison. This route remains unverified until
both simulator jobs finish successfully. Preserve all failure artifacts and
existing catalog status until the complete acceptance has been reviewed.
