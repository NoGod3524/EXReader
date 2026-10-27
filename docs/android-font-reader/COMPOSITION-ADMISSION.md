# Android font common-source admission

[Actions 40592584270, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40592584270)
successfully checked candidate `248e02e9b7205e4c793dbf4d372876023987776d`
using the Android font, D21 Apple, D22 Android and D25 real-corpus admission
guards. The probe workflow source was `fc05d7918bd5e8fd13b839a7423ccf346bd92037`;
it checked out the exact candidate and set the source identity for these guards.

The guard check does not build or exercise the product. The Android font
candidate's emulator run and each full common-source platform gate remain
separate. No frozen test or SDK path was changed by the admission probe.
