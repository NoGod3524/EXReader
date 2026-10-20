#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated independent open/render/text probe; no pixel-equivalence claim."""
import hashlib
import json
from pathlib import Path
import sys


def valid_reference(result):
    if not isinstance(result, dict) or type(result.get('schema')) is not int or result['schema'] != 1:
        return False
    if result.get('reference') != 'PyMuPDF' or not isinstance(result.get('version'), str):
        return False
    for key in ('complete', 'repaired', 'password_required'):
        if type(result.get(key)) is not bool:
            return False
    for key in ('pages', 'text_bytes'):
        if type(result.get(key)) is not int or result[key] < 0:
            return False
    count = result.get('page_count')
    return (result.get('stage') in ('open', 'render', 'text') and
            (not result['complete'] or (type(count) is int and count > 0 and
             count == result['pages'] and not result['password_required'])))


def main():
    import pymupdf
    if len(sys.argv) != 2:
        return 2
    result = {'schema': 1, 'reference': 'PyMuPDF', 'version': pymupdf.VersionBind,
              'complete': False, 'pages': 0, 'text_bytes': 0, 'repaired': False,
              'password_required': False, 'stage': 'open'}
    try:
        with pymupdf.open(sys.argv[1]) as document:
            result['repaired'] = document.is_repaired
            result['page_count'] = document.page_count
            result['password_required'] = bool(document.needs_pass)
            if document.needs_pass:
                raise ValueError('Password required by reference')
            if document.page_count <= 0:
                raise ValueError('No reference pages')
            for page in document:
                result['stage'] = 'render'
                extent = max(page.rect.width, page.rect.height)
                if extent <= 0:
                    raise ValueError('Invalid page extent')
                scale = min(1, 720/extent)
                bitmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
                if bitmap.width <= 0 or bitmap.height <= 0 or bitmap.n != 4:
                    raise ValueError('Invalid bitmap')
                result['stage'] = 'text'
                result['text_bytes'] += len(page.get_text().encode('utf-8'))
                result['pages'] += 1
            result['complete'] = True
    except Exception as error:
        result['error_type'] = type(error).__name__
        result['error'] = str(error)
    result['module_sha256'] = hashlib.sha256(Path(pymupdf.__file__).read_bytes()).hexdigest()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
