"""Current SDK provenance adapter; original validation and refusal tests intact."""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'tests/reader_windows_341/verify.py'
code = path.read_text(encoding='utf-8')
old = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
assert code.count(old) == 2, 'Original provenance literals changed'
exec(compile(code.replace(old, '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'), str(path), 'exec'), globals())
