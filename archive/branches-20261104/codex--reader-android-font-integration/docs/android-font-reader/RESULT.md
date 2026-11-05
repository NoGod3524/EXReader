# Android reader font on the integrated SDK candidate

[Actions 40590121689, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40590121689)
completed successfully on source `f903d8e1f9ec4692cbbf09b2b4504812256dbdba`.
The real API34 x86_64 emulator ran the retained C11 (20 checks), navigation
(18), reading (19), and new font-reader (3) checks successfully. The font
reader preserved the page and lease after invalid font import, changed rendered
pixels after valid selection and reopening, and released all leases on exit.

Artifact `12774923461` is 164407209 bytes, SHA-256
`37d1073613aba1dd3e69dd1d0659c35785236130f6149cf6f13cfa2d764c6938`,
expires 2027-01-25T21:50:47Z. The picker result is supplied by an ActivityMonitor
test stub; physical DocumentsUI, real devices and TalkBack are separate.

This is Android validation on the named source. The later combined Android-TXT
candidate requires its own same-source gates.
