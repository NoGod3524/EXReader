# S13 root review

The original green run 40233303849 does not establish root acceptance: its
summary did not hash the API artifact ZIP or include actual measured programs.
The original worker also exceeded its three-round limit; all earlier failures
and that process violation remain in the original branch history.

This separate review keeps the candidate patch, frozen SDK and original
expectations unchanged. It authenticates exact-attempt producer jobs, original
ZIP bytes/digest/expiry, safe unique archive members, actual probe and runtime
bytes, all four report parts and exact named-check counts. Equal failures in
both original suites no longer pass. Package binaries and install prefixes are
included in producer artifacts. Regression refusals execute only in Actions.

Root review budget: at most three full cloud rounds. No local builds, tests,
syntax checks, fixture generation or artifact processing. No SDK adoption,
performance or complete reader-product grant is made by this review.

Status: cloud verification pending.
