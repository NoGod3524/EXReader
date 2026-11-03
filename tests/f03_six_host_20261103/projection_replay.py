"""Native regression: deletion projection must converge on warm and fresh replicas."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from run import ROOT, admission, setup

def main():
    stamp = admission()
    identity = setup()
    p = argparse.ArgumentParser()
    p.add_argument("--consumer", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "tests/reader_sync"))
    from check_sync import revision, raw
    book = "txt:" + "a"*64
    parent, child, tag, series = (c*32 for c in "bcde")
    values = [
        revision(1, kind="book", key=book, payload={"format":"txt", "source_sha256":"a"*64,
                 "source_bytes":123, "title":"Replay book", "author":"", "favorite":False}),
        revision(2, kind="shelf", key=parent, payload={"name":"Parent", "parent_id":None, "ordinal":1}),
        revision(3, kind="shelf", key=child, payload={"name":"Child", "parent_id":parent, "ordinal":2}),
        revision(4, kind="tag", key=tag, payload={"name":"Tag"}),
        revision(5, kind="series", key=series, payload={"name":"Series"}),
    ]
    for n, kind, group, order in ((6,"shelf",child,3),(7,"tag",tag,0),(8,"series",series,7)):
        values.append(revision(n, kind="membership", key=kind+":"+group+":"+book,
                      payload={"collection_kind":kind,"collection_id":group,"book_key":book,"ordinal":order}))
    for n, kind, group, previous in ((9,"shelf",child,3),(10,"tag",tag,4),(11,"series",series,5)):
        values.append(revision(n, kind=kind, key=group, operation="delete", parents=[values[previous-1]["id"]]))
    paths = []
    for value in values:
        path = a.output / (value["id"] + ".json")
        path.write_bytes(raw(value)); paths.append(path)
    def call(database, *args):
        result = json.loads(subprocess.check_output([str(a.consumer.resolve()), str(database), *map(str,args)]))
        identity.require(result["status"] == 0, "public native projection call failed: " + str(result))
        return result
    def project(database):
        call(database,"book",book,values[0]["id"],"Replay book")
        unresolved = []
        for kind in ("shelf","tag","series","membership"):
            for retry in range(3):
                rows=call(database,"page",kind,"-",100)["rows"]
                pending=[row for row in rows if row["result"] != 0]
                if not pending:break
            unresolved.extend({"kind":kind,**row} for row in pending)
        return unresolved
    warm, cold = a.output / "warm.sqlite", a.output / "cold.sqlite"
    for path in paths[:8]:call(warm,"receive",path)
    identity.require(not project(warm), "initial warm projection failed")
    for path in paths[8:]:call(warm,"receive",path)
    warm_pending=project(warm)
    for path in paths:call(cold,"receive",path)
    cold_pending=project(cold)
    warm_snapshot, cold_snapshot = identity.read_snapshot(warm), identity.read_snapshot(cold)
    differences={table:{"warm":warm_snapshot[table],"cold":cold_snapshot[table]}
                 for table in identity.TABLES if warm_snapshot[table] != cold_snapshot[table]}
    accepted = not warm_pending and not cold_pending and not differences
    report={**stamp,"accepted":accepted,"scope":"native warm/cold organization deletion projection only",
            "warm_pending":warm_pending,"cold_pending":cold_pending,"differences":differences,
            "complete_product_accepted":False,"full_F03_accepted":False}
    identity.write_json(a.output/"result.json",report)
    print(json.dumps(report))
    identity.require(accepted,"warm/cold organization deletion projection diverges")

if __name__ == "__main__":main()
