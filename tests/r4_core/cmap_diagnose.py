"""Cloud-only structural inventory; original streams stay in the artifact."""
import hashlib
import json
import pathlib
import re
import sys

import pymupdf

root = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
records = []
for path in sorted(root.rglob("*.pdf")):
    if path.name not in {"nist-csf2.pdf", "nasa-solar-system.pdf"}:
        continue
    document = pymupdf.open(path)
    for xref in range(1, document.xref_length()):
        group_kind, group_value = document.xref_get_key(xref, "Group")
        if group_kind not in {"null", "none"}:
            group_xref = int(group_value.split()[0]) if group_kind == "xref" else xref
            key = "CS" if group_kind == "xref" else "Group/CS"
            space_kind, space_value = document.xref_get_key(group_xref, key)
            print(json.dumps({"file": path.name, "group_form_xref": xref,
                "group": [group_kind, group_value], "space": [space_kind, space_value],
                "group_object": document.xref_object(group_xref),
                "space_object": document.xref_object(int(space_value.split()[0]))
                if space_kind == "xref" else None}))
        mask_kind, mask_value = document.xref_get_key(xref, "SMask")
        if mask_kind in {"dict", "xref"}:
            print(json.dumps({"file": path.name, "smask_owner": xref,
                "smask": document.xref_object(int(mask_value.split()[0]))
                if mask_kind == "xref" else mask_value}))
        kind, value = document.xref_get_key(xref, "ToUnicode")
        if kind != "xref":
            continue
        stream_id = int(value.split()[0])
        data = document.xref_stream(stream_id)
        name = f"{path.stem}-{xref}-{stream_id}.cmap"
        (output / name).write_bytes(data)
        spaces = []
        mappings = []
        for block in re.findall(rb"begincodespacerange(.*?)endcodespacerange", data, re.S):
            tokens = re.findall(rb"<([0-9A-Fa-f\s]*)>", block)
            for first, last in zip(tokens[::2], tokens[1::2]):
                a, b = bytes.fromhex(first.decode()), bytes.fromhex(last.decode())
                spaces.append((len(a), int.from_bytes(a, "big"), int.from_bytes(b, "big")))
        for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
            tokens = re.findall(rb"<([0-9A-Fa-f\s]*)>", block)
            for source, target in zip(tokens[::2], tokens[1::2]):
                a = bytes.fromhex(source.decode())
                mappings.append((len(a), int.from_bytes(a, "big"), int.from_bytes(a, "big")))
        for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
            for row in block.splitlines():
                tokens = re.findall(rb"<([0-9A-Fa-f\s]*)>", row)
                if len(tokens) >= 3:
                    a, b = [bytes.fromhex(token.decode()) for token in tokens[:2]]
                    mappings.append((len(a), int.from_bytes(a, "big"), int.from_bytes(b, "big")))
        mappings.sort()
        overlap = [(a, b) for a, b in zip(mappings, mappings[1:]) if a[0] == b[0] and a[2] >= b[1]]
        outside = [m for m in mappings if not any(s[0] == m[0] and s[1] <= m[1] and s[2] >= m[2] for s in spaces)]
        row = {"file": path.name, "font_xref": xref, "stream_xref": stream_id,
               "path": name, "sha256": hashlib.sha256(data).hexdigest(),
               "spaces": spaces, "mapping_count": len(mappings),
               "overlap_count": len(overlap), "overlap": overlap[:5],
               "outside_count": len(outside), "outside": outside[:5],
               "type2": bool(re.search(rb"/CMapType\s+2\s+def", data))}
        records.append(row)
        print(json.dumps(row))
(output / "inventory.json").write_text(json.dumps({"diagnostic_only": True, "accepted": False, "records": records}, indent=2))
