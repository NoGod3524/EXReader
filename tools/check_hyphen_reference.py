#!/usr/bin/env python3
"""Development oracle; Pyphen is never an SDK dependency.

python tools/check_hyphen_reference.py DLL --oracle-dir /private/pyphen-install
Input dictionaries remain in the external oracle install, with their own licenses.
All input dictionaries are tested unchanged. Compound/separator behavior is
verified separately; this comparison uses standalone alphabetic words.
"""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import random
import re
import sys

class Error(c.Structure):
    _fields_=[('code',c.c_int),('message',c.c_char*256)]
class Input(c.Structure):
    _fields_=[('struct_size',c.c_size_t),('language',c.c_char_p),('patterns',c.c_void_p),
      ('size',c.c_size_t),('left_min',c.c_uint),('right_min',c.c_uint)]

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('library',type=Path);p.add_argument('--oracle-dir',type=Path,required=True)
    p.add_argument('--output',type=Path);a=p.parse_args();sys.path.insert(0,str(a.oracle_dir))
    import pyphen
    root=Path(pyphen.__file__).parent/'dictionaries';dll=c.CDLL(str(a.library.resolve()));pointer=c.c_void_p;error=Error()
    dll.exr_hyphenator_create_patterns.argtypes=[c.POINTER(Input),c.c_size_t,c.c_size_t,pointer,c.POINTER(pointer),c.POINTER(Error)]
    dll.exr_hyphenator_breaks.argtypes=[pointer,c.c_char_p,c.c_char_p,c.c_size_t,pointer,pointer,c.POINTER(Error)]
    dll.exr_hyphenator_memory_size.argtypes=[pointer];dll.exr_hyphenator_memory_size.restype=c.c_size_t
    dll.exr_hyphenator_free.argtypes=[pointer]
    samples={
      'en_US':'hyphenation dictionary international representation computer typography extraordinary compatibility alphabetic university',
      'fr':'bibliothèque lecture international extraordinaire représentation typographie université connaissance électricité français',
      'es':'biblioteca lectura internacional extraordinario representación tipografía universidad conocimiento electricidad español',
      'it_IT':'biblioteca lettura internazionale rappresentazione straordinario università conoscenza elettricità sillabazione italiano',
      'ru_RU':'библиотека чтение международный представление университет электричество совместимость типография русский автоматический',
    }
    reports=[];rng=random.Random(180325)
    for language,sample in samples.items():
        path=root/('hyph_'+language+'.dic');data=path.read_bytes();text=data.decode('utf-8');removed=[]
        portable=text.encode('utf-8');assert portable==data
        buffer=c.create_string_buffer(portable);tag=language.replace('_','-').encode()
        left=next((int(x.split()[1]) for x in text.splitlines() if x.startswith('LEFTHYPHENMIN ')),2)
        right=next((int(x.split()[1]) for x in text.splitlines() if x.startswith('RIGHTHYPHENMIN ')),2)
        source=Input(c.sizeof(Input),tag,c.cast(buffer,pointer),len(portable),0,0);h=pointer()
        assert dll.exr_hyphenator_create_patterns(c.byref(source),1,0,None,c.byref(h),c.byref(error))==0,(language,error.message)
        try:
            oracle=pyphen.Pyphen(filename=path,left=left,right=right,cache=False)
            keys=[re.sub(r'[0-9.]','',line) for line in text.splitlines()[1:]]
            keys=[key for key in keys if key.isalpha() and 2<=len(key)<=20]
            words=set(sample.split());words.update(rng.choice(keys)+rng.choice(keys) for _ in range(4000))
            count=0;checked=0
            for word in sorted(words):
                if word.casefold()!=word.lower(): continue # Case-fold expansion is tested separately in native tests.
                encoded=word.encode();out=(c.c_ubyte*(len(encoded)+1))()
                assert dll.exr_hyphenator_breaks(h,tag,encoded,len(encoded),out,None,c.byref(error))==0,(language,word,error.message)
                expected={len(word[:int(i)].encode()) for i in oracle.positions(word)}
                actual={i for i,x in enumerate(out) if x}
                assert expected==actual,(language,word,expected,actual)
                count+=len(actual);checked+=1
            report={'language':language,'words':checked,'breaks':count,'dictionary_sha256':hashlib.sha256(data).hexdigest(),
              'portable_sha256':hashlib.sha256(portable).hexdigest(),'input_projection':removed,'dictionary_bytes':len(data),
              'native_payload_bytes':dll.exr_hyphenator_memory_size(h),'left_min':left,'right_min':right}
            reports.append(report);print(language,checked,'words matched;',count,'breaks;',report['native_payload_bytes'],'native bytes',flush=True)
        finally: dll.exr_hyphenator_free(h)
    result={'oracle':'Pyphen '+pyphen.__version__,'seed':180325,'library_sha256':hashlib.sha256(a.library.read_bytes()).hexdigest(),'dictionaries':reports}
    if a.output: a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
if __name__=='__main__': main()
