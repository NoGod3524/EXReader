# Product-owned TXT originals

This opt-in product module imports an existing regular TXT file into a private,
pre-existing directory. It hashes and copies in 64 KiB blocks, reserves its
content identity in the product catalog, verifies the copy, flushes it and
publishes without replacement before marking it ready. Duplicate imports verify
and reuse the ready original without replacing catalog metadata or SDK books.
Call recovery on the catalog owner before imports at startup and after an
unsuccessful import; staged and deleting entries are reconciled there. A staged
publication becomes ready only after verification. Catalog shelf queries hide
pending metadata. Verified reopen checks the ready state, size and digest.

The root must be exclusively managed by the host, remain private while paths are
in use, and support file and directory durability and no-replace publication.
The caller supplies normalized metadata and serializes all operations on the
catalog owner. The host must connect the returned verified path to the approved
bounded TXT reader, manage UI/cancellation and lifecycle, and retain the old SDK
library for existing books. This module does not wire a host UI or migrate books.
