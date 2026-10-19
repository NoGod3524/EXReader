#!/usr/bin/env python3
"""Create an original short audiobook with FFmpeg; no runtime tool dependency."""
# SPDX-License-Identifier: MIT
from pathlib import Path
import hashlib
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT/'tests/fixtures/audio/metadata.m4b'
    with tempfile.TemporaryDirectory() as work:
        metadata = Path(work)/'book.txt'
        metadata.write_text(';FFMETADATA1\ntitle=Book 中文😀\nartist=作者\n'
                            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=100\ntitle=One\n'
                            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=100\nEND=200\ntitle=Two\n', encoding='utf-8')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', str(ROOT/'tests/fixtures/audio/pcm.wav'),
                        '-i', str(ROOT/'tests/fixtures/pdf-images/baseline.jpg'),
                        '-i', str(metadata), '-map', '0:a', '-map', '1:v',
                        '-map_metadata', '2', '-map_chapters', '2', '-c:a', 'aac',
                        '-c:v', 'copy', '-disposition:v:0', 'attached_pic',
                        '-f', 'ipod', str(target)], check=True)
    print(str(target.stat().st_size)+' bytes, SHA256 '+hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
