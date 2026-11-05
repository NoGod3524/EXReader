"""Retain installed binary/map/options assertions with the actual frozen SDK ID."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'tests/reader_windows_341/identity.py'
s=p.read_text()
old='edddc463c06ed5731195cdb8f06b2df6dff7699e'
assert s.count(old)==1
s=s.replace(old,'5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9')
exec(compile(s,str(p),'exec'),dict(__name__='__main__',__file__=str(p)))
