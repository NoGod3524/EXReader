"""Align executed coverage with the six fixed recovery claims, including not-run."""
CASES = (
    ("cancel_sync_retry", "cancel_retry", "local", "local"),
    ("offline_reconnect", "offline_reconnect", "author", "receiver"),
    ("kill_commit_ack_replay", "process_recovery", "local", "local"),
    ("delete_put_tombstone_preserved", "delete_put_tombstone_preserved", "receiver", "receiver"),
    ("concurrent_heads_preserved", "concurrent_heads_preserved", "receiver", "receiver"),
    ("restart_offline_read", "offline_read", "local", "local"),
)
NOT_RUN_REASON = "No completed native case supplies this claim"


def align_cases(coverage, receipt, claims):
    def require(value, message):
        if not value:
            raise AssertionError(message)
    def index(items, key):
        require(isinstance(items, list) and len(items) <= 6, "six-case list required")
        result = {}
        for row in items:
            require(isinstance(row, dict) and isinstance(row.get(key), str), "case ID required")
            require(row[key] not in result, "duplicate case ID: " + row[key])
            result[row[key]] = row
        return result
    actual, declared = index(coverage, "name"), index(receipt, "id")
    require(bool(actual), "empty executed coverage")
    require(set(actual) <= {row[0] for row in CASES}, "extra coverage ID")
    require(isinstance(claims, dict) and set(claims) == {row[1] for row in CASES}, "six exact claims required")
    used, rows = set(), []
    for case_id, claim, role, missing_role in CASES:
        if case_id in actual:
            expected_id = case_id
            outcome = actual[case_id].get("outcome")
            require(outcome in ("passed", "partial", "failed"), "invalid executed outcome")
            require(case_id in declared and declared[case_id].get("outcome") == outcome,
                "missing or mismatching executed receipt: " + case_id)
        else:
            expected_id, role, outcome = "not-run-" + claim, missing_role, "not-run"
            require(declared.get(expected_id) == {"id":expected_id, "outcome":"not-run",
                "reason":NOT_RUN_REASON}, "missing or invalid not-run declaration: " + case_id)
        require(claims[claim] == [{"case_id":expected_id, "role":role}], "claim binding mismatch: " + claim)
        used.add(expected_id)
        rows.append({"id":case_id, "receipt_id":expected_id, "outcome":outcome,
                     "executed":case_id in actual})
    require(set(declared) == used, "extra receipt ID")
    return rows
