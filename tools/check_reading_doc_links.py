#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check repository paths and heading anchors in the eight reading overview docs."""
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = ['README.md'] + ['docs/' + name + '.md' for name in (
    'PROJECT_OVERVIEW', 'CORE-ROADMAP', 'WORK-QUEUE-2026-10-22', 'COMPETITIVE',
    'VERSIONING', 'ARCHITECTURE', 'PROJECT_STUDY')]


def visible_lines(path):
    fence = None
    for line in path.read_text(encoding='utf-8').splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence is None:
            yield line


def anchors(path):
    result, seen = set(), {}
    for line in visible_lines(path):
        result.update(re.findall(r'<[^>]+\b(?:id|name)=[\'"]([^\'"]+)', line))
        heading = re.match(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$', line)
        if not heading:
            continue
        title = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', heading[1])
        title = re.sub(r'<[^>]+>', '', title).lower()
        slug = ''.join(c for c in title if c in '_-' or c.isspace() or unicodedata.category(c)[0] in 'LNM')
        slug = re.sub(r'\s', '-', slug)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug + (f'-{count}' if count else ''))
    return result


def main():
    checked, errors = [], []
    for name in FILES:
        source = ROOT / name
        for number, line in enumerate(visible_lines(source), 1):
            links = re.findall(r'!?\[[^]]*\]\(([^)\n]+)\)', line)
            definition = re.match(r'^\s*\[[^]]+\]:\s*(\S+)', line)
            if definition:
                links.append(definition[1])
            for link in links:
                link = link.strip().split(' ', 1)[0].strip('<>')
                url = urlsplit(link)
                if url.scheme or url.netloc or not link:
                    continue
                target = (source.parent / unquote(url.path)).resolve() if url.path else source
                reason = None
                if not target.is_relative_to(ROOT):
                    reason = 'outside repository'
                elif not target.exists():
                    reason = 'missing repository path'
                elif url.fragment and target.suffix.lower() == '.md' and unquote(url.fragment) not in anchors(target):
                    reason = 'missing Markdown heading or HTML anchor'
                record = {'source': name, 'link': link}
                checked.append(record)
                if reason:
                    errors.append({**record, 'visible_line': number, 'reason': reason})
    result = {'source_sha': os.environ.get('GITHUB_SHA'), 'files': FILES,
              'checked_local_links': len(checked), 'errors': errors, 'accepted': not errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
