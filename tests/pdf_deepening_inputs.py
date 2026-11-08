"""Original controlled PDF inputs; binary samples are always generated outside git.
CTest generation uses only Python's standard library. Matrix encryption uses pypdf.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zlib

TEXT = ['alpha beta gamma delta epsilon', 'zeta eta theta iota kappa', 'boundary']


def pdf(pages):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>']
    kids = []
    for content in pages:
        page = len(objects) + 1
        kids.append(f'{page} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 120] /Resources << /Font << /F1 3 0 R >> /XObject << /Im {page+2} 0 R >> >> /Contents {page+1} 0 R >>'.encode())
        objects.append(stream(content))
        pixels = bytes(c for y in range(8) for x in range(8) for c in ((0, 0, 0) if (x+y)%2 else (255, 255, 255)))
        objects.append(stream(zlib.compress(pixels), b'/Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode'))
    objects[1] = f'<< /Type /Pages /Count {len(pages)} /Kids [{" ".join(kids)}] >>'.encode()
    data = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f'{number} 0 obj\n'.encode()+body+b'\nendobj\n')
    start = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return data


def stream(data, attributes=b''):
    return b'<< /Length '+str(len(data)).encode()+b' '+attributes+b' >>\nstream\n'+data+b'\nendstream'


def text(value):
    return b'BT /F1 12 Tf 20 90 Td ('+value.encode('cp1252')+b') Tj ET'


def generate(directory, encrypted=False):
    directory.mkdir(parents=True, exist_ok=True)
    scan = b'q 80 0 0 80 20 20 cm /Im Do Q'
    definitions = {
        'text-a': ('text', [text(s) for s in TEXT]),
        'text-b': ('text', [text('café naïve résumé'), text('repeat repeat end')]),
        'scan-a': ('scan', [scan]*10),
        'scan-b': ('scan', [scan, scan]),
        'mixed-a': ('mixed', [text('alpha'), scan, text('beta'), scan]),
        'mixed-b': ('mixed', [scan, text('gamma'), scan]),
    }
    metadata = []
    for name, (kind, pages) in definitions.items():
        path = directory/(name+'.pdf'); path.write_bytes(pdf(pages))
        metadata.append(dict(id=name, kind=kind, path=str(path.resolve()), origin='original controlled fixture', expected_pages=len(pages)))
    if encrypted:
        from pypdf import PdfWriter
        for name, source, password, algorithm in [('encrypted-password','text-a','reader','AES-128'), ('encrypted-permissions','text-b','','AES-256')]:
            path = directory/(name+'.pdf')
            writer = PdfWriter(clone_from=directory/(source+'.pdf'))
            writer.encrypt(password, 'owner', algorithm=algorithm, permissions_flag=4)
            writer.write(path)
            metadata.append(dict(id=name, kind='encrypted', path=str(path.resolve()), origin=f'{source}; pypdf {algorithm}', password=password, expected_pages=3 if source=='text-a' else 2))
    for item in metadata:
        item['sha256'] = hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--group')
    args = parser.parse_args()
    if args.probe:
        with tempfile.TemporaryDirectory(prefix='exr-pdf-') as directory:
            generate(Path(directory))
            subprocess.run([str(args.probe), args.group, directory, str(args.fixtures)], check=True)
    else:
        metadata = generate(args.output, encrypted=True)
        (args.output/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')

if __name__ == '__main__':
    main()
