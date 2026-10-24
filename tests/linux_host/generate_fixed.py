# SPDX-License-Identifier: MIT
"""Generate independent fixed-page host inputs on Actions, never locally."""
import io
from pathlib import Path
import sys
import zipfile

from PIL import Image, ImageDraw


def pdf(path, repeated=False, rotate=False):
    count = 2 if repeated else 3
    font = 3 + count * 2
    kids = ' '.join(f'{3 + i} 0 R' for i in range(count))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               f'<< /Type /Pages /Count {count} /Kids [{kids}] >>'.encode()]
    for i in range(count):
        objects.append((f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] '
                        f'/Rotate {90 if rotate else 0} /Resources << /Font << /F1 {font} 0 R >> >> '
                        f'/Contents {3 + count + i} 0 R >>').encode())
    for i in range(count):
        if repeated:
            line = ('Identical context abcdefghijklmnopqrstuvwxyz 0123456789 selection target '
                    'identical suffix abcdefghijklmnopqrstuvwxyz 0123456789')
            lines = [line] * 3
        else:
            lines = [f'Fixed page {i + 1}. Native Linux PDF selection and annotation.',
                     f'Second distinct line on page {i + 1}. Stored original bytes survive restart.']
        content = 'BT /F1 12 Tf 36 720 Td ' + ' 0 -32 Td '.join(f'({line}) Tj' for line in lines) + ' ET'
        stream = content.encode('ascii')
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n'.encode() + b'0000000000 65535 f \n'
    for offset in offsets[1:]:
        data += f'{offset:010d} 00000 n \n'.encode()
    data += (f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n').encode()
    path.write_bytes(data)


def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    pdf(folder / 'Pages.pdf')
    pdf(folder / 'Repeated.pdf', repeated=True)
    pdf(folder / 'Rotated.pdf', rotate=True)
    with zipfile.ZipFile(folder / 'Pages.cbz', 'w') as archive:
        for i in range(3):
            image = Image.new('RGB', (600, 800), 'white')
            draw = ImageDraw.Draw(image)
            draw.rectangle((40 + i * 20, 70, 500, 700 - i * 30), fill=(40 + i * 60, 60, 180 - i * 30))
            draw.ellipse((100, 150, 350, 450), fill=(230, 160 - i * 40, 50))
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            item = zipfile.ZipInfo(f'{i + 1:03}.png', date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, buffer.getvalue())
    (folder / 'Broken.pdf').write_bytes(b'not a PDF')
    (folder / 'Broken.cbz').write_bytes(b'not a ZIP')
    with (folder / 'Too-large.pdf').open('wb') as output:
        output.truncate(32 * 1024 * 1024 + 1)


if __name__ == '__main__':
    generate(Path(sys.argv[1]))
