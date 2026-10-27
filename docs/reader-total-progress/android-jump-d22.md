# Android real search jump history: D22 retained evidence

Source: `92d453e374725896a7d1666c313e5d369ff83b3c`.
[Run 40460333186, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40460333186) completed successfully; both the Android build/receive and retained jobs passed.

The retained job verifies the APK identity against the same source, run and attempt, and executes `tests/reader_wave3_c11/device.sh` on the API 34 x86_64 emulator. The existing `jump_history_back_forward_over_real_search_landing` case opens the actual TXT reader, searches for a unique token, opens the result, and compares actual page starts when moving back and forward. The runner requires this named check, every other declared phase check, and matching installed APK bytes.

Artifact `12715880811`: 112475779 bytes, SHA-256 `369380a70797fd8bc1e5b3212720b716d3c010436c0a4cf1825b780bf79ded06`. The fixed catalog audit re-downloads this ZIP in Actions, verifies its identity and digest, and reads the named passing check. This evidence grants Android emulator search-jump history only; physical-device and final unified-source acceptance remain separate.
