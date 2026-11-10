#!/usr/bin/env python3
"""Compare the unchanged #124 writer and editable bridge with #117 metrics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_docx_edit_io import Bridge
from roundtrip import Engine, metrics, differences
from verify_docx import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--baseline-library', type=Path, help='separate #124 control DLL')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    api, reader = Bridge(args.library.resolve()), Engine(args.library.resolve())
    legacy = Engine((args.baseline_library or args.library).resolve())
    report = dict(library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(), documents=[])
    report['baseline_library_sha256'] = hashlib.sha256((args.baseline_library or args.library).read_bytes()).hexdigest()
    for entry in json.loads(args.manifest.read_text(encoding='utf-8-sig'))['documents']:
        source = (args.manifest.parent / entry['path']).resolve()
        data = source.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        baseline = args.output / (entry['id'] + '-legacy.docx')
        output = args.output / (entry['id'] + '-editable.docx')
        legacy_text = legacy.roundtrip(source, baseline)
        doc = api.read(data)
        try:
            output.write_bytes(api.write(doc))
        finally:
            api.doc_free(doc)
        before, after = metrics(source), metrics(output)
        rows = differences(before, after)
        assert all(r['status'] == 'PASS' for r in rows)
        assert all(before[k] == after[k] for k in ('text_sha256', 'image_sha256'))
        source_profile, output_profile = verify(source), verify(output)
        assert [(r['check'], r['status']) for r in source_profile] == [(r['check'], r['status']) for r in output_profile]
        a, b = reader.open(source), reader.open(output)
        try:
            assert reader.text_hash(a) == reader.text_hash(b)
        finally:
            reader.document_free(a)
            reader.document_free(b)
        report['documents'].append(dict(id=entry['id'], source_sha256=entry['sha256'],
            legacy_metrics=differences(before, metrics(baseline)), legacy_sdk_reread=legacy_text,
            editable_metrics=rows, content_hashes_equal=True, sdk_reread='PASS',
            formatting_results_preserved=True))
    report['total'] = 6 * len(report['documents'])
    for mode in ('legacy', 'editable'):
        report[mode + '_passed'] = sum(r['status'] == 'PASS' for d in report['documents'] for r in d[mode + '_metrics'])
    assert report['total'] == report['editable_passed'] == 18
    (args.output / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print('legacy %d/18; editable %d/18; content hashes, SDK reread and format retention PASS' %
          (report['legacy_passed'], report['editable_passed']))


if __name__ == '__main__':
    main()
