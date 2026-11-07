#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small offline regression check for the campaign, using the external baseline."""
import io
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from malformed_corpus import BASELINE, BASELINE_SHA256, CATEGORIES, Corpus, classify, probe, sha


def main():
    data = BASELINE.read_bytes()
    assert sha(data) == BASELINE_SHA256
    corpus = Corpus(data)
    hashes = set()
    for category in CATEGORIES:
        for index in range(1, 129):
            mutated, recipe = corpus.generate(category, index)
            assert mutated != data and sha(mutated) not in hashes
            assert (mutated, recipe) == corpus.generate(category, index)
            hashes.add(sha(mutated))
            if category in ("tail", "middle"):
                assert len(mutated) < len(data)
            elif category not in ("directory",):
                with zipfile.ZipFile(io.BytesIO(mutated)) as archive:
                    if category == "container":
                        assert "META-INF/container.xml" not in archive.namelist()
                    elif category == "mimetype":
                        assert archive.read("mimetype") != b"application/epub+zip"
                    elif category == "case":
                        assert corpus.opf not in archive.namelist()
                    elif category == "missing":
                        root = ET.fromstring(archive.read(corpus.opf))
                        assert any(e.attrib.get("href") == recipe["href"] for e in root.iter())
                        assert "OEBPS/" + recipe["href"] not in archive.namelist()
                    elif category == "duplicate":
                        names = archive.namelist()
                        assert len(names) > len(set(names))
    assert len(hashes) == 1024
    assert classify(1, "bad ZIP") == ("passed", "explicit_rejection")
    assert classify(1, "\n ") == ("investigate", "no_error_text")
    assert classify(0, "warning") == ("investigate", "accepted_malformed")
    assert classify(129, "bad ZIP") == ("investigate", "abnormal_exit")
    assert classify(-11, "") == ("investigate", "abnormal_exit")
    assert classify(1, "bad ZIP", True) == ("timeout", "timeout")
    # Exercise the actual watchdog/kill/reap path with a sleeping helper process.
    with tempfile.TemporaryDirectory(prefix="malformed-watchdog-check-") as directory:
        helper = Path(directory) / "sleep.py"
        helper.write_text("import time; time.sleep(30)\n", encoding="utf-8")
        import malformed_corpus as campaign
        real_popen = subprocess.Popen

        def sleeper(command, **kwargs):
            return real_popen([sys.executable, str(helper)], **kwargs)

        campaign.subprocess.Popen = sleeper
        try:
            result = probe(b"", Path(sys.executable), helper)
        finally:
            campaign.subprocess.Popen = real_popen
        assert result["bucket"] == "timeout" and result["timed_out"]
        assert result["exit_code"] is not None and 3 <= result["elapsed_seconds"] < 6
    print("1024 deterministic unique mutations, structural checks, classification and 3s watchdog passed")


if __name__ == "__main__":
    main()
