"""Capture native identities and exact bytes on Actions without importing the coordinator."""
import hashlib
import json
import os
from pathlib import Path
import stat

def native(path, retained=None):
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        assert stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode), str(path)
        digest = None
        if stat.S_ISREG(before.st_mode):
            chunks = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk: break
                chunks.append(chunk)
            data = b"".join(chunks)
            assert len(data) == before.st_size
            digest = hashlib.sha256(data).hexdigest()
            if retained is not None:
                retained.parent.mkdir(parents=True, exist_ok=True)
                retained.write_bytes(data)
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        assert all(getattr(before, key) == getattr(after, key) for key in fields), str(path)
        return dict(device=before.st_dev, inode=before.st_ino, mode=before.st_mode,
                    uid=before.st_uid, gid=before.st_gid, links=before.st_nlink,
                    bytes=before.st_size, sha256=digest)
    finally:
        os.close(descriptor)

def capture(authority, libraries, destination):
    assert os.environ.get("GITHUB_ACTIONS") == "true" and os.geteuid() != 0
    destination.mkdir(parents=True, exist_ok=False)
    objects = []
    for path in [authority, *sorted(authority.rglob("*"))]:
        relative = path.relative_to(authority).as_posix()
        row = native(path, destination / "authority" / relative)
        objects.append(dict(path=relative, **row))
    targets = []
    for index, path in enumerate(libraries):
        archive = "library-%d.sqlite" % index
        row = native(path, destination / archive)
        targets.append(dict(path=str(path), archive_path=archive, **row,
                            parent=dict(path=str(path.parent), **native(path.parent))))
    result = dict(schema="pc02-native-snapshot-v1", euid=os.geteuid(),
                  authority_path=str(authority), objects=objects, libraries=targets)
    (destination / "native-identities.json").write_text(json.dumps(result, indent=2) + "\n")
