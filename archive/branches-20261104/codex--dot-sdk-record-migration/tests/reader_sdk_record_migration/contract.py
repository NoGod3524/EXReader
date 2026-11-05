"""Fixed named acceptance contract; evaluated only in Actions."""
OLD = '9854061be331fe603a1822d9b2b36ee357154927'
NEW = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
START = 'a826a65c9c66e43620eff61b49cb79f941a3c953'
MERGED = 'd170d43038ebcc22a9e6e0bea9bf463a5ebec98e'
DEPENDENCY = 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'
LABELS = {
    f'{role}-{kind}-{operation}'
    for role in ('txt', 'epubg', 'epub', 'pdf', 'cbz')
    for kind in ('progress', 'bookmark', 'highlight')
    if not (role == 'cbz' and kind == 'highlight')
    for operation in ('put', 'note', 'delete', 'restore')
    if not (kind == 'progress' and operation == 'note')
} | {'txt-v1', 'txt-ambiguous', 'txt-tombstone', 'txt-conflict-0', 'txt-conflict-1'}
NEGATIVES = {
    'offset-only-legacy-not-found', 'wrong-book-missing-no-fallback',
    'changed-content-missing-no-fallback', 'bad-wire-rejected', 'bad-unicode-rejected',
    'unknown-anchor-version-rejected', 'missing-spine-rejected-without-guess',
    'real-navigation-parser-qualified-source-contract', 'wrong-original-hash-rejected',
    'reopened-sdk-notes-progress-originals-equal-producer',
    'reopened-product-history-outbox-equal-producer',
    'readonly-probe-sdk-notes-progress-originals-unchanged',
    'readonly-probe-product-history-outbox-unchanged', 'all-product-handles-closed',
}
DIRECTIONS = {'3.40.0-to-3.40.0', '3.40.0-to-3.41.0', '3.41.0-to-3.41.0', '3.41.0-to-3.40.0'}
