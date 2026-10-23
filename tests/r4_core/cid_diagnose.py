"""Diagnose actual bundled FreeType raw CID versus SFNT behavior in CI."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import pymupdf

if not os.environ.get('GITHUB_ACTIONS'):
    raise SystemExit('Run in GitHub Actions')
if sys.argv[1] == '--streams':
    source, output = map(Path, sys.argv[2:])
    output.mkdir(parents=True, exist_ok=False)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    assert sha == '2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a'
    document = pymupdf.open(source)
    page = document[35]
    related = {page.xref, *page.get_contents()}
    for image in page.get_images(full=True):
        related.update(image[:2])
    related.update(form[0] for form in page.get_xobjects())
    related.discard(0)
    supported = {'FlateDecode', 'Fl', 'LZWDecode', 'LZW', 'ASCIIHexDecode', 'AHx',
        'ASCII85Decode', 'A85', 'RunLengthDecode', 'RL', 'CCITTFaxDecode', 'CCF', 'DCTDecode', 'DCT', 'Crypt'}
    records = []
    for xref in range(1, document.xref_length()):
        if xref not in related and not document.xref_is_stream(xref):
            continue
        filter_kind, filters = document.xref_get_key(xref, 'Filter')
        parms_kind, parms = document.xref_get_key(xref, 'DecodeParms')
        resolved_filters = document.xref_object(int(filters.split()[0])) if filter_kind == 'xref' else filters
        resolved_parms = document.xref_object(int(parms.split()[0])) if parms_kind == 'xref' else parms
        names = re.findall(r'/([A-Za-z0-9]+)', resolved_filters)
        reasons = []
        if any(name not in supported for name in names):
            reasons.append('unsupported-filter-name')
        if filter_kind not in {'null', 'name', 'array', 'xref'}:
            reasons.append('filter-shape')
        if (filter_kind == 'array' and parms_kind not in {'null', 'array', 'xref'}) or (filter_kind == 'name' and parms_kind == 'array'):
            reasons.append('filter-parameter-shape')
        if filter_kind == 'array' or parms_kind not in {'null', 'dict'}:
            reasons.append('array-or-indirect-shape-review')
        if xref in related or reasons:
            row = {'xref': xref, 'page35_related': xref in related, 'filter': [filter_kind, filters],
                'decode_parms': [parms_kind, parms], 'resolved_filter': resolved_filters,
                'resolved_parms': resolved_parms, 'candidate_reasons': reasons,
                'dictionary': document.xref_object(xref)}
            records.append(row)
            print(json.dumps(row), flush=True)
    report = {'diagnostic_only': True, 'source_sha': os.environ['GITHUB_SHA'], 'input_sha256': sha,
        'page': 35, 'page_xref': page.xref, 'page_images': page.get_images(full=True),
        'page_forms': [(form[0], form[1], form[2]) for form in page.get_xobjects()],
        'page_contents': page.get_contents(), 'records': records}
    (output/'stream-inventory.json').write_text(json.dumps(report, indent=2)+'\n')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == sha
    print(json.dumps({key: value for key, value in report.items() if key != 'records'}), flush=True)
    raise SystemExit(0)
binary, source, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=False)
assert hashlib.sha256(source.read_bytes()).hexdigest() == '2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a'
document = pymupdf.open(source)
raw = output/'nasa-page29.cid'
raw.write_bytes(document.extract_font(820)[3])
wrapped = Path('tests/fixtures/fonts/pdf-cid.otf')
data = wrapped.read_bytes()
synthetic = output/'synthetic.cid'
for index in range(struct.unpack_from('>H', data, 4)[0]):
    tag, _, offset, size = struct.unpack_from('>4sIII', data, 12+16*index)
    if tag == b'CFF ':
        synthetic.write_bytes(data[offset:offset+size])
        break
records = []
for font in (raw, wrapped, synthetic):
    result = subprocess.run([str(binary.resolve()), '--cid-probe', str(font.resolve())], capture_output=True, timeout=120)
    (output/(font.stem+'.stdout')).write_bytes(result.stdout)
    (output/(font.stem+'.stderr')).write_bytes(result.stderr)
    record = {'font': str(font), 'sha256': hashlib.sha256(font.read_bytes()).hexdigest(), 'exit': result.returncode}
    records.append(record)
    print(json.dumps(record), flush=True)
    print(result.stdout.decode(), flush=True)
(output/'summary.json').write_text(json.dumps({'diagnostic_only': True, 'source_sha': os.environ['GITHUB_SHA'], 'records': records}, indent=2)+'\n')
assert all(record['exit'] == 0 for record in records)
