# Fixed raw inputs

`frozen-inputs.json` binds the eight existing `real-v1.json` documents to the R2
archive from accepted default-branch run 39974986212. `collect.py cached` checks
the run and archive identities, ZIP digest, exact document membership and every
document size/SHA before writing new inputs. It reruns independent structure
inspection and fetches current publisher license pages with the existing
required-terms checks. It copies no previous SDK or reference results.

`collect` still fetches publisher originals directly; `discover` retains source
discovery. Neither silently falls back to the archive. Direct identity failures
now record the observed size, SHA and final URL.

The registered artifact currently expires on 2026-11-22. Missing, expired or
changed evidence stops collection. A separately registered durable store of the
same original bytes is still needed for permanent preservation. This change
does not grant permanent availability or transfer old-source acceptance.

Cloud diagnostic 39986016184 recovered all eight exact originals and passed
current license/structure checks. Its independent publisher probe observed
different bytes at the same pg84 URL. The diagnostic grants no engine or budget
acceptance; current-source R2/R3 must still execute. Full identities are in
[the diagnostic record](../../docs/validation/reading-frozen-inputs-39986016184.json).
