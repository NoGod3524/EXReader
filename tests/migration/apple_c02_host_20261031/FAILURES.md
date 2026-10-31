# Apple C02 Actions failure history

## First candidate b396d639ff56016e1b7f806cce64385890486936

[Run 41176352127, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41176352127),
2026-10-31 06:22:42 UTC. Both frozen SDK jobs succeeded. Both products jobs
failed compiling the SDK admission helper; runtime jobs were skipped.

- macOS SDK job 124464599946: success.
- iPhone simulator SDK job 124464600014: success.
- macOS products job 124465341301: failure.
- iPhone simulator products job 124465341263: failure.

Both original failed logs report
extras/migration/posix_c02_sdk_admission_20261031/src/pc02_sdk.c:33:
use of undeclared identifier O_NOFOLLOW. Strict POSIX/XOPEN feature selection
hid the Darwin declaration. The native pc02.c already enables
_DARWIN_C_SOURCE; the SDK adapter needs the same declaration before system
headers. No test classification or admission check is relaxed.

Original artifacts remain attached to this run. The following sizes and digests
are GitHub artifact API metadata; no ZIP was downloaded or parsed outside Actions.

| Artifact | ID | Bytes | API SHA256 |
| --- | --- | ---: | --- |
| c02-apple-sdk-macos-41176352127-1 | 13033616057 | 19352489 | ffe280393c333b712236121f337f2a54909450f23bb7bcb9e992ea21d760362f |
| c02-apple-products-macos-41176352127-1 | 13033526193 | 1480731 | 44c4d4c6ca12947f80f67233097d32027fde064df4e8bf33ee4077bd3feff7b0 |
| c02-apple-sdk-iphonesimulator-41176352127-1 | 13033476969 | 19347139 | 369e15e1124695a7f7ef5bd9dc36150333d4a4fc65dbff4f16d28aef47b1c04e |
| c02-apple-products-iphonesimulator-41176352127-1 | 13032758313 | 1479814 | eda6cb2730118b748b9aeaabfc20e464da13a4c4d5fe8d9189a02a76308f33db |

Successful SDK compilation and partial product artifacts do not qualify Apple
runtime admission or complete C02.
