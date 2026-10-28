# Independent OpenType acceptance integration

Test source 133b97cb81dad003f6e1b802852c80272f08b5a3 and
[run 40623658421, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40623658421)
passed on Windows, Linux and macOS, with the same-run authentication job also
passing. The candidate SDK was pinned to 5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9
and the baseline to 25c2ef86c5c1c4e72b2c9d9daf8c47873c49bcab. Each platform
reported 30 cases, six alternating scenarios and 358 results, with matching
public outputs, cancellation callbacks, work-limit results and hand-authored
expectations. The SDK source and headers did not change in that test branch.

Artifacts, all from the same run and attempt:

- Linux: 12789060405, SHA-256 1d79b8d2678584036ed72b791c25f20f8aed017f4f93ed9b7d448da11d2d119c.
- Windows: 12788442388, SHA-256 66a93ae40d9d893b52c948f18917858a0ca56f6a084de5c1b22123fde04eb435.
- macOS: 12787729420, SHA-256 8330d050870dd29bb22f9b7b3f2fb8cf4141fbc3c32241dcbd9bd5fa646ad1d9.
- Authentication: 12788422589, SHA-256 dc91c620555bd86e948dd8bfe5cf69984ce20c9840240295d3b21624ab6b7331.

The previous failed run 40622921759/1 and its platform-specific missing
Windows font path are preserved in the test package README. The test package
is integrated here without changing the product. Its guard additionally pins
the already-published SDK evidence document; the new integration commit is not
the original tested test source. Future SDK or test changes require a new
three-platform run and authentication.
