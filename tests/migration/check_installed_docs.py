"""Check the two previously reported installed documentation path leaks."""
import os
from pathlib import Path
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true'
prefix = Path(sys.argv[1])
for name in ('CONVERSION.md', 'WP7-SCRIPTS.md'):
    path = prefix / 'docs' / name
    text = path.read_text(encoding='utf-8')
    assert 'C:/Users/Oscar/' not in text and 'C:\\Users\\Oscar\\' not in text, path
    assert 'build/wp' in text, path
    print('installed document checked:', path)
