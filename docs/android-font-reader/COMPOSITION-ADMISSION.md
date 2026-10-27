# Android font common-source admission

[Actions 40592584270, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40592584270)
successfully checked candidate `248e02e9b7205e4c793dbf4d372876023987776d`
using the Android font, D21 Apple, D22 Android and D25 real-corpus admission
guards. The probe workflow source was `fc05d7918bd5e8fd13b839a7423ccf346bd92037`;
it checked out the exact candidate and set the source identity for these guards.

The guard check does not build or exercise the product. The Android font
candidate's emulator run and each full common-source platform gate remain
separate. No frozen test or SDK path was changed by the admission probe.


The same four admission guards passed on the combined Android-font and Windows
TXT-search-history candidate `d21978f401781b311ad6168d0eb474f1657c9fb2` in
[Actions 40593986721/1](https://github.com/NoGod3524/EXReader/actions/runs/40593986721).
This checks source ownership and pinned bytes only; the candidate still requires
its product and platform runs.

[Actions 40604679182/1](https://github.com/NoGod3524/EXReader/actions/runs/40604679182)
passed the D23 Windows admission and Android font, D21, D22, D25 and
Android system-save source checks on candidate
`b9dca7c5b4b21b69aa6d63a5893a0141eaa814d5`. The probe workflow source was
`9f962a8980046e4c6f537cef7dc390a736422998`.

The preceding probe [40604422777/1](https://github.com/NoGod3524/EXReader/actions/runs/40604422777)
failed because the newly integrated save tests and audited evidence paths had
not yet been registered. The corrected candidate pins these files to their
recorded source commits; all existing source guards remain active. This run
checks source admission only. The product and same-source platform runs remain
separate.
