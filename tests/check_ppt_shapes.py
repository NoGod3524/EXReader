"""Real COM oracles plus malformed OfficeArt tests; Python standard library only."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from check_ppt import compound, record, OK, LIMIT


def prop_table(props, kind=0xF00B):
    return record(kind, b"".join(struct.pack("<HI", *p) for p in props), 3, len(props))


def shape(rgb=(255, 0, 0), box=(80, 80, 240, 180), kind=1, anchor=True,
          fill=True, line=False, width=3, extra=b"", child=False):
    color = rgb[0] | rgb[1] << 8 | rgb[2] << 16
    props = [(0x180, 0), (0x181, color), (0x1BF, 0x100010 if fill else 0x100000),
             (0x1C0, color), (0x1CB, int(width * 12700)),
             (0x1FF, 0x80008 if line else 0x80000)]
    atoms = record(0xF00A, struct.pack("<II", 1025, 0xA02 if child else 0xA00), 2, kind)
    atoms += prop_table(props) + extra
    if anchor:
        x, y, w, h = (int(v * 8) for v in box)
        atoms += (record(0xF00F, struct.pack("<iiii", x, y, x + w, y + h)) if child else
                  record(0xF010, struct.pack("<hhhh", y, x, x + w, y + h)))
    return record(0xF004, atoms, 15)


def group(children, ch=(0, 0, 5760, 4320), box=(0, 0, 720, 540), child=False):
    x, y, w, h = (int(v * 8) for v in box)
    atoms = record(0xF009, struct.pack("<iiii", *ch), 1)
    atoms += record(0xF00A, struct.pack("<II", 1024, 0x203 if child else 0x201), 2)
    atoms += (record(0xF00F, struct.pack("<iiii", x, y, x + w, y + h)) if child else
              record(0xF010, struct.pack("<hhhh", y, x, x + w, y + h)))
    return record(0xF003, record(0xF004, atoms, 15) + children, 15)


def document_header(count):
    atom = record(0x3E9, struct.pack("<II", 5760, 4320) + bytes(32))
    persist = b"".join(record(0x3F3, struct.pack("<IIIII", i + 1, 0, 0, i + 256, 0))
                       for i in range(count))
    return record(0x3E8, atom + record(0xFF0, persist, 15), 15)


def slide_record(content, drawing_record=True):
    body = record(0x3EF, bytes(24))
    if drawing_record:
        body += record(0x40C, content, 15)
    return record(0x3EE, body, 15)


def presentation(drawing=b"", *, drawing_record=True, second=None):
    result = document_header(2 if second is not None else 1)
    for content in ([drawing, second] if second is not None else [drawing]):
        result += slide_record(content, drawing_record)
    return compound(result)


class Pixels:
    def __init__(self, path):
        with path.open("rb") as stream:
            assert stream.readline() == b"P6\n"
            self.width, self.height = map(int, stream.readline().split())
            assert stream.readline() == b"255\n"
            self.data = stream.read()
        assert len(self.data) == self.width * self.height * 3

    def at(self, x, y):
        at = 3 * (int(y) * self.width + int(x))
        assert 0 <= int(x) < self.width and 0 <= int(y) < self.height
        return tuple(self.data[at:at + 3])

    def check(self, xy, rgb, tolerance=2):
        actual = self.at(*xy)
        assert all(abs(a - b) <= tolerance for a, b in zip(actual, rgb)), (xy, actual, rgb)
        return actual

    def white(self):
        assert self.data == b"\xff" * len(self.data), "expected blank page"

    def color_bounds(self, rgb):
        # Interior pixels give a stable box even when edges are antialiased.
        xs, ys = [], []
        for y in range(self.height):
            row = self.data[y * self.width * 3:(y + 1) * self.width * 3]
            for x in range(self.width):
                at = 3 * x
                if all(abs(row[at + c] - rgb[c]) <= 2 for c in range(3)):
                    xs.append(x)
                    ys.append(y)
        assert xs, f"missing color {rgb}"
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    def fill_interiors(self, shapes, scale):
        """Check every interior fill pixel, respecting later shapes' z-order."""
        colored = [s for s in shapes if s.get("rgb") is not None]

        def contains(item, px, py, margin=0):
            x, y, w, h = (v * scale for v in item["bbox_pt"])
            if not (x + margin < px < x + w - margin and y + margin < py < y + h - margin):
                return False
            if item["kind"] == "ellipse":
                return ((px - x - w / 2) / (w / 2 - margin)) ** 2 + ((py - y - h / 2) / (h / 2 - margin)) ** 2 < 1
            return item["kind"] == "rect"

        count, maximum = 0, 0
        for index, item in enumerate(colored):
            x, y, w, h = (v * scale for v in item["bbox_pt"])
            for py in range(max(0, math.floor(y)), min(self.height, math.ceil(y + h))):
                for px in range(max(0, math.floor(x)), min(self.width, math.ceil(x + w))):
                    margin = 2  # Exclude the rasterizer's antialiased edge band.
                    if not contains(item, px + .5, py + .5, margin):
                        continue
                    # The antialiasing band extends outside an overlaid shape.
                    if any(contains(s, px + .5, py + .5, -margin)
                           and not contains(s, px + .5, py + .5, margin)
                           for s in colored[index + 1:]):
                        continue
                    later = [s for s in colored[index + 1:] if contains(s, px + .5, py + .5)]
                    top = later[-1] if later else item
                    actual = self.at(px, py)
                    error = max(abs(a - b) for a, b in zip(actual, top["rgb"]))
                    assert error <= 2, (item["name"], (px, py), actual, top["rgb"])
                    maximum = max(maximum, error)
                    count += 1
        return count, maximum


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("group")
    args = parser.parse_args()
    checks = 0
    with tempfile.TemporaryDirectory(prefix="exr-ppt-shape-") as temp:
        source, output = Path(temp) / "sample.ppt", Path(temp) / "paint.ppm"

        def run(data=None, status=OK, source_file=None, warning=None, scale=1, page=0, memory=False):
            nonlocal checks
            if data is not None:
                source.write_bytes(data)
            output.unlink(missing_ok=True)
            command = [str(args.probe.resolve()), str(source_file or source), str(output), str(page), str(scale)]
            if memory:
                command.append("memory")
            result = subprocess.run(command, capture_output=True, encoding="utf-8", check=True)
            values = dict(line.split("=", 1) for line in result.stdout.splitlines())
            assert int(values["status"]) == status, result.stdout
            if warning:
                assert "warning" in values["message"].lower(), result.stdout
                assert warning in values["message"], result.stdout
            checks += 1
            pixels = Pixels(output) if status == OK and output.exists() else None
            if status != OK or warning:
                print(f"status={values['status']} message={values['message']}")
            return pixels, values

        name = args.group
        if name in ("red", "blue", "overlap", "group", "standard", "wide"):
            manifest = json.loads((args.fixtures / "manifest.json").read_text(encoding="utf-8"))
            stem = {"red": "red-rect", "blue": "blue-circle"}.get(name, name)
            matches = [f for f in manifest["fixtures"] if f.get("case", Path(f["file"]).stem) == stem]
            assert len(matches) == 1, (name, [f["file"] for f in manifest["fixtures"]])
            fixture = matches[0]
            path = args.fixtures / fixture["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture["sha256"]
            for scale, memory in ((1, False), (2, True)):
                pixels, values = run(source_file=path, scale=scale, memory=memory)
                assert int(values["pages"]) == 1
                assert (float(values["width"]), float(values["height"])) == (fixture["width_pt"], fixture["height_pt"])
                assert (pixels.width, pixels.height) == (math.ceil(fixture["width_pt"] * scale), math.ceil(fixture["height_pt"] * scale))
                paths = [s for s in fixture["shapes"] if s.get("rgb") is not None or s["kind"] == "line"]
                assert int(values["draw_count"]) == len(paths), values
                for index, item in enumerate(paths):
                    expected_flags = (1 if item.get("rgb") is not None else 0) | (2 if item.get("line_rgb") else 0)
                    assert int(values[f"draw_{index}_flags"]) == expected_flags, (item["name"], values)
                    for field in ("fill", "stroke"):
                        rgb = item.get("rgb" if field == "fill" else "line_rgb")
                        if rgb is not None:
                            rgba = rgb[0] << 24 | rgb[1] << 16 | rgb[2] << 8 | 255
                            assert int(values[f"draw_{index}_{field}"], 16) == rgba, (item["name"], field, values)
                    if item.get("line_rgb"):
                        assert abs(float(values[f"draw_{index}_width"]) - item["line_width_pt"]) < 1e-5, values
                for sample in fixture["samples"]:
                    xy = [int(v * scale) for v in sample["xy_pt"]]
                    actual = pixels.check(xy, sample["rgb"])
                    if scale == 1:
                        rgb = sample["rgb"]
                        origin = next((s for s in fixture["shapes"] if s.get("rgb") == rgb and s.get("colorref")), None)
                        raw = f" COM_COLORREF={origin['colorref']}" if origin else ""
                        print(f"{path.name} {sample['name']} xy={xy}{raw} expected={rgb} actual={list(actual)} max_error={max(abs(a-b) for a,b in zip(actual,rgb))}")
                checked, maximum = pixels.fill_interiors(fixture["shapes"], scale)
                print(f"{path.name} scale={scale} interior_pixels={checked} max_RGB_error={maximum}")
                if name == "group":
                    for item in fixture["shapes"]:
                        if item["kind"] != "rect":
                            continue
                        actual = pixels.color_bounds(item["rgb"])
                        x, y, w, h = item["bbox_pt"]
                        expected = [v * scale for v in (x, y, x + w, y + h)]
                        error = max(abs(a - b) for a, b in zip(actual, expected))
                        assert error < 2, (item["name"], actual, expected, error)
                        print(f"{path.name} {item['name']} scale={scale} PowerPoint={expected} rendered={list(actual)} max_position_error={error:.6g}px")
        elif name == "colors":
            shapes = shape((17, 34, 51)) + shape((255, 0, 0), (360, 80, 120, 100), kind=3)
            pixels, _ = run(presentation(shapes))
            pixels.check((120, 120), (17, 34, 51))
            pixels.check((420, 130), (255, 0, 0))
            pixels.check((361, 81), (255, 255, 255))
            print("COLORREF 0x00332211 -> RGB [17,34,51]; ellipse corner remains white")
        elif name == "anchors":
            pixels, _ = run(presentation(shape(anchor=False)), warning="missing-anchor=1")
            pixels.white()
            pixels, _ = run(presentation(drawing_record=False))
            pixels.white()
            pixels, _ = run(presentation(shape((255, 0, 0)), second=shape((0, 0, 255))), page=1)
            pixels.check((120, 120), (0, 0, 255))
            pixels.check((20, 20), (255, 255, 255))
            # int32 OfficeArtClientAnchor is also accepted, not mistaken for i16.
            atoms = record(0xF00A, struct.pack("<II", 1025, 0xA00), 2, 1)
            atoms += prop_table([(0x181, 0x332211), (0x1BF, 0x100010), (0x1FF, 0x80000)])
            atoms += record(0xF010, struct.pack("<iiii", 800, 640, 1920, 1440))
            pixels, _ = run(presentation(record(0xF004, atoms, 15)))
            pixels.check((90, 120), (17, 34, 51))
            pixels.check((120, 90), (255, 255, 255))
            pixels, _ = run(presentation(shape(box=(-20, 20, 100, 80))))
            pixels.check((10, 40), (255, 0, 0))
            pixels.check((120, 40), (255, 255, 255))
            # SlidePersistAtom references, not physical order, select pages.
            header = document_header(2)
            first, second = slide_record(shape()), slide_record(shape((0, 0, 255)))
            directory = record(0x1772, struct.pack("<III", 2 << 20 | 1,
                                                 len(header) + len(first), len(header)))
            ordered = compound(header + first + second + directory)
            pixels, _ = run(ordered)
            pixels.check((120, 120), (0, 0, 255))
            pixels, _ = run(ordered, page=1)
            pixels.check((120, 120), (255, 0, 0))
            # Without a usable persist mapping, a newer snapshot must not
            # borrow physical slides left over from the older document.
            latest = compound(header + first + second + document_header(1))
            pixels, values = run(latest)
            assert values["pages"] == "1"
            pixels.white()
        elif name == "truncated":
            good = shape((0, 0, 255), (360, 80, 120, 100))
            # Header says two six-byte entries, but the atom contains only one.
            malformed = record(0xF00B, struct.pack("<HI", 0x181, 0xFF), 3, 2)
            pixels, _ = run(presentation(shape(extra=malformed) + good), warning="malformed=1")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
            malformed = prop_table([(0x1CB, 0xFFFFFFFF)])
            pixels, _ = run(presentation(shape(extra=malformed) + good), warning="malformed=1")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
            bad_header = record(0xF004, record(0xF009, b"short", 1)
                                + record(0xF00A, struct.pack("<II", 1024, 0x201), 2), 15)
            malformed = record(0xF003, bad_header + shape(child=True), 15)
            pixels, _ = run(presentation(malformed + good), warning="malformed=1")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
            malformed = record(0xF00B, struct.pack("<HI", 0x181, 0xFF) + b"junk", 3, 1)
            pixels, _ = run(presentation(shape(extra=malformed) + good), warning="malformed=1")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
            # A complex property length must fit after the fixed entries too.
            malformed = prop_table([(0x8181, 100)])
            pixels, _ = run(presentation(shape(extra=malformed) + good), warning="malformed=1")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
            print("truncated fixed entries and complex data: malformed shape skipped; following shape blue")
        elif name == "limits":
            run(presentation(shape(fill=False) * 5001), LIMIT)
            run(presentation(group(b"") * 5001), LIMIT)
            # Exactly the documented ceiling is accepted.
            pixels, _ = run(presentation(shape(fill=False) * 5000))
            pixels.white()
            nested = shape(child=True)
            for _ in range(18):
                nested = group(nested)
            pixels, _ = run(presentation(nested + shape((0, 0, 255), (360, 80, 120, 100))), warning="depth=")
            pixels.check((120, 120), (255, 255, 255))
            pixels.check((400, 120), (0, 0, 255))
        elif name == "transforms":
            # off=(100,60), ext=(300,180), chOff=(80,40), chExt=(160,120).
            drawing = group(shape((17, 34, 51), (100, 60, 40, 30), child=True),
                            ch=(640, 320, 1920, 1280), box=(100, 60, 300, 180))
            pixels, _ = run(presentation(drawing))
            actual = pixels.color_bounds((17, 34, 51))
            assert max(abs(a-b) for a,b in zip(actual, (137.5, 90, 212.5, 135))) < 2, actual
            # Zero chExt retains identity scale and reports a warning.
            drawing = group(shape(box=(100, 60, 40, 30), child=True),
                            ch=(640, 320, 640, 320), box=(100, 60, 300, 180))
            pixels, _ = run(presentation(drawing), warning="zero-chExt=")
            actual = pixels.color_bounds((255, 0, 0))
            assert max(abs(a-b) for a,b in zip(actual, (120, 80, 160, 110))) < 2, actual
            inner = group(shape((17, 34, 51), (20, 10, 20, 10), child=True),
                          ch=(80, 40, 400, 200), box=(40, 20, 100, 50), child=True)
            pixels, _ = run(presentation(group(inner, ch=(0, 0, 1600, 800), box=(100, 60, 400, 200))))
            actual = pixels.color_bounds((17, 34, 51))
            assert max(abs(a-b) for a,b in zip(actual, (230, 125, 330, 175))) < 2, actual
        elif name == "styles":
            pixels, _ = run(presentation(shape(fill=False)))
            pixels.white()
            pixels, _ = run(presentation(shape((17, 34, 51), (80, 80, 240, 0), kind=20,
                                                 fill=False, line=True, width=6)))
            pixels.check((160, 80), (17, 34, 51))
            for y in (78, 79, 80, 81):
                pixels.check((160, y), (17, 34, 51))
            pixels.check((160, 70), (255, 255, 255))
            pixels, _ = run(presentation(shape((17, 34, 51), line=True, width=6)))
            pixels.check((160, 80), (17, 34, 51))
            pixels.check((160, 120), (17, 34, 51))
            # M3 preserves the available color when a gradient endpoint is absent.
            pixels, _ = run(presentation(shape(extra=prop_table([(0x180, 4)]))), warning="gradient-missing=")
            pixels.check((120, 120), (255, 0, 0))
            for kind in (0xF121, 0xF122):
                pixels, _ = run(presentation(shape(extra=prop_table([(0x181, 0x332211)], kind))))
                pixels.check((120, 120), (17, 34, 51))
            complex_data = record(0xF00B, struct.pack("<HI", 0x8380, 4) + b"test", 3, 1)
            pixels, _ = run(presentation(shape(extra=complex_data)))
            pixels.check((120, 120), (255, 0, 0))
            pixels, _ = run(presentation(shape(extra=prop_table([(0x181, 0x080000FF)]))))
            pixels.white()
            # A later boolean property only changes bits selected by its upper
            # 16-bit use mask; it must preserve an earlier explicit noLine.
            later = prop_table([(0x1FF, 0x400000)], 0xF121)
            pixels, values = run(presentation(shape(extra=later)))
            assert values["draw_0_flags"] == "1", values
            pixels.check((120, 120), (255, 0, 0))
            later = prop_table([(0x1BF, 0x200000)], 0xF121)
            pixels, values = run(presentation(shape(fill=False, extra=later)))
            assert values["draw_count"] == "0", values
            pixels.white()
            later = prop_table([(0x1FF, 0x80000)], 0xF122)
            pixels, values = run(presentation(shape(line=True, extra=later)))
            assert values["draw_0_flags"] == "1", values
            pixels.check((120, 120), (255, 0, 0))
            later = prop_table([(0x1C0, 0xFF0000), (0x1FF, 0x80008)], 0xF121)
            pixels, values = run(presentation(shape(extra=later)))
            assert values["draw_0_flags"] == "3", values
            pixels.check((120, 80), (0, 0, 255))
            pixels.check((120, 120), (255, 0, 0))
        else:
            raise ValueError(name)
    print(f"native-ppt-shape-{args.group}: {checks} checks passed")


if __name__ == "__main__":
    main()
