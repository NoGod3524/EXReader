"""Actions-only navigation originals, built with the fixed F2 fixture writer."""
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path(__file__).resolve().parents[2]
from fixture_module import epub,pdf,NAV3,NCX2,REPEATED_NAV,A,B,entry
sys.path.insert(0,str(root/'tests/reader_reading_state'))
from make_fixtures import cbz

folder=Path(sys.argv[1]);folder.mkdir(parents=True,exist_ok=False)
# Thirty-five roots exercise real next-page state; the first roots preserve the
# fixed F2 hand-authored hierarchy and positive/negative target expectations.
extra=''.join(f'<li><a href="../Text/c.xhtml">Extra {i:02d}</a></li>' for i in range(35))
nav=NAV3.replace('</ol></nav>',extra+'</ol></nav>',1)
epub(folder/'nav3.epub',3,navigation=nav)
epub(folder/'ncx2.epub',2,ncx=NCX2,toc='ncx')
epub(folder/'repeated.epub',3,navigation=REPEATED_NAV,duplicate=True)
epub(folder/'empty.epub',2)
pdf(folder/'navigation-pdf.pdf');cbz(folder/'navigation-cbz.cbz')
# Include a raw surrogate-interior CFI and collapsed whitespace as honest
# non-mappable examples. The native probe creates CFIs through public SDK APIs.
source=folder/'nav3.epub';temporary=folder/'updated.epub'
with zipfile.ZipFile(source) as incoming,zipfile.ZipFile(temporary,'w') as outgoing:
    for info in incoming.infolist():
        data=incoming.read(info.filename)
        if info.filename==B:
            data=data.replace(b'</body>', '<p id="unicode">🙂 tail</p><p id="collapsed">A   B</p></body>'.encode())
        entry(outgoing,info.filename,data)
temporary.replace(source)
for name,title in [('nav3.epub','Navigation EPUB3'),('ncx2.epub','Navigation NCX2'),('repeated.epub','Navigation repeated'),('empty.epub','Navigation empty')]:
    original=folder/name;temporary=folder/('rewrite-'+name)
    with zipfile.ZipFile(original) as incoming,zipfile.ZipFile(temporary,'w') as outgoing:
        for info in incoming.infolist():
            data=incoming.read(info.filename)
            if info.filename=='OPS/book.opf':data=data.replace(b'<dc:title>Navigation fixture</dc:title>',('<dc:title>'+title+'</dc:title>').encode())
            entry(outgoing,info.filename,data)
    temporary.replace(original)
rows=[]
for role,file,title,format in [('nav','nav3.epub','Navigation EPUB3','epub'),('ncx','ncx2.epub','Navigation NCX2','epub'),('repeated','repeated.epub','Navigation repeated','epub'),('empty','empty.epub','Navigation empty','epub'),('pdf','navigation-pdf.pdf','Navigation PDF','pdf'),('cbz','navigation-cbz.cbz','Navigation CBZ','cbz')]:
    data=(folder/file).read_bytes();rows.append({'role':role,'file':file,'title':title,'format':format,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(folder/'manifest.json').write_text(json.dumps({'books':rows,'expected':{'nav_total_rows':48,'root_page_limit':32,'nav_root_count':45,'nav_child_part':1,'repeated_candidates':[0,1],'repeated_child_part':2,'pdf_pages':3,'cbz_pages':3}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
