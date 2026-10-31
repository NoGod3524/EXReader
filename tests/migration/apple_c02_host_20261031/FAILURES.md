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

## Second candidate 36918c9c1ee18aa5345cd6ea4cf3072922e3c43b

[Run 41177046640, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41177046640).
Both SDK and both complete products jobs succeeded. Native runtime cases have
not yet run.

Simulator runtime job124467687280 failed compiling the production bundle:
HostC02Admission.swift:30 resolved open to the enclosing enum method.
The correction explicitly selects Darwin.open.

macOS runtime job124467687252 built and checked the full production bundle,
then failed compiling the review harness: excluding ReaderApp.swift while
including HostViews.swift removed its SelfTestScreen declaration. The harness
now explicitly compiles the nine production SDK/model/catalog owner files and
their actual dependencies. The full production app continues compiling all UI
and its original ReaderApp entry point.

| Artifact | ID | Bytes | API SHA256 |
| --- | --- | ---: | --- |
| c02-apple-sdk-macos-41177046640-1 | 13033017427 | 19352659 | c89f5d00917fed5462ea3b13491792de0905a492d763b55d4168dd6db8e86477 |
| c02-apple-sdk-iphonesimulator-41177046640-1 | 13032777523 | 19347238 | ca6bcff45e522772b1ea3bd4c34d9a8b9620c4a11cc2b7f5a6b8ebb996ec42f2 |
| c02-apple-products-macos-41177046640-1 | 13033797396 | 5078581 | 98f1cf29a6fe8f58aca8c1d73412cea6995ddd017b7d95add8742e72067c4e50 |
| c02-apple-products-iphonesimulator-41177046640-1 | 13033253643 | 1493227 | 444c370f464d83d78d1ad4252f29fcc0f68e13804c1d3f7a02fb38d9de44c2b2 |
| c02-apple-runtime-macos-41177046640-1 | 13033343936 | 104469 | f49f0a99f68539df29b2e20248f721048c142c54a381f8ff5f2701aa8fcfd868 |
| c02-apple-runtime-iphonesimulator-41177046640-1 | 13032744433 | 103895 | 68e63c8a3134a9015766b7a72142c34d59a5e632288d12fa82e217c933930ef9 |

## Third candidate 0bf4bf4b99795e0f2301b372cd7eb60dd631361e

[Run 41177757574, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/41177757574).
Both SDK and both products jobs succeeded. macOS runtime job124469334136
succeeded. Simulator runtime job124469334107 built both bundles and completed
the actual1002/1102 external termination barriers, then failed baseline startup.

The original ZIP was independently API/digest-bound and read only in
[diagnostic run41178931382/A1](https://github.com/NoGod3524/EXReader/actions/runs/41178931382).
Its baseline.log and runtime/baseline/failure.json show actual HostModel startup
deadline. The harness executed its blocking baseline inside a main GCD block;
nested iOS RunLoop waiting could not run the queued main completion block.
The test now runs its iOS exercise on a worker and uses main.sync for model
creation/actions/state reads. UIKit's ordinary main loop remains available.
The30second deadline and all actual admission/last-owner assertions remain.

| Artifact | ID | Bytes | API SHA256 |
| --- | --- | ---: | --- |
| c02-apple-sdk-macos-41177757574-1 | 13033249682 | 19354597 | 6ef6ff48fdae2710e950e6943e7421bad0632cb5c299a28ccac5e1fd5ffcad54 |
| c02-apple-sdk-iphonesimulator-41177757574-1 | 13034035284 | 19349519 | c2cdba63f44e28ef12c49708b5945fb337459465b4ed5a3282793444c326df0c |
| c02-apple-products-macos-41177757574-1 | 13033841686 | 5078591 | 1a68ae7ec87786466c824682be342937f43273c632538cb2c091c486a1a21d16 |
| c02-apple-products-iphonesimulator-41177757574-1 | 13034095194 | 1493235 | 47db02395319cf38ed26bdb5b76c5da2d3dcecd9e2104c211e55b0b2c5593053 |
| c02-apple-runtime-macos-41177757574-1 | 13033808562 | 55007217 | 79d9dd786a363cf09aee20462590694924045cabe725925252ee4b9e83ed7390 |
| c02-apple-runtime-iphonesimulator-41177757574-1 | 13033871756 | 54869708 | bb8cea6ace75d618e997ea36b76e46790678fe7225e920a038170b870a749d48 |
