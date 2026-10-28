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

## Integrated test package verification

[Run 40624960071, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40624960071)
passed Windows, Linux and macOS correctness jobs and same-run authentication.
The test source was 9ba27dc4b6f6d1105bac872c378ac36a1a1ad2da; the fixed SDK
candidate and control remain the exact sources above. This verifies the added
source admission after integration.

Artifacts:
- Windows 12789047676, SHA-256 6db47b367e5aa8ea7d4ad0b0ee67cca58347ccce0a73583e71d80babe76681ee.
- Linux 12788508952, SHA-256 3a421bbc895aa82b419a97bcb030102ce7ae84e39b773ad4f3ee9b5a3feedaf8.
- macOS 12788434372, SHA-256 86881855cef8be21491cadd37088e6e5ea6413d6c3a4230f65132973e08ab546.
- Authentication 12788793604, SHA-256 21eb603dd5adafb7547884e161d8d683474f8d356516e2c659f8cbae66ae2dc0.
