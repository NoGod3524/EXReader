#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PPT M6: compare committed PowerPoint COM geometry/colors to public ABI pixels.

Only the standard library is used. The independent oracle is recorded by the
fixture authoring script, never inferred from engine pixels. Coverage and PNG
encoding share the existing PPTX M6 implementation. A length-preserving CFB
mutation disables text atoms to distinguish glyphs from fills and photographs.
"""
import argparse
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
import sys
import time

from pptx_real_matrix import Paint, Raster, Region, metrics
from test_pptx_skeleton import Bitmap, Engine, Error

HERE = Path(__file__).resolve().parent / 'fixtures/ppt-real'
FREE, END = 0xffffffff, 0xfffffffe


def font_warnings_only(message):
    """Accept each font field separately; a fallback cannot hide other warnings."""
    if not message:
        return True
    if not message.startswith('PPT warning: '):
        return False
    for field in message.removeprefix('PPT warning: ').split(';'):
        field = field.strip()
        if not field:
            continue
        if re.fullmatch(r'font fallback=[^;]+', field):
            continue
        if re.fullmatch(r'glyph .+ U\+[0-9A-F]{4,6} (?:missing|fallback)', field):
            continue
        # The ABI's 256-byte buffer can truncate a long host-glyph list, cutting
        # a field mid-codepoint (e.g. `U+4E0`). The textless document is also
        # checked, exposing subsequent non-font fields, so a truncated `glyph …U+`
        # tail is host-font noise rather than a real warning.
        # A truncated glyph list can end mid-codepoint (`U+4E0`) or right after a
        # complete codepoint with no state word. Either way it is host-font noise.
        if field.startswith('glyph ') and ' U+' in field:
            if re.fullmatch(r'glyph .+ U\+[0-9A-F]{1,6}(?: [a-z]+)?', field):
                continue
            if len(message.encode('utf-8')) >= 250:
                continue
        return False
    return True


class Compound:
    """Map a CFB stream's logical bytes to file offsets, including mini streams."""
    def __init__(self, data):
        self.data = data
        if data[:8] != bytes.fromhex('D0CF11E0A1B11AE1') or len(data) < 512:
            raise ValueError('invalid CFB header')
        self.sector = 1 << self.u16(30)
        if self.sector not in (512, 4096) or len(data) % self.sector:
            raise ValueError('invalid CFB sector size')
        self.sectors = len(data)//self.sector-1
        fat_ids = [i for i in struct.unpack_from('<109I', data, 76) if i != FREE]
        difat, seen = self.u32(68), set()
        for _ in range(self.u32(72)):
            if difat in seen:
                raise ValueError('cyclic DIFAT')
            seen.add(difat)
            start = self.offset(difat)
            entries = struct.unpack_from('<'+'I'*(self.sector//4), data, start)
            fat_ids.extend(i for i in entries[:-1] if i != FREE)
            difat = entries[-1]
        if len(fat_ids) != self.u32(44):
            raise ValueError('CFB FAT count mismatch')
        self.fat = []
        for index in fat_ids:
            self.fat.extend(struct.unpack_from('<'+'I'*(self.sector//4), data, self.offset(index)))
        directory = self.read(self.chain(self.u32(48), self.fat, self.sector))
        self.entries = []
        for at in range(0, len(directory), 128):
            if directory[at+66] not in (2, 5):
                continue
            length = struct.unpack_from('<H', directory, at+64)[0]
            if not 2 <= length <= 64 or length % 2:
                raise ValueError('invalid CFB directory name')
            name = directory[at:at+length-2].decode('utf-16le')
            start, size = struct.unpack_from('<IQ', directory, at+116)
            if self.u16(26) == 3:
                size &= 0xffffffff
            self.entries.append((name, directory[at+66], start, size))
        roots = [e for e in self.entries if e[1] == 5]
        if len(roots) != 1:
            raise ValueError('missing CFB root')
        _, _, root, root_size = roots[0]
        self.root_map = self.chain(root, self.fat, self.sector)[:root_size] if root_size else []
        mini_count = self.u32(64)
        mini_map = self.chain(self.u32(60), self.fat, self.sector) if mini_count else []
        mini_data = self.read(mini_map[:mini_count*self.sector])
        self.mini = list(struct.unpack('<'+'I'*(len(mini_data)//4), mini_data))

    def u16(self, at):
        return struct.unpack_from('<H', self.data, at)[0]

    def u32(self, at):
        return struct.unpack_from('<I', self.data, at)[0]

    def offset(self, index):
        if not 0 <= index < self.sectors:
            raise ValueError('CFB sector outside file')
        return (index+1)*self.sector

    def chain(self, index, links, block, root=None):
        result, seen = [], set()
        while index != END:
            if not 0 <= index < len(links) or index in seen:
                raise ValueError('invalid/cyclic CFB chain')
            seen.add(index)
            if root is None:
                start = self.offset(index)
                result.extend(range(start, start+block))
            else:
                start = index*block
                if start+block > len(root):
                    raise ValueError('mini sector outside root stream')
                result.extend(root[start:start+block])
            index = links[index]
        return result

    def read(self, offsets):
        return bytes(self.data[i] for i in offsets)

    def stream_map(self, name):
        entries = [e for e in self.entries if e[0] == name and e[1] == 2]
        if len(entries) != 1:
            raise ValueError(f'CFB stream missing/ambiguous: {name}')
        _, _, start, size = entries[0]
        if not size:
            return []
        offsets = (self.chain(start, self.mini, 64, self.root_map) if size < 4096
                   else self.chain(start, self.fat, self.sector))
        if len(offsets) < size:
            raise ValueError('truncated CFB stream')
        return offsets[:size]


def text_atom_offsets(data, begin=0, end=None, depth=0):
    """Visit record containers, including outline lists and drawing textboxes."""
    end = len(data) if end is None else end
    if depth > 64:
        raise ValueError('PPT record recursion limit')
    at = begin
    while at < end:
        if end-at < 8:
            raise ValueError('truncated PPT record header')
        packed, kind, length = struct.unpack_from('<HHI', data, at)
        following = at+8+length
        if following > end:
            raise ValueError('PPT record outside container')
        if kind in (0x0fa0, 0x0fa8):
            yield at+2
        elif packed & 15 == 15 or (packed & 15 == 0 and kind in (0x3e8, 0x3ee, 0xff0)):
            yield from text_atom_offsets(data, at+8, following, depth+1)
        at = following


def without_text(data):
    """Disable only text atom types; retain all offsets, lengths and style runs.

    Replacing characters with spaces leaves paragraph bullets behind. Renaming
    the two text atoms removes all glyphs without changing any CFB/persist offset
    or causing the original paragraph/character run lengths to become invalid.
    """
    compound = Compound(data)
    mapping = compound.stream_map('PowerPoint Document')
    stream = compound.read(mapping)
    output = bytearray(data)
    for at in text_atom_offsets(stream):
        for i, value in enumerate(struct.pack('<H', 0x7ffe)):
            output[mapping[at+i]] = value
    return bytes(output)


class Reference:
    """COM-authored shape metadata and twelve predetermined RGB samples."""
    def __init__(self, oracle, slide=0):
        self.width, self.height = oracle['width'], oracle['height']
        self.background = Paint('solid', (*oracle.get('background', [255, 255, 255]), 255))
        self.regions, self.frames, self.text_boxes = [], [], []
        item = oracle['slides'][slide]
        for shape in item['regions']:
            l, t, r, b = shape['bounds']
            if not all(math.isfinite(v) for v in (l, t, r, b)) or l > r or t > b:
                raise ValueError('invalid oracle shape bounds')
            fill = shape.get('fill')
            paint = Paint('solid', (*fill, 255)) if fill is not None else None
            region = Region(shape['name'], (1, 0, 0, 1, l, t), r-l, b-t,
                            shape.get('geometry', 'rect'), paint, bool(shape.get('text')),
                            shape.get('stroke', 0))
            self.regions.append(region)
            self.frames.append(region.bounds)
            if region.text:
                self.text_boxes.append(tuple(shape.get('text_bounds', region.bounds)))
        self._samples = [(int(x), int(y), tuple(rgb)) for x, y, *rgb in item['samples']]
        if len(self._samples) != 12 or len({(x, y) for x, y, _ in self._samples}) != 12:
            raise ValueError('oracle needs twelve distinct color samples')
        if any(not (0 <= x < self.width and 0 <= y < self.height) or len(rgb) != 3 or
               any(not 0 <= c <= 255 for c in rgb) for x, y, rgb in self._samples):
            raise ValueError('invalid oracle color sample')

    def samples(self):
        return list(self._samples)

    def background_image(self, size):
        return Raster.new(size, self.background.value[:3])


def opened(engine, path=None, data=None):
    doc, error = C.c_void_p(), Error()
    if path is not None:
        status = engine.lib.exr_fixed_open(str(path).encode('utf-8'), None, C.byref(doc), C.byref(error))
    else:
        status = engine.lib.exr_fixed_open_memory(10, data, len(data), None, C.byref(doc), C.byref(error))
    return status, error.code, error.message.decode('utf-8', errors='replace'), doc


def render(engine, doc, page):
    bitmap, error = Bitmap(), Error()
    start = time.perf_counter_ns()
    status = engine.lib.exr_fixed_render(doc, page, 1, None, C.byref(bitmap), C.byref(error))
    elapsed = (time.perf_counter_ns()-start)/1e6
    try:
        message = error.message.decode('utf-8', errors='replace')
        if status or error.code or not font_warnings_only(message):
            raise ValueError(f'render status={status} code={error.code}: {message!r}')
        if bitmap.channels != 4 or not bitmap.pixels:
            raise ValueError('invalid RGBA bitmap')
        rgba = C.string_at(bitmap.pixels, bitmap.stride*bitmap.height)
        rows = b''.join(rgba[y*bitmap.stride:y*bitmap.stride+bitmap.width*4] for y in range(bitmap.height))
        rgb = bytearray(bitmap.width*bitmap.height*3)
        for channel in range(3):
            rgb[channel::3] = rows[channel::4]
        return Raster(bitmap.width, bitmap.height, rgb), elapsed
    finally:
        engine.lib.exr_bitmap_free(C.byref(bitmap))


def check_file(engine, path, entry, output, repeats):
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    status, code, warning, doc = opened(engine, path=path)
    result = dict(file=path.name, sha256=sha, status=status, code=code, warning=warning, pages=[], ok=False)
    print(f'{path.name} open status={status} code={code} warning={warning!r}')
    baseline = None
    try:
        if entry.get('sha256') != sha or entry.get('bytes') != len(data):
            raise ValueError('manifest SHA256/size differs from corpus bytes')
        if 'expected_status' in entry:
            memory_status, memory_code, memory_warning, memory_doc = opened(engine, data=data)
            try:
                expected = entry['expected_status']
                result['ok'] = (status == code == memory_status == memory_code == expected == 5 and
                                not doc.value and not memory_doc.value and bool(warning) and bool(memory_warning))
                result.update(error_name='EXR_FORMAT', memory_status=memory_status, memory_code=memory_code,
                              memory_warning=memory_warning)
                print(f"{path.name} bad={'ok' if result['ok'] else 'FAIL'} EXR_FORMAT file={status}/{code} memory={memory_status}/{memory_code} message={warning!r}")
                return result
            finally:
                if memory_doc.value:
                    engine.lib.exr_fixed_free(memory_doc)
        if status or code or not doc.value:
            raise ValueError(f'open failed status={status} code={code}')
        oracle = entry['oracle']
        count = C.c_size_t()
        pages = engine.lib.exr_fixed_pages(doc, C.byref(count))
        reported_slides = entry['powerpoint_reported_slides']
        result['engine_slides'], result['powerpoint_slides'] = count.value, reported_slides
        file_ok = count.value == len(oracle['slides']) == entry['slides'] == reported_slides and font_warnings_only(warning)
        print(f'{path.name} slides engine={count.value} powerpoint-com={reported_slides} oracle={len(oracle["slides"])} warnings={"ok" if font_warnings_only(warning) else "FAIL"}')
        clean_status, clean_code, clean_warning, baseline = opened(engine, data=without_text(data))
        if clean_status or clean_code or not baseline.value or not font_warnings_only(clean_warning):
            raise ValueError(f'textless open failed: {clean_status}/{clean_code} {clean_warning!r}')
        clean_count = C.c_size_t()
        engine.lib.exr_fixed_pages(baseline, C.byref(clean_count))
        if clean_count.value != count.value:
            raise ValueError('textless baseline page count changed')
        for index in range(len(oracle['slides'])):
            page = dict(slide=index+1, ok=False)
            result['pages'].append(page)
            try:
                if index >= count.value:
                    raise ValueError('engine page missing')
                reference = Reference(oracle, index)
                image, ms = render(engine, doc, index)
                clean, _ = render(engine, baseline, index)
                expected_size = math.ceil(reference.width), math.ceil(reference.height)
                if image.size != expected_size or clean.size != image.size:
                    raise ValueError(f'bitmap dimensions={image.size}, reference={expected_size}')
                page.update(metrics(reference, image, clean))
                page['geometry_bounds'] = list(pages[index].geometry.bounds)
                if any(abs(a-b) > .01 for a, b in zip(page['geometry_bounds'], (0, 0, reference.width, reference.height))):
                    page['ok'] = False
                    page['geometry_error'] = 'public page geometry differs from PowerPoint dimensions'
                measures = [ms]
                for _ in range(repeats-1):
                    _, elapsed = render(engine, doc, index)
                    measures.append(elapsed)
                page['render_samples_ms'] = measures
                page['render_ms'] = statistics.median(measures)
                print(f'{path.name}#{index+1} coverage={"ok" if page["coverage"] else "FAIL"} color={page["colors"]}/12 text={"ok" if page["text"] else "FAIL"}')
                for check in page['coverage_shapes']:
                    if not check['ok']:
                        print(f'  {check["kind"]} {check["name"]!r}: bbox actual={check["actual_bbox"]} expected={check["expected_bbox"]} glyph_pixels={check["glyph_pixels"]} tolerance=4px')
                for sample in page['samples']:
                    if not sample['ok']:
                        print(f'  color ({sample["x"]},{sample["y"]}) actual={sample["actual"]} expected={sample["expected"]} delta={sample["delta"]}')
                if output:
                    target = output/path.stem
                    target.mkdir(parents=True, exist_ok=True)
                    image.save(target/f'{index+1:02}.png')
                    clean.save(target/f'{index+1:02}-textless.png')
            except Exception as exc:
                page['error'] = str(exc)
                print(f'{path.name}#{index+1} coverage=FAIL color=FAIL/12 text=FAIL error={exc}')
            file_ok &= page['ok']
        result['ok'] = bool(file_ok)
    except Exception as exc:
        result['error'] = str(exc)
        print(f'{path.name} FAIL {exc}')
    finally:
        if baseline and baseline.value:
            engine.lib.exr_fixed_free(baseline)
        if doc.value:
            engine.lib.exr_fixed_free(doc)
    return result


def performance(entries, results):
    """Gate only a same-machine ratio of equally authored single/multi decks."""
    by_stem = {Path(result['file']).stem: (entry, result) for (_, entry), result in zip(entries, results)}
    checks = []
    for (_, entry), result in zip(entries, results):
        if not entry.get('benchmark'):
            continue
        baseline_entry, baseline = by_stem[entry['benchmark_baseline']]
        if baseline_entry['slides'] != 1 or entry['slides'] != 20:
            raise ValueError('performance requires one-slide and twenty-slide documents')
        # Names may differ after COM duplicates a page; painted geometry and
        # samples must still be identical to avoid comparing unlike workloads.
        def signature(oracle, slide):
            regions = [{k: v for k, v in region.items() if k != 'name'} for region in slide['regions']]
            return oracle['width'], oracle['height'], oracle.get('background'), regions, slide['samples'], slide.get('text_content')
        expected = signature(baseline_entry['oracle'], baseline_entry['oracle']['slides'][0])
        if any(signature(entry['oracle'], slide) != expected for slide in entry['oracle']['slides']):
            raise ValueError('single/multi benchmark pages differ in authored geometry/colors')
        single = [p['render_ms'] for p in baseline['pages']]
        multi = [p['render_ms'] for p in result['pages']]
        if len(single) != 1 or len(multi) != 20:
            raise ValueError('performance pages missing')
        t1, t20 = statistics.median(single), statistics.median(multi)
        maximum = max(t for r in (baseline, result) for p in r['pages'] for t in p['render_samples_ms'])
        check = dict(file=result['file'], baseline=baseline['file'], T1_ms=t1, T20_ms=t20,
                     ratio=t20/t1, ratio_limit=3.0, max_ms=maximum, max_under_200ms=maximum < 200,
                     ok=t20 <= t1*3.0)
        checks.append(check)
        print(f'PERFORMANCE T1={t1:.3f}ms T20={t20:.3f}ms ratio={t20/t1:.3f} limit=3.000 result={"ok" if check["ok"] else "FAIL"} max={maximum:.3f}ms max<200ms={"yes" if maximum < 200 else "no"} (observed; relative gate only)')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--fixtures', type=Path, default=HERE)
    parser.add_argument('--output', type=Path, help='write JSON and actual/textless PNGs')
    parser.add_argument('--file', help='select one fixture stem')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    entries = [(m, json.loads(m.read_text(encoding='utf-8'))) for m in sorted(args.fixtures.glob('*/manifest.json'))]
    if args.file:
        entries = [(m, e) for m, e in entries if Path(e['file']).stem == args.file]
        if len(entries) != 1:
            parser.error('--file must select exactly one fixture')
    elif sum('expected_status' not in e for _, e in entries) != 8 or sum('expected_status' in e for _, e in entries) != 2:
        parser.error('corpus requires eight valid presentations and two malformed files')
    engine = Engine(args.library.resolve())
    results = [check_file(engine, m.parent/e['file'], e, args.output, args.repeats) for m, e in entries]
    checks = []
    perf_error = None
    if not args.file:
        try:
            checks = performance(entries, results)
            if len(checks) != 1:
                raise ValueError('corpus requires exactly one paired performance benchmark')
        except Exception as exc:
            perf_error = str(exc)
            print(f'PERFORMANCE FAIL {exc}')
    summary = dict(python=sys.version.split()[0], platform=sys.platform,
                   library=str(args.library.resolve()), library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
                   coverage_tolerance_px=4, color_tolerance_per_channel=4, color_pass_minimum=10,
                   coverage_definition=dict(filled='non-background ink bbox covers geometry bbox',
                                            text='glyph pixels > 0; glyph bbox contained in shape bbox',
                                            outline='non-background pixels in shape region plus 4px',
                                            backdrop='independent COM-authored solid background'),
                   files=len(results), passed=sum(r['ok'] for r in results), performance=checks,
                   performance_error=perf_error, results=results)
    print(f'MATRIX files={len(results)} passed={summary["passed"]} failed={len(results)-summary["passed"]}')
    if args.output:
        (args.output/'matrix.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0 if all(r['ok'] for r in results) and not perf_error and all(p['ok'] for p in checks) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())


