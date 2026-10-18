"""Original PDF security fixtures, generated with independent pypdf/cryptography.

Requires pypdf and cryptography only when regenerating; no test/runtime dependency.
Deterministic entropy below is FOR TEST FIXTURES ONLY.
"""
from pathlib import Path
from io import BytesIO
import hashlib
import secrets
import zlib
from pypdf._encryption import Encryption, EncryptAlgorithm
from pypdf.generic import BooleanObject, NameObject

root = Path(__file__).resolve().parents[1]/'tests/fixtures/pdf-crypto'
root.mkdir(exist_ok=True)
counter = 0
def fixture_random(n):
    global counter
    out = b''
    while len(out) < n:
        counter += 1
        out += hashlib.sha256(b'EXReader original PDF encryption fixture' + counter.to_bytes(8, 'big')).digest()
    return out[:n]

def make(name, algorithm, user='reader', owner='owner', metadata=True, modern=False,
         identity=False, explicit=False, damage=None, generation=0, incremental=False):
    global counter
    counter = 0
    identifier = b'EXReader-security-test-001'
    e = Encryption.make(algorithm, 0xFFFFF0C4, identifier)
    e.EncryptMetadata = metadata
    dictionary = e.write_entry(user, owner)
    if algorithm.value[0] >= 4:
        dictionary[NameObject('/EncryptMetadata')] = BooleanObject(metadata)
    out = BytesIO(); dictionary.write_to_stream(out)
    enc_dict = out.getvalue()
    if damage == 'handler': enc_dict = enc_dict.replace(b'/Standard', b'/PubSec')
    if damage == 'perms':
        old = e.values.Perms.hex().encode()
        enc_dict = enc_dict.replace(old, (bytes([e.values.Perms[0] ^ 1]) + e.values.Perms[1:]).hex().encode())
    if identity:
        e.StmF = e.StrF = '/Identity'
        enc_dict = enc_dict.replace(b'/StmF /StdCF', b'/StmF /Identity').replace(b'/StrF /StdCF', b'/StrF /Identity')
    def string(number, value, gen=0):
        return b'<' + e._make_crypt_filter(number, gen).str_crypt.encrypt(value).hex().encode() + b'>'
    def stream(number, value, attrs=b'', gen=0, encrypt=True):
        payload = e._make_crypt_filter(number, gen).stm_crypt.encrypt(value) if encrypt else value
        if damage == 'padding' and number == 4:
            # Alter the byte in the previous CBC block that controls the final pad.
            payload = payload[:-17] + bytes([payload[-17] ^ 0x80]) + payload[-16:]
        return b'<< /Length '+str(len(payload)).encode()+b' '+attrs+b' >>\nstream\n'+payload+b'\nendstream'
    content = b'0 1 0 rg 2 2 10 10 re f BT /F1 10 Tf 3 Tr 2 20 Td (Secret text) Tj ET\n'
    attrs = b'/Filter /FlateDecode'
    if explicit: attrs = b'/Filter [/Crypt /FlateDecode] /DecodeParms [<< /Name /StdCF >> null]'
    values = {
        1: b'<< /Type /Catalog /Pages 2 0 R /Metadata 7 0 R /Signatures [<< /Type /Sig /Contents <01020304> >> << /ByteRange [0 1 2 3] /Contents <05060708> >>] >>',
        2: b'<< /Type /Pages /Count 2 /Kids [3 0 R 10 0 R] >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 '+str(generation).encode()+b' R /Annots [8 0 R] >>',
        4: stream(4, zlib.compress(content), attrs, generation),
        5: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
        6: b'<< /Title '+string(6, b'Private title')+b' >>',
        7: stream(7, b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/></x:xmpmeta>', b'/Type /Metadata /Subtype /XML', encrypt=metadata),
        8: b'<< /Type /Annot /Subtype /Text /Rect [1 1 10 10] /Contents '+string(8,b'Private note')+b' >>',
        9: enc_dict,
        10: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 40 40] /Contents 11 0 R >>',
        # Invalid second page exercises lazy reader reconstruction without keeping the password.
        11: stream(11,b'not-a-content-operator'),
    }
    if modern:
        # Embedded strings are encrypted once as part of ObjStm, never individually.
        members = {1: values.pop(1), 2: values.pop(2), 3: values.pop(3),
                   5: values.pop(5), 6: b'<< /Title (Private title) >>',
                   8: b'<< /Type /Annot /Subtype /Text /Rect [1 1 10 10] /Contents (Private note) >>'}
        del values[6], values[8]
        pairs, body = [], bytearray()
        for number,value in members.items():
            pairs.append((number,len(body)));body += value+b'\n'
        header = b''.join(f'{number} {offset} '.encode() for number,offset in pairs)
        values[12] = stream(12,zlib.compress(header+body),f'/Type /ObjStm /N {len(pairs)} /First {len(header)} /Filter /FlateDecode'.encode())
    data = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets = {}
    for number,value in sorted(values.items()):
        offsets[number] = len(data); gen = generation if number == 4 else 0
        data += f'{number} {gen} obj\n'.encode()+value+b'\nendobj\n'
    trailer = b'/Root 1 0 R /Info 6 0 R /Encrypt 9 0 R /ID [<'+identifier.hex().encode()+b'><'+identifier.hex().encode()+b'>]'
    xref = len(data)
    if modern:
        offsets[13] = xref
        compressed = {number:i for i,number in enumerate(members)}
        rows = bytearray(b'\0\0\0\0\0\xff\xff')
        for number in range(1,14):
            if number in compressed: kind,field,gen = 2,12,compressed[number]
            elif number in offsets: kind,field,gen = 1,offsets[number],generation if number == 4 else 0
            else: kind,field,gen = 0,0,0
            rows += bytes([kind])+field.to_bytes(4,'big')+gen.to_bytes(2,'big')
        payload = zlib.compress(rows)
        # Xref stream stays unencrypted, including its /ID strings.
        data += b'13 0 obj\n<< /Type /XRef /Size 14 /W [1 4 2] /Filter /FlateDecode '+trailer+b' /Length '+str(len(payload)).encode()+b' >>\nstream\n'+payload+b'\nendstream\nendobj\n'
    else:
        data += b'xref\n0 12\n0000000000 65535 f \n'
        for number in range(1,12):
            data += f'{offsets[number]:010d} {generation if number==4 else 0:05d} n \n'.encode()
        data += b'trailer\n<< /Size 12 '+trailer+b' >>\n'
    data += b'startxref\n'+str(xref).encode()+b'\n%%EOF\n'
    if incremental:
        offset = len(data)
        data += b'12 0 obj\n<< /Title '+string(12,b'Private title')+b' >>\nendobj\n'
        latest = len(data)
        data += b'xref\n12 1\n'+f'{offset:010d} 00000 n \n'.encode()
        data += b'trailer\n<< /Size 13 /Info 12 0 R /Prev '+str(xref).encode()+b' /ID [<'+identifier.hex().encode()+b'><01020304>] >>\nstartxref\n'+str(latest).encode()+b'\n%%EOF\n'
    (root/(name+'.pdf')).write_bytes(data)

if __name__ == '__main__':
    original = secrets.token_bytes
    secrets.token_bytes = fixture_random
    try:
        for name,alg in [('r2',EncryptAlgorithm.RC4_40),('r3',EncryptAlgorithm.RC4_128),
                         ('r4',EncryptAlgorithm.AES_128),('r5',EncryptAlgorithm.AES_256_R5),('r6',EncryptAlgorithm.AES_256)]:
            make(name,alg,generation=17)
            make(name+'-empty',alg,user='')
            make(name+'-objects',alg,modern=True)
            if alg.value[0]>=4:
                make(name+'-metadata-clear',alg,metadata=False)
                make(name+'-identity',alg,identity=True)
                make(name+'-crypt',alg,explicit=True)
        make('r6-unicode',EncryptAlgorithm.AES_256,user='I\u00adX\u2168\u00aa\u00a0\u1100\u1161\u11a8\u00e9',owner='\u0627\u0628')
        make('r6-long',EncryptAlgorithm.AES_256,user='x'*140)
        make('r4-incremental',EncryptAlgorithm.AES_128,incremental=True)
        make('r6-bad-perms',EncryptAlgorithm.AES_256,damage='perms')
        make('r6-bad-padding',EncryptAlgorithm.AES_256,damage='padding')
        make('unsupported-handler',EncryptAlgorithm.AES_128,damage='handler')
    finally:
        secrets.token_bytes = original
    print(len(list(root.glob('*.pdf'))),'original fixtures generated')
