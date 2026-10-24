"""Actions-only originals; reuse the accepted search and migration writers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS')=='true'
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tests/reader_search'))
from make_search_fixtures import txt,epub,pdf,long_epub,NEEDLE,entry
from make_fixtures import cbz
spec=importlib.util.spec_from_file_location('reader_search_legacy_fixture',root/'tests/migration/legacy_data.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
folder=Path(sys.argv[1]);folder.mkdir(parents=True,exist_ok=False)
(folder/'search.txt').write_bytes(txt());epub(folder/'search.epub');pdf(folder/'search.pdf')
(folder/'blank.pdf').write_bytes(legacy.pdf(['']))
cbz(folder/'search.cbz');long_epub(folder/'long.epub')
with zipfile.ZipFile(folder/'search.epub') as incoming,zipfile.ZipFile(folder/'legacy.epub','w') as outgoing:
    for name in incoming.namelist():
        data=incoming.read(name)
        if name=='book.opf':data=data.replace(b'<dc:title>reader-search</dc:title>',b'<dc:title>Reading legacy EPUB</dc:title>')
        entry(outgoing,name,data)
    outgoing.comment=b'Android old global projection fixture'
rows=[]
for role,name,title in [('txt','search.txt','Search TXT'),('epub','search.epub','Search EPUB'),('pdf','search.pdf','Search PDF'),('blank','blank.pdf','Search blank PDF'),('cbz','search.cbz','Search CBZ'),('long','long.epub','Search long EPUB'),('legacy','legacy.epub','Reading legacy EPUB')]:
    data=(folder/name).read_bytes();rows.append({'role':role,'file':name,'title':title,'format':'pdf' if role=='blank' else 'epub' if role in ('long','legacy') else role,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest={'books':rows,'expected':{'txt_many_query':'Z-hit','txt_many_count':250,'txt_unique_query':'Z-hit 249','txt_unicode_query':'🙂🎉','txt_unicode_count':2,'txt_ambiguous_query':'AMBIGUOUS TARGET','txt_ambiguous_count':2,'epub_unique_query':'unique-b-only 🙂','epub_unique_count':1,'epub_unique_part':1,'epub_repeated_query':'Alpha SEARCHTOKEN','epub_repeated_count':2,'epub_repeated_parts':[0,2],'pdf_unique_query':'Fixed page four.','pdf_unique_count':1,'pdf_unique_page':3,'blank_query':'no printed text','long_query':NEEDLE}}
(folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
