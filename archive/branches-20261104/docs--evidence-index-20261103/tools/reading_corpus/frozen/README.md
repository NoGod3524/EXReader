# Retained original EPUB inputs

These two unmodified Project Gutenberg EPUBs preserve the identities already
registered in `../real-v1.json`. The publisher's live EPUB endpoints changed
after registration, causing collection to reject the new bytes on 2026-10-31.

The originals were recovered from the successful default-branch acceptance
[run 39974986212](https://github.com/NoGod3524/EXReader/actions/runs/39974986212),
artifact `r2-real-corpus-39974986212-1` (ID `12510622310`), created 2026-10-23.
The artifact ZIP SHA-256 is
`11ae13cd9b10d063c7a17e465c53544c54d7114d1847453aee73e7910bb2e352`.

| Original | Bytes | SHA-256 |
| --- | ---: | --- |
| `epub/pg84.epub` — Mary Wollstonecraft Shelley, *Frankenstein*, Project Gutenberg 84 | 474733 | `b82b1ad5cdd15439ab99e864741a0343f107adc796ce4326e44235a3f6f558a7` |
| `epub/pg1342.epub` — Jane Austen, *Pride and Prejudice*, Project Gutenberg 1342 | 24836548 | `d401ad6b118e84d01b8dd1a3d034fd41784feb14c50f1f7a0fc17f3263fa8e9f` |

The complete original credits and Project Gutenberg licenses remain embedded
in each EPUB. The registered permission scope is public domain in the USA;
the original publisher and policy URLs remain in `real-v1.json`.

Collection reads these retained bytes, checks the same frozen SHA-256, length
and byte limit, and records the retained file URI. It still fetches and checks
the current publisher's license terms. Discovery always uses the live source.
The registered manifest, selected pages, expected results and performance
budgets are unchanged.
