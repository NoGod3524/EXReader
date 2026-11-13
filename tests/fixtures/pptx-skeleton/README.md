# PPTX M1 fixtures

Six original decks created with python-pptx 1.0.2. No Office installation is needed.

```sh
python -m pip install python-pptx==1.0.2
python tests/fixtures/pptx-skeleton/generate.py
python tests/fixtures/pptx-skeleton/generate.py --check
ctest --test-dir build/pptx-m1 -R '^native-pptx-' --output-on-failure
```

`manifest.json` records page counts and EMU dimensions read back through
python-pptx. ZIP member order, timestamps and permissions are normalized so
regeneration can compare bytes. The ctypes acceptance tests need only Python's
standard library and the built SDK, and exercise both file and memory opens.

The six decks cover zero slides, a title slide, five layouts, 16:9, 4:3 and
twenty slides. Invalid containers and references are derived in temporary
directories by `tests/test_pptx_skeleton.py`; malformed binaries are not stored.
