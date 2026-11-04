# S5.5 required-check rejection control

Draft PR #40 targeted main682e1ab5. The only temporary change replaced the protocol release-check command with an explicit nonzero exit; all other groups, dependencies and final aggregation remained unchanged. Run41902048351 completed with protocol=failure and final reading-required-core=failure; every other non-skipped job passed.

Before restoring the branch, GraphQL reported the actual reading-required-core check as isRequired=true, conclusion=FAILURE, status=COMPLETED, app15368/github-actions. The PR had mergeable=MERGEABLE (no conflicts) but mergeStateStatus=BLOCKED; REST independently returned mergeable=true, mergeable_state=blocked. Effective main rules require reading-required-core from app15368 under ruleset25700819. These API responses are preserved verbatim as structured JSON in this directory. PR draft status is retained in the evidence; no merge was attempted.

The negative workflow was restored in commitb43b1fb9, pushed with [skip ci], and the entire resulting source tree was verified equal to the original main682e1ab5 tree. PR #40 was then closed without merge and the remote/local temporary branches deleted. The failing check belongs to the recorded pre-restoration head66cda7de. No ruleset fields were edited.
