# D23 current-source relay

Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.

The candidate already contains the relay from `609ab65555d16e2bf7f1533c5864a894ef0d6033`, including the chooser-state synchronization originally authored in `f92e31c8f9db0cf71f098782223a0f9a54daf292`. No missing implementation is inferred from the older `e61b5eda` failure in run 40425627113/1. That failure and its original tests remain unchanged.

The D23 directory initially preserves all existing relay assertions. Its dedicated workflow checks the common candidate rather than the older product-path baseline, builds both native hosts from the same source, retains Windows and both GTK account regressions, and verifies the four phases' run/attempt, source, binary, certificate and object hashes. TLS service state is transferred between separate runners; this is NOT one continuously running service or online concurrency.

No local build, fixture generation, syntax check, test or artifact processing is permitted. Results and any product repairs will be based on this workflow's actual same-source failures. SDK, historical tests, Windows large-TXT candidate and other task workspaces are untouched.

Baseline run 40447044820/1 passed all five jobs at source `026cd51f2fde3fb3e8cb70bf1a46b40df5eb45bb`. Current chooser behavior did not reproduce the historical failure. Review nevertheless found a real verification gap: Windows return checked SDK bytes but did not explicitly open the GTK book in the native reader. D23 adds a native shelf-open and rendered-selection-copy assertion for both the received GTK book and the previous Windows book, with screenshots, without changing any prior assertion. The final candidate must rerun every phase and the strict verifier.
