#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make pkg-config metadata relocatable instead of stripping its prefix.

A .pc file is functional configuration, not prose: its prefix must keep pointing
at the installed include and library directories after the tree moves. For every
file this module computes the expression that resolves back to the prefix from
the file's own location (the pcfiledir variable, relative) and replaces the
absolute build prefix with it, leaving library names, flags, dependencies and
layout untouched. Every replacement is recorded per occurrence, so the original
bytes can be rebuilt exactly and nothing else in the file can change unnoticed.
"""
import posixpath
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib

PCFILEDIR = chr(36) + '{pcfiledir}'
PREFIX_VARIABLE = re.compile(r'^prefix\s*=', re.M)


def expression_for(pc_relative_path):
    """The pcfiledir-relative expression that names the stage root."""
    directory = posixpath.dirname(Path(pc_relative_path).as_posix())
    if not directory:
        return PCFILEDIR
    return PCFILEDIR + '/' + posixpath.relpath('.', directory)


def stage_needles(stage):
    """The absolute stage path in both separator spellings."""
    text = str(Path(stage).absolute()).rstrip('\\/')
    needles = {'stage-windows': text.replace('/', '\\').encode('utf-8')}
    posix = text.replace('\\', '/')
    if posix != text.replace('/', '\\'):
        needles['stage-posix'] = posix.encode('utf-8')
    return needles


def relocate(payload, stage, pc_relative_path):
    """Replace the absolute stage prefix with the pcfiledir expression."""
    expression = expression_for(pc_relative_path)
    needles = stage_needles(stage)
    replacements = {key: expression.encode('utf-8') for key in needles}
    relocated, occurrences = distlib.rewrite_occurrences(payload, needles, replacements)
    return relocated, occurrences, expression


def has_prefix_variable(payload):
    try:
        return bool(PREFIX_VARIABLE.search(payload.decode('utf-8')))
    except UnicodeDecodeError:
        return False
