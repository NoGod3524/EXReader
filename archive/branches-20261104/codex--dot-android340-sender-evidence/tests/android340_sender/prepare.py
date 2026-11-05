"""Generate a dedicated positive-only runner; execute exclusively in Actions."""
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
BASE = '047648865e509d5835b7d6e1389681e314d94e28'
path = 'tests/reader_android_reading/java/org/exreader/host/ReadingUiTest.java'
original = subprocess.check_output(['git', 'show', BASE + ':' + path]).decode()
assert Path(path).read_text() == original
source = original[:original.index('    private byte[] retained(')]
source = source.replace('public final class ReadingUiTest', 'public final class Android340SenderTest')
seed = '            library.saveProgress(book("txt"),0);library.saveNote(book("txt"),0,0,0,"retained existing SDK note");'
assert source.count(seed) == 1
source = source.replace(seed, '')
source = source.replace('private void seed()', 'private void importOriginals()')
count_guard = 'need(items.length==7,"seven exact originals retained");'
assert source.count(count_guard) == 1
source = source.replace(count_guard, 'need(items.length==1,"one exact TXT original retained");')
assert 'NativeReadingProduct.apply(' not in source
assert 'NativeReadingProbe.receive(' not in source
source += Path('tests/android340_sender/sender.java.inc').read_text() + '\n}\n'
target = Path('build/android340-sender/java/org/exreader/host/Android340SenderTest.java')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(source)
