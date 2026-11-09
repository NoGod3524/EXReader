# SPDX-License-Identifier: MIT
"""Real Windows host selection, dictionary, persistence and CSV acceptance.

python -X utf8 examples/windows/check_shell_dictionary.py EXE FONT IFO1 IFO2 OUTPUT
Dictionaries stay local. All pointer events are dispatched to the real page HWND.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from check_shell_search import run, setup, SearchSDK

WORDS = ['apple', 'book', 'cat', 'dog', 'elephant', 'fish', 'house', 'love', 'night', 'zebra']
SENTENCES = [f'The {word} is here, beside the "window".' for word in WORDS]


def book(path, title, sentences):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('OEBPS/book.opf', f'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">{title}</dc:identifier><dc:title>{title}</dc:title><dc:language>en</dc:language></metadata><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr('OEBPS/chapter.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Words</title></head><body>'+''.join('<p>'+s+'</p>' for s in sentences)+'</body></html>')


def main():
    exe,font,one,two,out=[Path(x).resolve() for x in sys.argv[1:6]];out.mkdir(parents=True,exist_ok=True)
    sdk=SearchSDK(exe.parent/'libexreader.dll');a=out/'words.epub';b=out/'second.epub'
    book(a,'Dictionary Acceptance',SENTENCES+['The qzxvmissing is absent.']);book(b,'Second Book',['An apple appears in this second book.'])
    pub=sdk.open({'path':str(a)});text=sdk.texts(pub)[0];sdk.publication_free(pub)
    pub=sdk.open({'path':str(b)});second=sdk.texts(pub)[0];sdk.publication_free(pub)
    phase=out/'live';profile=phase/'profile';profile.mkdir(parents=True,exist_ok=True)
    # Verify unrelated shelf data survives setting updates.
    (profile/'shelf.json').write_text('{"unrelated":{"title":"保留","count":7}}',encoding='utf8')
    script=['import|'+str(a),'import|'+str(b),'open|Dictionary Acceptance']+setup()+[
        'dict_add|'+str(one.parent),'dict_add|'+str(two.parent),'dict_settings','dict_close','dict_auto|0']
    captures=[]
    for i,word in enumerate(WORDS):
        offset=text.index(word.encode())
        if i==5:script+=['dict_auto|1']
        script += [f'annotgoto|0|{offset}',f'select_pointer|double|{offset}|0',f'select_pointer|up|{offset}|0']
        if i<5:script+=['select_key|D|0|1']
        script += [f'dict_check|{word}|2|lookup-{i}']
        if i==0:
            script+=['dict_collapse|0|1','dict_collapse|0|0']
            captures.append((f'STEP\t{len(script)}\tdict_collapse\tPASS','dictionary-light'))
            script+=['probe_wait|4000','shell_click|settings','shell_click|dark','shell_click|settings','dict_check|apple|2|dark']
            captures.append((f'STEP\t{len(script)}\tdict_check\tPASS','dictionary-dark'))
            script+=['probe_wait|4000','shell_click|settings','shell_click|light','shell_click|settings']
        if i<4:script+=['dict_save']
        script+=['dict_close']
    offset=text.index(b'qzxvmissing')
    script += [f'select_pointer|double|{offset}|0',f'select_pointer|up|{offset}|0','dict_check|qzxvmissing|0|missing']
    captures.append((f'STEP\t{len(script)}\tdict_check\tPASS','dictionary-missing'))
    script+=['dict_copy','probe_wait|4000','dict_close','open|Second Book','wait_idle']
    offset=second.index(b'apple')
    script += [f'select_pointer|double|{offset}|0',f'select_pointer|up|{offset}|0','dict_check|apple|2|second','dict_save','dict_vocab|5',
        'dict_filter|1|4','dict_export|first.csv','dict_filter|2|1','dict_export|second.csv','dict_filter|0|5','dict_export|vocabulary.csv',
        'dict_roundtrip|1','dict_pick_vocab|0']
    captures.append((f'STEP\t{len(script)}\tdict_pick_vocab\tPASS','vocabulary'))
    script+=['probe_wait|4000','dict_close','dict_remove|1','dict_add|'+str(two.parent),'dict_settings']
    captures.append((f'STEP\t{len(script)}\tdict_settings\tPASS','dictionary-settings'))
    script+=['probe_wait|4000','quit']
    result=run(exe,font,phase,script,captures)
    for name in ('drive.log','run.drive','result.json'):shutil.copyfile(phase/name,phase/('initial-'+name))
    for i,word in enumerate(WORDS):
        row=json.loads((phase/f'lookup-{i}.dictionary.json').read_text('utf8'))
        assert row['word']==word and row['groups']==2 and row['native_content_matches'] and row['surface_width_dip']<=380
        assert row['sentence'].strip()==SENTENCES[i],(word,row['sentence'])
    raw=json.loads((profile/'vocab.json').read_text('utf8'));assert len(raw['words'])==5
    assert [v['book'] for v in raw['words']]==['Dictionary Acceptance']*4+['Second Book']
    with (phase/'vocabulary.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==5
    for row,v in zip(rows,raw['words']):
        assert row['词']==v['word'] and row['例句']==v['sentence'] and row['释义摘要']==v['summary']
        assert json.loads(row['锚点'])==v['anchor'] and row['书名']==v['book'] and row['时间']==str(v['time_ms'])
    for name,count in [('first.csv',4),('second.csv',1)]:
        with (phase/name).open(encoding='utf-8-sig',newline='') as f:assert len(list(csv.DictReader(f)))==count
    saved=json.loads((profile/'shelf.json').read_text('utf8'));assert saved['unrelated']=={'title':'保留','count':7}
    assert saved['dictionary_auto_lookup'] is True and saved['dictionary_directories']==[str(one.parent),str(two.parent)]
    # Same profile, new process: reload and resolve serialized anchors in both books.
    restart=['open|Dictionary Acceptance']+setup()+['dict_vocab|5','dict_close','dict_roundtrip|4','open|Second Book','wait_idle','dict_roundtrip|1','quit']
    result2=run(exe,font,phase,restart)
    report={'selection_lookups':{'passed':10,'total':10,'manual_shortcut':5,'on_selection':5},'missing':1,'collapse':2,
        'vocabulary':{'saved':5,'csv_sentence_correct':5,'anchor_roundtrips_after_restart':5,'book_filter_counts':[4,1]},
        'shelf_preserved':True,'dictionary_count':2,'dictionary_paths':[str(one),str(two)],'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'runs':[result,result2]}
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
