# Windows account and read-only sync evidence

[Actions 40642072411, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40642072411)
completed all steps on source `42445abd6dfeb312c8803d0a000a32f2a0459a15`
with the packaged Windows Wave3 host and installed SDK 3.41.

The retained Wave3 UI step exercises read-only status before syncing and after
a real failed network session, verifies unchanged database state, and scans
the profile for the session secret. The same run passed 32 native account
checks covering secure credential binding, native HTTPS transfer, real reading
records, interrupted network recovery, cancellation and explicit retry,
mapping recovery, shutdown during scan and reopen. Its organization step also
passed original receive cancellation and retry, original hash checks, and
shelf, series and tag synchronization.

[Actions 40643169696, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40643169696)
independently authenticated the early account artifact and 32 actual successful
checks at that source and attempt. Its source is
`87a039e0c4e3f3ae0f7fe4995f1dcfb20617ea5c`.
The early artifact is 12795934576, 4,115,157 bytes, SHA-256
`bf48afd9828d90777b10e7efcc9411038aee7d5f689c445edfabc79cb2c09659`.
The full-run artifact is 12796877182, 7,671,168 bytes, SHA-256
`9f6f2f2347b87670904b9a3ee6a3cbdffa9e89cd89fb0d86175ae4bef19b5a39`.

The scope is native Windows on a GitHub runner with a local authenticated HTTPS
fixture. The earlier failed run 40639588814 remains recorded in
[the detailed validation](https://github.com/NoGod3524/EXReader/blob/9f0067dc/docs/terra-windows-sync/account-verified.md).
This result does not grant the separate SDK 3.42 candidate, final same-source
six-platform sync, or deployment acceptance.
