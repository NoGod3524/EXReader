#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Use the shared Android builder with the current catalog's full install target set."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path('tools').resolve()))
import build_android_host as builder

original_run = builder.run


def run(command, *args, **kwargs):
    command = list(command)
    if '--target' in command and 'reader_catalog' in command:
        index = command.index('reader_catalog')
        command.insert(index + 1, 'reader_original_import')
        print('Performance candidate: also build reader_original_import before catalog install', flush=True)
    return original_run(command, *args, **kwargs)


builder.run = run
builder.main()
