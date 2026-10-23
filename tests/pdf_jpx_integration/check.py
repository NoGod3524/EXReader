#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Tiny real PDF/JPX closure through the installed public SDK consumer, in CI."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image, features

RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
GRAY = [0, 85, 170, 255]
OK, FORMAT, UNSUPPORTED = 0, 5, 11


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def stream(dictionary, payload):
    return b'<< ' + dictionary + b' /Length ' + str(len(payload)).encode() + b' >>\nstream\n' + payload + b'\nendstream'


def pdf(payload, dictionary=b'/ColorSpace /DeviceRGB /BitsPerComponent 8', *,
        filters=b'/JPXDecode', width=2, inline=False, mask=None):
    image = (b'/Type /XObject /Subtype /Image /Width ' + str(width).encode() + b' /Height 2 ' +
             dictionary + b' /Filter ' + filters + b' /Interpolate false')
    content = b'q 2 0 0 2 0 0 cm /I Do Q'
    if inline:
        content = b'q 2 0 0 2 0 0 cm BI /W 2 /H 2 /CS /RGB /BPC 8 /F /JPXDecode ID\n' + payload + b'\nEI Q'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2 2] /Resources << /XObject << /I 5 0 R >> >> /Contents 4 0 R >>',
               stream(b'', content), stream(image, payload)]
    if mask is not None:
        objects.append(stream(b'/Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 /Interpolate false', mask))
    output = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{number} 0 obj\n'.encode() + body + b'\nendobj\n')
    xref = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(output)


def encoded(mode, samples, raw=False):
    if mode == 'I;16':
        image = Image.frombytes(mode, (2, 2), struct.pack('<4H', *samples))
    else:
        image = Image.new(mode, (2, 2))
        image.putdata(samples)
    destination = io.BytesIO()
    image.save(destination, format='JPEG2000', irreversible=False, num_resolutions=1, no_jp2=raw)
    result = destination.getvalue()
    with Image.open(io.BytesIO(result)) as reopened:
        require(reopened.size == (2, 2) and list(reopened.getdata()) == samples, 'Pillow lossless source verification failed')
    return result


def change_siz(payload, offset, value):
    marker = payload.find(b'\xff\x51')
    require(marker >= 0 and len(payload) > marker + offset, 'generated codestream has no SIZ field')
    altered = bytearray(payload)
    altered[marker + offset] = value
    return bytes(altered)


def jp2_boxes(payload):
    offset = 0
    while offset < len(payload):
        require(len(payload) - offset >= 8, 'truncated JP2 box header')
        size, kind = struct.unpack_from('>I4s', payload, offset)
        size = size or len(payload) - offset
        require(8 <= size <= len(payload) - offset, 'invalid generated JP2 box length')
        yield kind, payload[offset + 8:offset + size]
        offset += size


def jp2_metadata(payload):
    marker = payload.find(b'\xff\x51')
    require(marker >= 0 and marker + 40 <= len(payload), 'missing JP2 SIZ component declaration')
    definitions = [body.hex() for kind, header in jp2_boxes(payload) if kind == b'jp2h'
                   for subkind, body in jp2_boxes(header) if subkind == b'cdef']
    return {'components': struct.unpack_from('>H', payload, marker + 38)[0], 'cdef_boxes': definitions}


def alpha_cdef(payload):
    require(jp2_metadata(payload) == {'components': 4, 'cdef_boxes': []}, 'RGBA mismatch fixture must have four components and no CDEF')
    definitions = struct.pack('>H', 4) + b''.join(struct.pack('>HHH', channel, 0, channel + 1) for channel in range(3))
    definitions += struct.pack('>HHH', 3, 1, 0)  # Channel 3 is unassociated whole-image alpha.
    cdef = struct.pack('>I4s', len(definitions) + 8, b'cdef') + definitions
    output = bytearray()
    for kind, body in jp2_boxes(payload):
        if kind == b'jp2h':
            body += cdef
        output.extend(struct.pack('>I4s', len(body) + 8, kind) + body)
    result = bytes(output)
    require(jp2_metadata(result) == {'components': 4, 'cdef_boxes': [definitions.hex()]}, 'explicit RGBA CDEF was not installed')
    with Image.open(io.BytesIO(result)) as image:
        require(image.mode == 'RGBA' and list(image.getdata()) == [(*color, 128) for color in RGB],
                'Pillow did not independently accept the explicit RGBA CDEF fixture')
    return result


def generate(root):
    require(features.check('jpg_2000'), 'Pillow requires its independent JPEG2000 codec')
    rgb = encoded('RGB', RGB)
    gray = encoded('L', GRAY)
    gray_raw = encoded('L', GRAY, True)
    indices = encoded('L', [0, 1, 2, 3])
    indices_raw = encoded('L', [0, 1, 2, 3], True)
    rgba = encoded('RGBA', [(*color, 128) for color in RGB])
    rgba_with_cdef = alpha_cdef(rgba)
    gray16 = encoded('I;16', [0, 21845, 43690, 65535])
    palette = b'/ColorSpace [/Indexed /DeviceRGB 3 <ff000000ff000000ffffffff>] /BitsPerComponent 8 /Decode [0 255]'
    gray_dict = b'/ColorSpace /DeviceGray /BitsPerComponent 8'
    cases = []

    def add(name, data, expected=None, statuses=None, off_statuses=None, **kwargs):
        path = root / (name + '.pdf')
        raw = pdf(data, **kwargs)
        path.write_bytes(raw)
        (root / (name + '.jpx')).write_bytes(data)
        cases.append({'name': name, 'pdf': path.name, 'pdf_sha256': sha(raw), 'payload_sha256': sha(data),
                      'expected_rgb': expected, 'on_statuses': [OK] if expected is not None else statuses,
                      'off_statuses': [UNSUPPORTED] if off_statuses is None else off_statuses})

    gray_rgb = [(value, value, value) for value in GRAY]
    add('gray-jp2', gray, gray_rgb, dictionary=gray_dict)
    add('gray-j2k', gray_raw, gray_rgb, dictionary=gray_dict)
    add('gray-decode-ignored', gray, gray_rgb, dictionary=gray_dict + b' /Decode [1 0]')
    add('gray16-jp2', gray16, gray_rgb, dictionary=b'/ColorSpace /DeviceGray /BitsPerComponent 16')
    add('rgb-jp2', rgb, RGB)
    add('rgb-ascii85-terminal-jpx', base64.a85encode(rgb, adobe=False) + b'~>', RGB,
        filters=b'[/ASCII85Decode /JPXDecode]')
    add('indexed-jp2-decode-0-255', indices, RGB, dictionary=palette)
    add('indexed-j2k-decode-0-255', indices_raw, RGB, dictionary=palette)
    add('indexed-jp2-reversed-decode-ignored', indices, RGB,
        dictionary=palette.replace(b'/Decode [0 255]', b'/Decode [255 0]'))
    add('rgb-softmask', rgb, [(255, 255, 255), RGB[1], RGB[2], (255, 255, 255)],
        dictionary=b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /SMask 6 0 R', mask=bytes([0, 255, 255, 0]))
    add('rgb-color-key-mask', rgb, [(255, 255, 255), RGB[1], RGB[2], RGB[3]],
        dictionary=b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Mask [255 255 0 0 0 0]')
    add('malformed', b'not a JPEG2000 codestream', statuses=[FORMAT])
    add('truncated', gray_raw[:len(gray_raw)//2], statuses=[FORMAT], dictionary=gray_dict)
    add('dimensions-mismatch', gray, statuses=[FORMAT], dictionary=gray_dict, width=3)
    add('components-mismatch', gray, statuses=[FORMAT])
    add('precision-signed8', change_siz(gray_raw, 40, 0x87), statuses=[UNSUPPORTED], dictionary=gray_dict)
    add('precision32', change_siz(gray_raw, 40, 31), statuses=[FORMAT, UNSUPPORTED], dictionary=gray_dict)
    add('subsampled-component', change_siz(encoded('RGB', RGB, True), 44, 2), statuses=[UNSUPPORTED])
    add('rgba-components-mismatch', rgba, statuses=[FORMAT])
    add('embedded-alpha-cdef', rgba_with_cdef, statuses=[UNSUPPORTED])
    add('jpx-not-last-filter', rgb, statuses=[FORMAT], off_statuses=[FORMAT], filters=b'[/JPXDecode /ASCII85Decode]')
    add('non-null-decode-parms', rgb, statuses=[FORMAT], off_statuses=[FORMAT],
        dictionary=b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /DecodeParms << /Unused 1 >>')
    add('inline-jpx', rgb, statuses=[FORMAT], off_statuses=[FORMAT], inline=True)
    add('stencil-jpx', gray, statuses=[FORMAT], off_statuses=[FORMAT], dictionary=b'/ImageMask true /BitsPerComponent 1')
    return cases


def run(command, destination, timeout=60):
    result = subprocess.run([str(item) for item in command], capture_output=True, timeout=timeout)
    destination.with_suffix('.stdout').write_bytes(result.stdout)
    destination.with_suffix('.stderr').write_bytes(result.stderr)
    return result


def image_pixels(path):
    with Image.open(path) as image:
        require(image.size == (2, 2), 'rendered image dimensions differ from the known 2x2 page')
        return list(image.convert('RGB').getdata())


def inspect_artifact(artifact_id, digest):
    """Read retained tiny evidence in Actions without altering its expectations."""
    require(artifact_id > 0 and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
            'artifact ID and complete lowercase ZIP SHA-256 required')
    raw = subprocess.check_output(['gh', 'api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/artifacts/{artifact_id}/zip'])
    require(sha(raw) == digest, 'retained diagnostic ZIP digest differs')
    observations = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for case in ('gray-jp2', 'rgb-jp2', 'indexed-jp2-decode-0-255', 'rgb-softmask', 'gray-decode-ignored',
                     'gray16-jp2', 'indexed-jp2-reversed-decode-ignored', 'embedded-alpha',
                     'rgba-components-mismatch', 'embedded-alpha-cdef'):
            pdf_names = [name for name in archive.namelist() if name.endswith('/' + case + '.pdf')]
            if not pdf_names:
                continue
            require(len(pdf_names) == 1, 'retained diagnostic PDF duplicated')
            observation = {'case': case}
            for filename in ('page-0.ppm', 'poppler.ppm', 'reference.stderr', 'native.stderr'):
                names = [name for name in archive.namelist() if name.endswith('/' + case + '/' + filename)]
                require(len(names) <= 1, 'duplicate diagnostic member')
                if not names:
                    continue
                content = archive.read(names[0])
                if filename.endswith('.ppm'):
                    with Image.open(io.BytesIO(content)) as image:
                        require(image.size in ((2, 2), (20, 20)), 'diagnostic page dimensions changed')
                        converted = image.convert('RGB')
                        pixels = (list(converted.getdata()) if image.size == (2, 2) else
                                  [converted.getpixel(point) for point in ((5, 5), (15, 5), (5, 15), (15, 15))])
                        observation[filename] = {'sha256': sha(content), 'dimensions': image.size, 'pixels': pixels}
                else:
                    observation[filename] = content.decode('utf-8', errors='replace')[:4096]
            payload_names = [name for name in archive.namelist() if name.endswith('/' + case + '.jpx')]
            if case in ('embedded-alpha', 'rgba-components-mismatch', 'embedded-alpha-cdef'):
                require(len(payload_names) == 1, 'retained alpha payload missing or duplicated')
                observation['jp2_metadata'] = jp2_metadata(archive.read(payload_names[0]))
            else:
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root / 'source.pdf'
                    source.write_bytes(archive.read(pdf_names[0]))
                    rendered = run(['pdftoppm', '-r', '720', '-f', '1', '-singlefile', '-aa', 'no', '-aaVector', 'no',
                                    source, root / 'high'], root / 'reference-high')
                    require(rendered.returncode == 0, 'higher resolution reference diagnostic failed')
                    with Image.open(root / 'high.ppm') as image:
                        require(image.size == (20, 20), 'higher resolution reference dimensions changed')
                        pixels = image.convert('RGB')
                        coordinates = (0, 5, 15, 19)
                        observation['reference_720dpi_grid'] = [{'x': x, 'y': y, 'rgb': pixels.getpixel((x, y))}
                                                               for y in coordinates for x in coordinates]
            observations.append(observation)
    print(json.dumps({'diagnostic_only': True, 'artifact_id': artifact_id, 'zip_sha256': digest,
                      'observations': observations}, allow_nan=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--expect-off', action='store_true')
    parser.add_argument('--inspect-artifact', type=int)
    parser.add_argument('--artifact-digest')
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'JPX integration runs only in cloud CI')
    if args.inspect_artifact is not None:
        return inspect_artifact(args.inspect_artifact, args.artifact_digest or '')
    require(args.binary is not None and args.font is not None and args.output is not None and
            args.binary.is_file() and args.font.is_file(), 'installed consumer binary, font and output are required')
    require(not args.output.exists(), 'output directory already exists')
    args.output.mkdir(parents=True)
    cases = generate(args.output)
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    plan = {'schema': 1, 'source_sha': source, 'binary_sha256': sha(args.binary.read_bytes()),
            'font_sha256': sha(args.font.read_bytes()), 'expected_off': args.expect_off,
            'plan_written_before_first_engine_execution': True,
            'sanitizer_policy': 'reject native sanitizer findings even when a negative case expects nonzero exit',
            'independent_reference': {'program': 'pdftoppm', 'dpi': 720, 'dimensions': [20, 20],
                                      'centers': [[5, 5], [15, 5], [5, 15], [15, 15]], 'interior_radius': 1,
                                      'comparison': 'exact known source values throughout each 3x3 interior'},
            'case_count': len(cases), 'cases': cases}
    write_json(args.output / 'plan.json', plan)
    frozen = sha((args.output / 'plan.json').read_bytes())
    report = {'schema': 1, 'source_sha': source, 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'expected_off': args.expect_off,
              'plan_sha256': frozen, 'accepted': False, 'results': [], 'problems': []}
    for case in cases:
        result = {'name': case['name'], 'passed': False}
        folder = args.output / case['name']
        folder.mkdir()
        try:
            path = args.output / case['pdf']
            require(sha(path.read_bytes()) == case['pdf_sha256'], 'planned PDF changed')
            native = run([args.binary.resolve(), 'pdf', path.resolve(), args.font.resolve(), folder.resolve(), '0'], folder / 'native')
            stderr = native.stderr.decode('utf-8', errors='replace')
            require(not any(marker in stderr for marker in ('ERROR: AddressSanitizer', 'ERROR: LeakSanitizer',
                        'runtime error:', 'SUMMARY: UndefinedBehaviorSanitizer', 'AddressSanitizer:DEADLYSIGNAL')),
                    'native sanitizer reported an error')
            lines = native.stdout.decode('utf-8').splitlines()
            require(len(lines) == 1, 'installed consumer must return exactly one JSON report')
            observed = json.loads(lines[0])
            status = observed['status']
            result.update(exit_code=native.returncode, status=status, stage=observed['stage'])
            expected = case['off_statuses'] if args.expect_off else case['on_statuses']
            require(status in expected, 'public SDK status differs from frozen plan')
            ppm = folder / 'page-0.ppm'
            if expected == [OK]:
                require(native.returncode == 0 and observed['success'] is True and observed['stage'] == 'complete' and
                        observed['page_count'] == 1 and len(observed['samples']) == 50 and ppm.is_file(),
                        'public SDK did not complete every actual page render')
                expected_rgb = [tuple(value) for value in case['expected_rgb']]
                pixels = image_pixels(ppm)
                result['native_pixels'] = pixels
                require(pixels == expected_rgb, 'native pixels differ from independently known source values')
                reference = run(['pdftoppm', '-r', '720', '-f', '1', '-singlefile', '-aa', 'no', '-aaVector', 'no',
                                 path.resolve(), (folder / 'poppler').resolve()], folder / 'reference')
                reference_path = folder / 'poppler.ppm'
                require(reference.returncode == 0 and reference_path.is_file(), 'independent Poppler rendering failed')
                result['reference_sha256'] = sha(reference_path.read_bytes())
                with Image.open(reference_path) as reference_image:
                    require(reference_image.size == (20, 20), 'independent reference dimensions changed')
                    reference_image = reference_image.convert('RGB')
                    centers = plan['independent_reference']['centers']
                    reference_pixels = [reference_image.getpixel(tuple(point)) for point in centers]
                    result['reference_pixels'] = reference_pixels
                    for (x, y), expected_pixel in zip(centers, expected_rgb):
                        require(all(reference_image.getpixel((x + dx, y + dy)) == expected_pixel
                                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)),
                                'Poppler interior pixels differ from known source values')
                require(reference_pixels == expected_rgb, 'Poppler pixels differ from known source values')
                result.update(ppm_sha256=sha(ppm.read_bytes()), reference_sha256=sha(reference_path.read_bytes()),
                              exact_source_pixels=True, exact_poppler_interiors=True)
            else:
                require(native.returncode != 0 and observed['success'] is False and not list(folder.glob('*.ppm')),
                        'rejected PDF produced success or a partial rendered page')
                result['no_ppm'] = True
            result['passed'] = True
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            result['problem'] = str(error)
            report['problems'].append(case['name'] + ': ' + str(error))
        report['results'].append(result)
    require(sha((args.output / 'plan.json').read_bytes()) == frozen, 'frozen expectation plan changed')
    report.update(cases=len(cases), passed=sum(item['passed'] for item in report['results']), failed=len(report['problems']), skipped=0)
    report['accepted'] = report['failed'] == 0 and report['passed'] == report['cases']
    write_json(args.output / 'report.json', report)
    print(json.dumps(report, allow_nan=False))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
