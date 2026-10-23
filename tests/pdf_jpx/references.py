"""CI-only independent JPX component references and primary PDF spec excerpts."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request


def spec():
    import pymupdf
    url = "https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf"
    data = urllib.request.urlopen(url, timeout=60).read()
    print("primary", url, "sha256", hashlib.sha256(data).hexdigest())
    document = pymupdf.open(stream=data, filetype="pdf")
    hits = 0
    for number, page in enumerate(document):
        text = page.get_text()
        if "JPXDecode" in text and ("Decode array" in text or "Decode entry" in text or "Decode shall" in text):
            print(f"=== PDF physical page {number+1} ===\n{text}")
            hits += 1
    if not hits:
        raise RuntimeError("No JPX/Decode primary text found")


def packed(image, bits):
    values = list(image.getdata())
    components = len(image.getbands())
    row = (image.width * components * bits + 7) // 8
    out = bytearray(row * image.height)
    for y in range(image.height):
        at = y * row * 8
        for x in range(image.width):
            value = values[y * image.width + x]
            for component in value if isinstance(value, tuple) else (value,):
                for shift in range(bits - 1, -1, -1):
                    out[at // 8] |= ((component >> shift) & 1) << (7 - at % 8)
                    at += 1
    return bytes(out)


def references(executable, frozen):
    from PIL import Image
    import pymupdf
    # Pillow independently decodes files produced by the OpenJPEG encoder.
    # Restrict Pillow comparisons to byte precision: Pillow normalizes subbyte
    # and RGB16 samples, whereas the C regression checks their original values.
    for path in sorted(Path.cwd().glob("jpx-8-*.*")):
        components = int(path.stem.rsplit("-", 1)[1])
        output = path.with_suffix(path.suffix + ".samples")
        subprocess.run([executable, str(path), "7", "3", str(components), "8", str(int(components == 1)), str(output)], check=True)
        expected = packed(Image.open(path), 8)
        assert output.read_bytes() == expected, path
        print("Pillow exact component reference", path, hashlib.sha256(expected).hexdigest())
    source = Path(frozen)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == "2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a"
    document = pymupdf.open(source)
    original = document.xref_stream_raw(357)
    Path("nasa-original.jp2").write_bytes(original)
    # Read raw codestream to compare original indices independently of JP2 PCLR.
    if original.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n"):
        at = 0
        while at < len(original):
            size = int.from_bytes(original[at:at+4], "big")
            kind = original[at+4:at+8]
            header = 8
            if size == 1:
                size = int.from_bytes(original[at+8:at+16], "big")
                header = 16
            elif size == 0:
                size = len(original) - at
            assert header <= size <= len(original) - at
            if kind == b"jp2c":
                original = original[at+header:at+size]
                break
            at += size
        else:
            raise RuntimeError("NASA JP2 has no codestream")
    Path("nasa-codestream.j2k").write_bytes(original)
    reference = Image.open("nasa-codestream.j2k")
    assert reference.size == (575, 288) and reference.mode == "L", (reference.size, reference.mode)
    expected = reference.tobytes()
    subprocess.run([executable, "nasa-original.jp2", "575", "288", "1", "8", "1", "nasa.samples"], check=True)
    assert Path("nasa.samples").read_bytes() == expected
    print("NASA original Indexed samples match Pillow", len(expected), hashlib.sha256(expected).hexdigest())


if __name__ == "__main__":
    if sys.argv[1] == "--spec":
        spec()
    else:
        references(str(Path(sys.argv[1]).resolve()), sys.argv[2])
