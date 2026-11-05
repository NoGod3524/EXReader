# Android history compatibility on the common reader candidate

[Actions run 40640180824, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40640180824)
tested `36fb8db3c088d665f87aac407f8e3739fa73e0f0`. All three jobs
completed successfully: the original Android suite, the current Android
reading/sync/owner and history compatibility suite, and their same-run
artifact authentication.

The original suite records 130 checks. The current suite records 19 reading,
16 sync, 18 owner checks and 8 history-compatibility observations. The
aggregator verifies the current source and run identity, same-run artifact
digests, reports, and the signing identity of all five APKs.

Authenticated artifacts:

- Original suite: 12796280286, 131,391,773 bytes, SHA-256
  `d11a6c87e644224d789b7b52f865564177126f5238ddac7f7d4d503e437426e7`.
- Current suite: 12795458777, 29,526,303 bytes, SHA-256
  `ca8c2629431eee453af2b35f62e104ec55e87db3737452db776ace5c035dc416`.
- Summary: 12796381147, 2,412 bytes, SHA-256
  `c198d15c4201d9f7c61b5de42cc57b6be476c099707fed9a57ca06fa3a744ca8`.

The evidence covers the API 34 x86_64 emulator and SDK 3.41 candidate.
It does not establish 3.42, physical-device, remote provider, performance
or complete multi-platform acceptance. The earlier common-source run
[40638429504/1](https://github.com/NoGod3524/EXReader/actions/runs/40638429504)
failed because the current job and raw-selector identity capture were skipped;
the workflow conditions were corrected on the tested source. The earlier
standalone failures remain recorded in their original runs. This evidence-only
commit is not the tested source.
