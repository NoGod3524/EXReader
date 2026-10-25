"""Deploy the installed Windows runtime beside the unchanged installed probe."""
import os
from pathlib import Path
import shutil
from common import actions, file_hash


def deploy(stage, directory):
    actions()
    if os.name != 'nt':
        return []
    stage, directory = Path(stage), Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    libraries = sorted((stage / 'bin').glob('*.dll'))
    assert any(path.name.lower() == 'exreader.dll' for path in libraries), 'installed SDK runtime absent'
    records = []
    for library in libraries:
        destination = directory / library.name
        shutil.copyfile(library, destination)
        assert file_hash(destination) == file_hash(library)
        records.append({'name': library.name, 'bytes': library.stat().st_size,
                        'sha256': file_hash(library), 'installed': str(library), 'deployed': str(destination)})
    return records
