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
