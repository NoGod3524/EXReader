#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read current SDK identity or an installed, possibly historical, SDK header."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def source_version(root=ROOT):
    text = (Path(root) / 'cmake/versions.cmake').read_text(encoding='utf-8')
    return re.search(r'set\(EXR_SDK_VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)\)', text)[1]


def header_text(path):
    """Retain the legacy public macro for inspectors; resolve its generated alias."""
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    if re.search(r'^#define EXR_VERSION EXR_SDK_VERSION$', text, re.M):
        generated = path.with_name('version.h').read_text(encoding='utf-8')
        version = re.search(r'^#define EXR_SDK_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', generated, re.M)[1]
        text = text.replace('#define EXR_VERSION EXR_SDK_VERSION', f'#define EXR_VERSION "{version}"')
        text += '\n' + generated
    return text


def installed_version(sdk):
    text = header_text(Path(sdk) / 'include/exr/base.h')
    return re.search(r'^#define EXR_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M)[1]


if __name__ == '__main__':
    print(source_version())
