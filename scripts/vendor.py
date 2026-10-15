"""Fetch pinned MIT-licensed Foliate sources, preserving upstream licenses."""
import io, pathlib, urllib.request, zipfile

REV = '78914aef4466eb960965702401634c2cb348e9b1'
root = pathlib.Path(__file__).resolve().parents[1] / 'vendor' / 'foliate'
data = urllib.request.urlopen(f'https://codeload.github.com/johnfactotum/foliate-js/zip/{REV}', timeout=60).read()
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    for entry in archive.infolist():
        rel = pathlib.PurePosixPath(*pathlib.PurePosixPath(entry.filename).parts[1:])
        if len(rel.parts) == 1 and (rel.suffix == '.js' or rel.name in ('LICENSE', 'README.md')) or str(rel) in ('vendor/zip.js', 'vendor/fflate.js'):
            target = root.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
(root / 'REVISION').write_text(REV + '\n')
# PDF is handled by our current PDF.js adapter; exclude upstream's experimental adapter.
view = root / 'view.js'
source = view.read_text(encoding='utf-8')
source = source.replace("const { makePDF } = await import('./pdf.js')\n        book = await makePDF(file)", "throw new UnsupportedTypeError('Use EXReader PDF adapter')")
view.write_text(source, encoding='utf-8')
# A ResizeObserver can fire while an iframe navigates, or a font promise after it closes.
paginator = root / 'paginator.js'
source = paginator.read_text(encoding='utf-8')
patches = {
    'class View {\n': 'class View {\n    #destroyed = false\n',
    '        if (!layout) return\n': '        if (!layout || this.#destroyed || !this.document?.body) return\n',
    '    expand() {\n        const { documentElement }': '    expand() {\n        if (this.#destroyed || !this.document?.body) return\n        const { documentElement }',
    '        if (this.document) this.#observer.unobserve(this.document.body)': '        this.#destroyed = true\n        this.#observer.disconnect()',
    '    render() {\n        if (!this.#view) return\n': '    render() {\n        if (!this.#view?.document?.body) return\n',
    'this.#view?.document?.fonts?.ready?.then(() => this.#view.expand())': 'this.#view?.document?.fonts?.ready?.then(() => this.#view?.expand())',
    'this.#background.style.background = getBackground(this.#view.document))': 'this.#view?.document?.body && (this.#background.style.background = getBackground(this.#view.document)))',
}
for before, after in patches.items():
    assert source.count(before) == 1, f'Upstream paginator changed: {before}'
    source = source.replace(before, after)
paginator.write_text(source, encoding='utf-8')
print('Vendored Foliate', REV)
