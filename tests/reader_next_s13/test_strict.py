"""Actions-only regression checks for authenticated artifact consumption."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from strict import authenticated_zip


class ArtifactChecks(unittest.TestCase):
    def consume(self, member="reports/summary.json", **changes):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr(member, b"{}")
        blob = data.getvalue()
        identity = dict(id=1, name="test", expired=False,
                        expires_at="2099-01-01T00:00:00Z", size_in_bytes=len(blob),
                        digest="sha256:" + hashlib.sha256(blob).hexdigest())
        identity.update(changes)
        with tempfile.TemporaryDirectory() as directory:
            with patch("strict.download_artifact_zip", side_effect=lambda identifier, stream: stream.write(blob)):
                result = authenticated_zip(identity, Path(directory))
                self.assertEqual((result / member).read_bytes(), b"{}")

    def test_valid(self):
        self.consume()

    def test_refusals(self):
        for changes in (dict(expired=True), dict(expires_at="2000-01-01T00:00:00Z"),
                        dict(size_in_bytes=1), dict(digest="sha256:" + "0" * 64)):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                self.consume(**changes)
        for member in ("../escape", "/absolute", "C:/drive", "dir\\escape"):
            with self.subTest(member=member), self.assertRaises(AssertionError):
                self.consume(member)


if __name__ == "__main__":
    unittest.main()
