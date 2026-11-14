"""M3 COM pixel oracles and independent malformed OfficeArt cases (stdlib)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zlib

from check_ppt import compound, record
from check_ppt_shapes import Pixels, document_header, group, prop_table, shape, slide_record


def stream(path, name="PowerPoint Document"):
    """Extract a regular stream from these committed CFB fixtures, independently."""
    raw = path.read_bytes()
    sector = 1 << struct.unpack_from("<H", raw, 30)[0]
    ids = struct.unpack_from("<109I", raw, 76)
    fat = []
    for index in ids:
        if index < 0xFFFFFFFA:
            fat.extend(struct.unpack_from("<" + "I" * (sector // 4), raw, (index + 1) * sector))

    def chain(index):
        blocks, seen = [], set()
        while index < 0xFFFFFFFA:
            assert index not in seen
            seen.add(index)
            blocks.append(raw[(index + 1) * sector:(index + 2) * sector])
            index = fat[index]
        return b"".join(blocks)

    directory = chain(struct.unpack_from("<I", raw, 48)[0])
    for offset in range(0, len(directory), 128):
        length = struct.unpack_from("<H", directory, offset + 64)[0]
        if directory[offset:offset + length - 2].decode("utf-16le") == name:
            size = struct.unpack_from("<I", directory, offset + 120)[0]
            assert size >= 4096, "helper only reads committed regular document streams"
            return chain(struct.unpack_from("<I", directory, offset + 116)[0])[:size]
    raise AssertionError(name)


def records(data, at=0, end=None, parents=()):
    end = len(data) if end is None else end
    while at < end:
        packed, kind, size = struct.unpack_from("<HHI", data, at)
        payload, next_at = at + 8, at + 8 + size
        assert next_at <= end
        yield kind, packed >> 4, data[payload:next_at], parents
        if packed & 15 == 15:
            yield from records(data, payload, next_at, parents + (kind,))
        at = next_at


def presentation(drawing, entries=b"", master=b""):
    header = document_header(1)
    count = sum(kind == 0xF007 for kind, _, _, _ in records(entries))
    drawing_group = record(0x40B, record(0xF000, record(0xF001, entries, 15, count), 15), 15)
    return compound(record(0x3E8, header[8:] + drawing_group, 15) + master + slide_record(drawing))


def picture(index=1, box=(80, 80, 400, 50), child=False, flip=False):
    extra = prop_table([(0x4104, index)])
    if flip:
        extra += record(0xF00A, struct.pack("<II", 1025, (0xA02 if child else 0xA00) | 0x40), 2, 75)
    return shape(box=box, kind=75, fill=False, child=child, extra=extra)


def bse(data, kind=0xF01E, dual=False):
    instance = (0x6E0 if kind in (0xF01E, 0xF02B) else 0x46A) + int(dual)
    blip = record(kind, bytes(32 if dual else 16) + b"\xff" + data, 0, instance)
    header = struct.pack("<BB16sHIIIBBBB", 6, 6, bytes(16), 0xFF, len(blip), 1, 0, 0, 0, 0, 0)
    return record(0xF007, header + blip, 2, 6)


def gradient(stops=None, back=True, kind=1):
    props = [(0x180, 7)]
    if back:
        props.append((0x183, 0xFF0000))
    extra = prop_table(props)
    if stops is not None:
        array = struct.pack("<HHH", len(stops), len(stops), 8)
        array += b"".join(struct.pack("<II", color, position) for color, position in stops)
        extra += record(0xF00B, struct.pack("<HI", 0x8197, len(array)) + array, 3, 1)
    return shape(box=(80, 80, 400, 100), kind=kind, extra=extra)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("group")
    args = parser.parse_args()
    manifest = json.loads((args.fixtures / "manifest.json").read_text(encoding="utf-8"))
    fixtures = {item["case"]: item for item in manifest["fixtures"]}
    checks = 0
    with tempfile.TemporaryDirectory(prefix="exr-ppt-fill-") as temp:
        source, output = Path(temp) / "sample.ppt", Path(temp) / "render.ppm"

        def run(data=None, case=None, warning=None, scale=1, memory=False, page=0):
            nonlocal checks
            if case:
                source_file = args.fixtures / fixtures[case]["file"]
                assert hashlib.sha256(source_file.read_bytes()).hexdigest() == fixtures[case]["sha256"]
            else:
                source.write_bytes(data)
                source_file = source
            output.unlink(missing_ok=True)
            command = [str(args.probe.resolve()), str(source_file), str(output), str(page), str(scale)]
            if memory:
                command.append("memory")
            result = subprocess.run(command, capture_output=True, encoding="utf-8", check=True)
            values = dict(line.split("=", 1) for line in result.stdout.splitlines())
            assert values["status"] == "0", result.stdout
            if warning:
                assert "warning" in values["message"].lower() and warning in values["message"], result.stdout
                assert re.search(re.escape(warning) + r"[1-9]\d*", values["message"]), result.stdout
            checks += 1
            print(f"status={values['status']} message={values['message']}")
            return Pixels(output), values

        name = args.group
        if name in ("png", "scale"):
            for scale, memory in ((1, False), (2, True)):
                pixels, _ = run(case=name, scale=scale, memory=memory)
                points = [(81, 105), (180, 105), (280, 105), (380, 105), (478, 105)] if name == "scale" else [(130, 105)]
                actual = [pixels.check((x * scale, y * scale), (0, 255, 0)) for x, y in points]
                print(f"COM {name} scale={scale}: RGB={actual}; maximum error={max(max(abs(a-b) for a,b in zip(rgb,(0,255,0))) for rgb in actual)}")
        elif name == "gradient":
            assert fixtures[name]["stops"] == [{"rgb": [255, 0, 0], "position": 0.0}, {"rgb": [0, 0, 255], "position": 1.0}]
            for scale, memory in ((1, False), (2, True)):
                pixels, _ = run(case=name, scale=scale, memory=memory, warning="gradient-horizontal=")
                positions = [81, 130, 180, 230, 280, 330, 380, 430, 478]
                colors = [pixels.at(x * scale, 130 * scale) for x in positions]
                assert all(colors[i][0] > colors[i+1][0] and colors[i][2] < colors[i+1][2] for i in range(8)), colors
                for x, color in zip(positions, colors):
                    expected = ((1 - (x + .5 / scale - 80) / 400) * 255, 0, (x + .5 / scale - 80) / 400 * 255)
                    assert max(abs(a-b) for a,b in zip(color, expected)) <= 2, (color, expected)
                print(f"COM red->blue scale={scale}: x={positions}; RGB={colors}; monotonic=PASS")
        elif name == "theme":
            raw = stream(args.fixtures / fixtures[name]["file"])
            palettes = [payload for kind, instance, payload, parent in records(raw)
                        if kind == 0x7F0 and instance == 1 and parent and parent[-1] == 0x3F8]
            assert palettes
            accent1 = tuple(palettes[0][16:19])
            assert accent1 == tuple(fixtures[name]["shapes"][0]["master_rgb"])
            for scale, memory in ((1, False), (2, True)):
                pixels, _ = run(case=name, scale=scale, memory=memory)
                for item in fixtures[name]["shapes"]:
                    x, y, width, height = item["bbox_pt"]
                    assert item["rgb"] == item["master_rgb"]
                    actual = pixels.check(((x + width/2) * scale, (y + height/2) * scale), item["master_rgb"], 0)
                    print(f"COM {item['name']}: pixel={actual} master={tuple(item['master_rgb'])}")
                print(f"MainMaster COLOR_SCHEME[4]={accent1}: exact=PASS")
        elif name == "fallback":
            following = shape((0, 0, 255), (520, 80, 100, 50))
            for index in (0, 1, 0xFFFFFFFF):
                pixels, _ = run(presentation(picture(index) + following), warning="pib=")
                actual = pixels.check((280, 105), (204, 204, 204), 0)
                pixels.check((550, 105), (0, 0, 255), 0)
                print(f"invalid pib={index}: pixel={actual}; process survived")
            pixels, values = run(presentation(picture() + following, bse(b"unsupported", 0xF01A)), warning="blip-unsupported=")
            pixels.check((280, 105), (255, 255, 255), 0)
            pixels.check((550, 105), (0, 0, 255), 0)
            assert values["draw_count"] == "1"
            print("unknown blip: shape skipped; process survived")
            pixels, _ = run(presentation(picture() + following, bse(b"broken PNG")), warning="image-decode=")
            pixels.check((280, 105), (204, 204, 204), 0)
            pixels.check((550, 105), (0, 0, 255), 0)
            print("broken PNG: gray fallback; process survived")
            truncated = record(0xF007, bytes(20), 2, 6)
            delayed = record(0xF007, struct.pack("<BB16sHIIIBBBB", 6, 6, bytes(16), 0xFF, 100, 1, 0xFFFFFFFF, 0, 0, 0, 0), 2, 6)
            for label, entry in (("truncated BSE", truncated), ("invalid delayed offset", delayed)):
                pixels, _ = run(presentation(picture() + following, entry), warning="image-decode=")
                pixels.check((280, 105), (204, 204, 204), 0)
                pixels.check((550, 105), (0, 0, 255), 0)
                print(f"{label}: gray fallback; following blue shape=PASS")
        elif name == "blips":
            for kind, suffix in ((0xF01E, "png"), (0xF02B, "png"), (0xF01D, "jpg"), (0xF02A, "jpg")):
                data = (args.fixtures / ("green-100x50." + suffix)).read_bytes()
                for dual in (False, True):
                    pixels, _ = run(presentation(picture(), bse(data, kind, dual)), memory=dual)
                    pixels.check((280, 105), (0, 255, 0))
                    print(f"inline blip 0x{kind:04X} uid_count={2 if dual else 1}: green=PASS")
            png = (args.fixtures / "green-100x50.png").read_bytes()
            entries = bse(b"unknown", 0xF01A) + bse(png)
            pixels, _ = run(presentation(picture(1, (80, 80, 100, 50)) + picture(2, (240, 80, 100, 50)), entries), warning="blip-unsupported=")
            pixels.check((130, 105), (255, 255, 255), 0)
            pixels.check((290, 105), (0, 255, 0), 0)
            print("unsupported BSE retains its index; following pib2 green=PASS")
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
            stripe = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
                      + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\0\0\xff")) + chunk(b"IEND", b""))
            drawing = group(picture(box=(0, 0, 100, 50), child=True, flip=True),
                            ch=(0, 0, 800, 400), box=(80, 80, 400, 100))
            pixels, _ = run(presentation(drawing, bse(stripe)))
            pixels.check((100, 130), (0, 0, 255), 0)
            pixels.check((460, 130), (255, 0, 0), 0)
            print("striped picture: group scale(4,2), horizontal flip gives blue-left/red-right=PASS")
            drawing = shape(box=(80, 80, 100, 50), kind=75, fill=False,
                            extra=prop_table([(0x4104, 1), (0x4186, 0xFFFFFFFF)]))
            drawing += shape(box=(240, 80, 100, 50), extra=prop_table([(0x180, 3), (0x4186, 1)]))
            drawing += shape(box=(400, 80, 100, 50), kind=3, extra=prop_table([(0x180, 3), (0x4186, 1)]))
            drawing += shape(box=(560, 80, 100, 50), fill=False, extra=prop_table([(0x180, 3), (0x4186, 1)]))
            pixels, _ = run(presentation(drawing, bse(png)))
            for x in (130, 290, 450):
                pixels.check((x, 105), (0, 255, 0), 0)
            pixels.check((401, 81), (255, 255, 255), 0)
            pixels.check((610, 105), (255, 255, 255), 0)
            print("picture pib precedence and rectangle/ellipse fillBlip: green=PASS; ellipse clip and explicit noFill=PASS")
        elif name == "gradient-fallback":
            pixels, _ = run(presentation(gradient(back=False)), warning="gradient-missing=")
            for x in (100, 280, 460):
                pixels.check((x, 130), (255, 0, 0), 0)
            print("missing gradient endpoint: solid red=PASS")
            # Two explicit stops override a deliberately different fill/back pair.
            stops = [(0x00FF00, 0), (0x00FFFF, 65536)]
            pixels, _ = run(presentation(gradient(stops)), warning="gradient-horizontal=")
            samples = [pixels.at(x, 130) for x in (81, 280, 478)]
            assert all(rgb[1] == 255 and rgb[2] == 0 for rgb in samples), samples
            assert samples[0][0] < samples[1][0] < samples[2][0], samples
            print(f"fillShadeColors endpoints RGB={samples}")
            for stops in ([], [(0xFF, 0)], [(0xFF, 0), (0xFF0000, 65537)], [(0xFF, 0), (0xFF0000, 0)]):
                pixels, _ = run(presentation(gradient(stops)), warning="gradient-missing=")
                for x in (100, 280, 460):
                    pixels.check((x, 130), (255, 0, 0), 0)
            print("empty/single/out-of-range/duplicate gradient stops: solid red=PASS")
            pixels, _ = run(presentation(gradient(kind=3)), warning="gradient-horizontal=")
            pixels.check((82, 82), (255, 255, 255), 0)
            pixels.check((280, 130), (127, 0, 128), 2)
            left, right = pixels.at(110, 130), pixels.at(450, 130)
            assert left[0] > right[0] and left[2] < right[2], (left, right)
            print("ellipse gradient: white corner, clipped horizontal red->blue fill=PASS")
        elif name == "scheme":
            colors = [(11, 21, 31), (41, 51, 61), (71, 81, 91), (101, 111, 121),
                      (131, 141, 151), (161, 171, 181), (191, 201, 211), (221, 231, 241)]
            palette = b"".join(bytes(rgb) + b"\0" for rgb in colors)
            master = record(0x3F8, record(0x7F0, palette, 0, 1), 15)
            drawing = b"".join(shape(box=(40 + i*80, 80, 60, 50), extra=prop_table([(0x181, 0x08000000 | i)])) for i in range(8))
            pixels, _ = run(presentation(drawing, master=master))
            for i, color in enumerate(colors):
                pixels.check((70 + i*80, 105), color, 0)
            print(f"legacy COLOR_SCHEME indices0..7 RGB={colors}; exact=PASS")
            # Persist ids and slide master ids select the first master even
            # when another MainMaster appears later in physical stream order.
            def two_masters(follow):
                def scheme(color):
                    return record(0x7F0, (bytes(color) + b"\0") * 8, 0, 1)
                master1 = record(0x3F8, scheme((17, 83, 211)), 15)
                master2 = record(0x3F8, scheme((231, 41, 51)), 15)
                master_refs = b"".join(record(0x3F3, struct.pack("<IIIII", pid, 0, 0, sid, 0))
                                       for pid, sid in ((10, 0x80000001), (11, 0x80000002)))
                header = record(0x3E8, document_header(2)[8:] + record(0xFF0, master_refs, 15, 1), 15)
                indirect = shape(extra=prop_table([(0x181, 0x08000004)]))
                slides = []
                for sid, flags in ((0x80000001, 2), (0x80000002, follow)):
                    atom = bytearray(24)
                    struct.pack_into("<I", atom, 12, sid)
                    struct.pack_into("<H", atom, 20, flags)
                    slides.append(record(0x3EE, record(0x3EF, atom) + scheme((71, 191, 31))
                                         + record(0x40C, indirect, 15), 15))
                offsets = [len(header), len(header) + len(master1)]
                slide_offsets = [offsets[1] + len(master2), offsets[1] + len(master2) + len(slides[0])]
                directory = struct.pack("<III", 2 << 20 | 10, *offsets)
                directory += struct.pack("<III", 2 << 20 | 1, *slide_offsets)
                return compound(header + master1 + master2 + b"".join(slides) + record(0x1772, directory))
            for follow in (0, 2):
                data = two_masters(follow)
                pixels, _ = run(data, page=0)
                pixels.check((120, 120), (17, 83, 211), 0)
                pixels, _ = run(data, page=1)
                pixels.check((120, 120), (231, 41, 51) if follow else (71, 191, 31), 0)
            print("two masters: persist/masterId resolution and slide COLOR_SCHEME override=PASS")
            def master(color):
                return record(0x3F8, record(0x7F0, (bytes(color) + b"\0") * 8, 0, 1), 15)
            indirect = shape(extra=prop_table([(0x181, 0x08000004)]))
            data = compound(document_header(1) + master((17, 83, 211)) + slide_record(indirect)
                            + master((231, 41, 51)))
            pixels, _ = run(data)
            pixels.check((120, 120), (17, 83, 211), 0)
            print("missing persist/masterId: nearest preceding physical master selected=PASS")
        else:
            raise ValueError(name)
    print(f"native-ppt-fill-{name}: {checks} checks passed")


if __name__ == "__main__":
    main()
