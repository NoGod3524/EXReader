"""Actions-only inspection of text produced by the installed public SDK API."""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path('build/c04-projection')
body = (root / 'public-text.txt').read_bytes()
text = body.decode('utf-8')
query = 'Policy and Procedure TTR'
contexts = []
for word in ('Policy', 'Procedure', 'TTR', 'policy', 'procedure'):
    offset = 0
    for _ in range(20):
        at = text.find(word, offset)
        if at < 0:
            break
        contexts.append({'word': word, 'unicode_offset': at, 'context': text[max(0, at-100):at+160]})
        offset = at + len(word)
report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
          'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'accepted': False,
          'scope': 'public API text projection diagnosis only; original F5 remains unchanged',
          'text_sha256': hashlib.sha256(body).hexdigest(), 'text_bytes': len(body),
          'original_query': query, 'exact_query_offset': text.find(query),
          'casefold_query_offset': text.casefold().find(query.casefold()),
          'whitespace_collapsed_query_offset': ' '.join(text.split()).casefold().find(query.casefold()),
          'head': text[:1600], 'contexts': contexts}
(root / 'projection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('C04-PUBLIC-PROJECTION ' + json.dumps(report, ensure_ascii=False))
