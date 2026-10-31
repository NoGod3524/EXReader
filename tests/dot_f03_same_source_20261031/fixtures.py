"""Generate only original book bytes and names. Never synthesize accepted product revisions."""
import argparse
import hashlib
from pathlib import Path
from identity import SCOPE, identity, write_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    stamp = identity()
    a.output.mkdir(parents=True, exist_ok=False)
    books = []
    for host in SCOPE["hosts"]:
        raw = (("F03 actual host source: " + host + "\n") * 80).encode("utf-8")
        filename = host + "-organization.txt"
        (a.output / filename).write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        books.append({"host": host, "path": filename, "bytes": len(raw), "sha256": sha,
                      "book_key": "txt:" + sha,
                      "names": {"root": "F03 " + host + " root", "child": "F03 " + host + " child",
                                "tag": "F03 " + host + " tag", "series": "F03 " + host + " series"}})
    write_json(a.output / "manifest.json", {**stamp, "books": books, "contains_product_revisions": False})
if __name__ == "__main__":
    main()
