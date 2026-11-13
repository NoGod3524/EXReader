"""CFB/record adversarial cases plus committed PowerPoint COM oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

FREE, END, FAT, DIF = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC
OK, FORMAT, LIMIT = 0, 5, 6


def record(kind, payload=b"", version=0, instance=0):
    return struct.pack("<HHI", version | instance << 4, kind, len(payload)) + payload


def document(count=1, width=5760, height=4320, orphan=0, size=True):
    atom = record(0x3E9, struct.pack("<II", width, height) + bytes(32)) if size else b""
    slides = b"".join(record(0x3F3, struct.pack("<IIIII", i + 1, 0, 0, i + 256, 0)) for i in range(count))
    masters = record(0xFF0, record(0x3F3, bytes(20)), 15, 1)
    notes = record(0xFF0, record(0x3F3, bytes(20)), 15, 2)
    return (record(0x3E8, atom + record(0xFF0, slides, 15) + masters + notes, 15)
            + record(0x3EE, record(0x3EF, bytes(24)), 15) * (count + orphan))


def summary(title, wide=True):
    raw = (title + "\0").encode("utf-16le" if wide else "cp1252")
    value = struct.pack("<II", 31 if wide else 30, len(raw) // 2 if wide else len(raw)) + raw
    section = struct.pack("<IIIIII", 24 + 8 + len(value), 2, 1, 24, 2, 32)
    section += struct.pack("<IHH", 2, 1200 if wide else 1252, 0) + value
    return struct.pack("<HHI", 0xFFFE, 0, 0) + bytes(16) + struct.pack("<I", 1) + bytes(16) + struct.pack("<I", 48) + section


def compound(payload, sector_size=512, title=None, name="PowerPoint Document"):
    """A deterministic, independent CFB writer for byte-level negative tests."""
    streams = [(name, payload)]
    if title is not None:
        streams.append(("\x05SummaryInformation", title))
    sectors, links, mini_links, mini_data, entries = [], [], [], bytearray(), []

    def allocate(data):
        first = len(sectors)
        blocks = (len(data) + sector_size - 1) // sector_size
        for i in range(blocks):
            sectors.append(data[i * sector_size:(i + 1) * sector_size].ljust(sector_size, b"\0"))
            links.append(first + i + 1 if i + 1 < blocks else END)
        return first if blocks else END

    for stream_name, data in streams:
        if len(data) < 4096:
            start = len(mini_links)
            blocks = (len(data) + 63) // 64
            for i in range(blocks):
                mini_links.append(start + i + 1 if i + 1 < blocks else END)
            mini_data.extend(data.ljust(blocks * 64, b"\0"))
            entries.append((stream_name, start if blocks else END, len(data)))
        else:
            entries.append((stream_name, allocate(data), len(data)))
    root_start = allocate(mini_data)
    mini_fat = allocate(b"".join(struct.pack("<I", n) for n in mini_links).ljust(
        ((len(mini_links) * 4 + sector_size - 1) // sector_size) * sector_size, b"\xff"))

    def entry(n, kind, start, size, right=FREE, child=FREE):
        b = bytearray(128)
        text = (n + "\0").encode("utf-16le")
        b[:len(text)] = text
        struct.pack_into("<HBBIII", b, 64, len(text), kind, 1, FREE, right, child)
        struct.pack_into("<IQ", b, 116, start, size)
        return b

    directory = entry("Root Entry", 5, root_start, len(mini_data), child=1)
    for i, (n, start, size) in enumerate(entries):
        directory += entry(n, 2, start, size, right=i + 2 if i + 1 < len(entries) else FREE)
    directory_start = allocate(directory)
    base = len(sectors)
    fat_count, dif_count = 1, 0
    while True:
        needed_fat = (base + fat_count + dif_count + sector_size // 4 - 1) // (sector_size // 4)
        needed_dif = max(0, (needed_fat - 109 + sector_size // 4 - 2) // (sector_size // 4 - 1))
        if (fat_count, dif_count) == (needed_fat, needed_dif):
            break
        fat_count, dif_count = needed_fat, needed_dif
    fat_ids = list(range(base, base + fat_count))
    dif_ids = list(range(base + fat_count, base + fat_count + dif_count))
    all_links = links + [FAT] * fat_count + [DIF] * dif_count
    fat_bytes = b"".join(struct.pack("<I", n) for n in all_links).ljust(fat_count * sector_size, b"\xff")
    sectors.extend(fat_bytes[i * sector_size:(i + 1) * sector_size] for i in range(fat_count))
    for i, _ in enumerate(dif_ids):
        values = fat_ids[109 + i * (sector_size // 4 - 1):109 + (i + 1) * (sector_size // 4 - 1)]
        values += [FREE] * (sector_size // 4 - 1 - len(values))
        values.append(dif_ids[i + 1] if i + 1 < len(dif_ids) else END)
        sectors.append(struct.pack("<" + "I" * len(values), *values))
    header = bytearray(sector_size)
    header[:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3 if sector_size == 512 else 4, 0xFFFE,
                     9 if sector_size == 512 else 12, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 1 if sector_size == 4096 else 0, fat_count,
                     directory_start, 0, 4096, mini_fat,
                     (len(mini_links) * 4 + sector_size - 1) // sector_size,
                     dif_ids[0] if dif_ids else END, dif_count)
    struct.pack_into("<109I", header, 76, *(fat_ids[:109] + [FREE] * max(0, 109 - len(fat_ids))))
    return bytes(header) + b"".join(sectors)


def main():
    # CTest pipes use the Windows ANSI code page unless explicitly overridden.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("group")
    args = parser.parse_args()
    checks = 0
    with tempfile.TemporaryDirectory(prefix="exr-ppt-") as temp:
        path = Path(temp) / "sample.ppt"

        def run(data=None, status=OK, mode="file", source=None, message=None, pages=None, dims=None, title=None):
            nonlocal checks
            if data is not None:
                path.write_bytes(data)
            result = subprocess.run([str(args.probe.resolve()), mode, str(source or path)],
                                    capture_output=True, encoding="utf-8", errors="strict", check=True)
            values = dict(line.split("=", 1) for line in result.stdout.splitlines())
            assert int(values["status"]) == status, result.stdout
            if message:
                assert message in values["message"], result.stdout
            if pages is not None:
                assert int(values["pages"]) == pages, result.stdout
            if dims:
                assert (float(values["width"]), float(values["height"])) == dims, result.stdout
            if title is not None:
                assert values["title"] == title, result.stdout
            assert values["white"] == "1", result.stdout
            checks += 1
            if status != OK or values["message"]:
                label = {OK: "OK", FORMAT: "FORMAT", LIMIT: "LIMIT", 9: "CANCELLED"}[status]
                print(f"{mode}: EXR_{label}: {values['message']}")
            return values

        group = args.group
        if group == "cfb":
            run(compound(document(2)), mode="cfb", pages=len(document(2)))
            for sector in (512, 4096):
                run(compound(document(2), sector), pages=2)
                run(compound(document(2) + record(0x1234, bytes(5000)), sector), pages=2)
            big = compound(document() + record(0x1234, bytes(8 * 1024 * 1024)))
            assert struct.unpack_from("<I", big, 72)[0] > 0
            run(big, pages=1)
            malformed = bytearray(compound(document()))
            struct.pack_into("<H", malformed, 30, 10)
            run(malformed, FORMAT)
            malformed = bytearray(compound(document()))
            directory = (struct.unpack_from("<I", malformed, 48)[0] + 1) * 512
            struct.pack_into("<I", malformed, directory + 120 + 128, 256 * 1024 * 1024 + 1)
            run(malformed, LIMIT, message="256 MiB")
            malformed = bytearray(compound(document(), title=summary("title")))
            directory = (struct.unpack_from("<I", malformed, 48)[0] + 1) * 512
            for index in (1, 2):
                struct.pack_into("<I", malformed, directory + 120 + 128 * index, 128 * 1024 * 1024 + 1)
            run(malformed, LIMIT, message="total stream size")
            malformed = bytearray(compound(document()))
            # First mini FAT entry points back to itself.
            mini = (struct.unpack_from("<I", malformed, 60)[0] + 1) * 512
            struct.pack_into("<I", malformed, mini, 0)
            run(malformed, FORMAT, message="offset")
            malformed = bytearray(compound(document()))
            fat = (struct.unpack_from("<I", malformed, 76)[0] + 1) * 512
            directory_id = struct.unpack_from("<I", malformed, 48)[0]
            struct.pack_into("<I", malformed, fat + directory_id * 4, directory_id)
            run(malformed, FORMAT, message="offset")
            malformed = bytearray(compound(document()))
            directory = (struct.unpack_from("<I", malformed, 48)[0] + 1) * 512
            struct.pack_into("<I", malformed, directory + 128 + 72, 1)
            run(malformed, FORMAT, message="directory tree")
            malformed = bytearray(big)
            difat = (struct.unpack_from("<I", malformed, 68)[0] + 1) * 512
            struct.pack_into("<I", malformed, difat + 508, struct.unpack_from("<I", malformed, 68)[0])
            run(malformed, FORMAT, message="DIFAT termination")
        elif group == "records":
            run(document(3), mode="records", pages=3)
            # The independent physical-container path works without a slide list.
            run(record(0x3E8, b"", 15) + record(0x3EE, b"", 15) * 4, mode="records", pages=4)
            run(document() + record(0xFD9, b"", 15) + record(0xFF5, bytes(28)), mode="records", pages=1)
            run(document(2, orphan=1), mode="records", pages=2, message="warning")
            run(compound(document(2, orphan=1)), pages=2, message="PPT warning")
            # recVer=0 is legal on atoms, including arbitrary opaque payloads.
            run(document() + record(0x7777, b"not records!"), mode="records", pages=1)
            run(record(0x3E8, record(0xFF0, record(0x3F3, bytes(20)), 0), 0), mode="records", pages=1)
            run(document(7) + document(2), mode="records", pages=2, message="warning")
            nested = record(0x7777)
            for _ in range(65):
                nested = record(0x7777, nested, 15)
            run(nested, LIMIT, mode="records", message="depth")
            nested = b""
            for _ in range(64):
                nested = record(0x7777, nested, 15)
            run(document() + nested, mode="records", pages=1)
            run(record(0x3E8, record(0xFF0, record(0x3F3, bytes(4)), 15), 15), FORMAT,
                mode="records", message="offset")
        elif group == "slides":
            manifest = json.loads((args.fixtures / "manifest.json").read_text())
            for fixture in manifest["fixtures"]:
                source = args.fixtures / fixture["file"]
                assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["sha256"]
                result = run(source=source, pages=fixture["pages"])
                run(source.read_bytes(), mode="memory", pages=fixture["pages"])
                if fixture["pages"]:
                    assert (float(result["width"]), float(result["height"])) == (fixture["width_pt"], fixture["height_pt"])
                print(f"{fixture['file']}: engine={result['pages']} PowerPoint={fixture['pages']} white=OK")
            run(compound(document(0)), pages=0)
            run(compound(document(10001)), LIMIT, message="10000")
            run(compound(document()), 9, mode="cancel")
        elif group == "size":
            run(compound(document()), pages=1, dims=(720, 540))
            run(compound(document(width=7680)), dims=(960, 540))
            run(compound(document(size=False)), dims=(720, 540))
            run(compound(document(width=0, height=0)), dims=(720, 540))
            short = record(0x3E8, record(0x3E9, b"abc") + record(0xFF0, record(0x3F3, bytes(20)), 15), 15)
            run(compound(short), dims=(720, 540))
            for wide, text in ((True, "测试标题 🐧"), (False, "Résumé €")):
                run(compound(document(), title=summary(text, wide)), title=text)
            run(compound(document()), title="")
            run(compound(document(), title=b"bad"), title="")
        elif group == "truncated":
            source = (args.fixtures / "slides-20.ppt").read_bytes()
            run(source[:len(source) // 3], FORMAT, message="offset")
            run(document()[:-1], FORMAT, mode="records", message="offset")
            run(document() + b"abc", FORMAT, mode="records", message="offset")
            for n in (0, 3, 8, 64, 511):
                run(source[:n], FORMAT, mode="memory", message="offset")
                run(source[:n], FORMAT, message="offset")
            run(compound(document()[:-1]), FORMAT, message="offset")
        elif group == "wrongformat":
            source = bytearray((args.fixtures / "slides-1.ppt").read_bytes())
            source[:3] = b"BAD"
            run(source, FORMAT, message="signature")
            # Real committed docx, renamed to .ppt.
            docx = next(args.fixtures.parent.glob("*.docx"))
            run(docx.read_bytes(), FORMAT, message="signature")
            run(compound(document(), name="WordDocument"), FORMAT, message="不是 PowerPoint 97-2003 文档")
            run(compound(b""), FORMAT, message="DocumentContainer")
            # Signature sniffing also opens an extensionless presentation.
            extensionless = Path(temp) / "presentation"
            extensionless.write_bytes(compound(document(2)))
            run(source=extensionless, pages=2)
        else:
            raise ValueError(group)
    print(f"native-ppt-{group}: {checks} checks passed")


if __name__ == "__main__":
    main()
