"""Ensure comparison cannot hide private/vendor exports or fat-slice differences."""
import tempfile
import struct
from pathlib import Path

from symbols import compare, inspect_shared, public_symbols, ROOT
from test_check_exports import ar, macho


def main():
    rows = [{"platform": p, "symbols": {"exr_api"}} for p in ["windows", "linux", "macos", "android", "ios"]]
    rows[1]["symbols"].add("vendor_leak")
    rows[3]["symbols"].add("__emutls_get_address")
    result = compare(rows, {"exr_api"})
    assert result["common_symbols"] == ["exr_api"]
    assert result["desktop_sets_equal"] is False
    assert result["platforms"][1]["unique_symbols"] == ["vendor_leak"]
    assert len(result["differences"]) == 2
    assert result["differences"][0]["present_on"] == ["android"]
    assert "TLS" in result["differences"][0]["reason"]
    try:
        compare(rows[:-1], {"exr_api"})
        raise AssertionError("incomplete platform cohort accepted")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "fixture.dylib"
        dylib = bytearray(macho([("exr_api", 0xf), ("exr_private", 0x1f), ("import", 1)]))
        struct.pack_into("<I", dylib, 12, 6)  # MH_DYLIB
        binary.write_bytes(dylib)
        assert inspect_shared(binary)[1][0]["symbols"] == {"exr_api"}
        binary.write_bytes(ar(binary.read_bytes()))
        try:
            inspect_shared(binary)
            raise AssertionError("static archive described as dynamic exports")
        except ValueError:
            pass
        binary.write_bytes(macho([("exr_api", 0xf)]))
        try:
            inspect_shared(binary)
            raise AssertionError("Mach-O object described as dynamic exports")
        except ValueError:
            pass
    assert "exr_version" in public_symbols(ROOT / "include/exr")
    print("PASS five-platform completeness, full exports, unique names, Mach-O normalization, archive rejection")


if __name__ == "__main__":
    main()
