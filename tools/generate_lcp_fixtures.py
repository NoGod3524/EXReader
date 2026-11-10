#!/usr/bin/env python3
"""Generate offline Basic Profile vectors using Python cryptography, not SDK crypto.

Only regeneration needs cryptography. CTest reads the checked-in EPUBs.
Use the PUBLIC test certificate/key from readium/readium-lcp-server/test/cert;
these are test credentials, never a publisher's production private key.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import zipfile
import zlib

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

AES = 'http://www.w3.org/2001/04/xmlenc#aes256-cbc'
SHA = 'http://www.w3.org/2001/04/xmlenc#sha256'
PASS = 'LCP café 口令'
KEY = bytes(range(32))
LICENSE = 'META-INF/license.lcpl'


def encrypted(data, key, label):
    iv = hashlib.sha256(label.encode()).digest()[:16]  # reproducible test IVs only
    n = 16 - len(data) % 16
    # XML Encryption permits arbitrary preceding pad bytes; exercise that rule.
    data += bytes([0xA5]) * (n - 1) + bytes([n])
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return iv + cipher.update(data) + cipher.finalize()


def packed(path, entries):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--certificate', type=Path, required=True)
    ap.add_argument('--key', type=Path, required=True)
    ap.add_argument('--output', type=Path, default=Path('tests/fixtures/lcp'))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cert = x509.load_pem_x509_certificate(args.certificate.read_bytes())
    signer = serialization.load_pem_private_key(args.key.read_bytes(), password=None)

    def signed(license):
        license = copy.deepcopy(license)
        canon = json.dumps(license, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        signature = signer.sign(canon, padding.PKCS1v15(), hashes.SHA256())
        license['signature'] = dict(
            algorithm='http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
            certificate=base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode(),
            value=base64.b64encode(signature).decode())
        return json.dumps(license, ensure_ascii=True, indent=2).encode()

    entries = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'EPUB/book.opf': b'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">urn:uuid:8d2cb040-0000-4000-8000-000000000001</dc:identifier><dc:title>LCP fixture</dc:title><dc:language>en</dc:language></metadata><manifest><item id="c" href="chapter%20one.xhtml" media-type="application/xhtml+xml"/><item id="css" href="style.css" media-type="text/css"/><item id="svg" href="image.svg" media-type="image/svg+xml"/><item id="empty" href="empty.css" media-type="text/css"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="c"/></spine></package>''',
        'EPUB/chapter one.xhtml': ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>LCP</title><link rel="stylesheet" href="style.css"/></head><body><h1>Memory only</h1>' + '<p>The reader decrypts a resource when it is requested. café 口令.</p>' * 40 + '<img src="image.svg" alt="rectangle"/></body></html>').encode(),
        'EPUB/style.css': b'p { margin-bottom: 10px; } h1 { color: #123456; }',
        'EPUB/image.svg': b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="24"><rect width="32" height="24" fill="blue"/></svg>',
        'EPUB/empty.css': b'',
        'EPUB/nav.xhtml': b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="chapter%20one.xhtml">Memory only</a></li></ol></nav></body></html>',
    }
    packed(args.output / 'clear.epub', entries)
    protected = dict(entries)
    xml = '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:e="http://www.w3.org/2001/04/xmlenc#" xmlns:d="http://www.w3.org/2000/09/xmldsig#" xmlns:c="http://www.idpf.org/2016/encryption#compression">'
    for name, method in [('EPUB/chapter one.xhtml', 8), ('EPUB/style.css', 8), ('EPUB/image.svg', 0), ('EPUB/empty.css', 8)]:
        data = entries[name]
        if method == 8:
            compressor = zlib.compressobj(wbits=-15)
            data = compressor.compress(data) + compressor.flush()
        protected[name] = encrypted(data, KEY, name)
        uri = name.replace(' ', '%20')
        xml += f'<e:EncryptedData><e:EncryptionMethod Algorithm="{AES}"/><d:KeyInfo><d:RetrievalMethod URI="license.lcpl#/encryption/content_key" Type="http://readium.org/2014/01/lcp#EncryptedContentKey"/></d:KeyInfo><e:CipherData><e:CipherReference URI="{uri}"/></e:CipherData><e:EncryptionProperties><e:EncryptionProperty><c:Compression Method="{method}" OriginalLength="{len(entries[name])}"/></e:EncryptionProperty></e:EncryptionProperties></e:EncryptedData>'
    xml += '</encryption>'
    protected['META-INF/encryption.xml'] = xml.encode()
    user = hashlib.sha256(PASS.encode()).digest()
    license = dict(id='8d2cb040-0000-4000-8000-000000000001', provider='https://example.org/lcp-test',
                   issued='2020-01-01T00:00:00Z',
                   encryption=dict(profile='http://readium.org/lcp/basic-profile',
                                   content_key=dict(algorithm=AES, encrypted_value=base64.b64encode(encrypted(KEY, user, 'key')).decode()),
                                   user_key=dict(algorithm=SHA, text_hint='The documented UTF-8 test passphrase',
                                                 key_check=base64.b64encode(encrypted(b'8d2cb040-0000-4000-8000-000000000001', user, 'check')).decode())),
                   rights=dict(start='2019-12-31T19:00:00-05:00', end='2999-12-31T23:59:59.75+05:30'),
                   links=[dict(rel='hint', href='https://example.org/lcp-test/hint')])

    def save(name, l=None, book=None, raw=None):
        data = dict(protected if book is None else book)
        data[LICENSE] = raw if raw is not None else signed(license if l is None else l)
        packed(args.output / (name + '.epub'), data)

    save('normal')
    packed(args.output / 'missing-license.epub', protected)
    alias = dict(protected)
    alias['META-INF/encryption.xml'] = xml.replace('license.lcpl#', 'license.lcp.json#').encode()
    alias['META-INF/license.lcp.json'] = signed(license)
    packed(args.output / 'alias.epub', alias)
    for name, end in [('expired', '2001-02-03T04:05:06Z'), ('expired-offset', '2001-02-03T09:35:06.125+05:30')]:
        l = copy.deepcopy(license)
        l['rights'] = dict(end=end)
        save(name, l)
    for name, where, val in [
        ('profile', ('encryption', 'profile'), 'http://readium.org/lcp/profile-2.5'),
        ('kdf', ('encryption', 'user_key', 'algorithm'), 'urn:unsupported:pbkdf2'),
        ('cipher', ('encryption', 'content_key', 'algorithm'), 'urn:unsupported:aes-gcm'),
        ('bad-date', ('rights', 'end'), '2001-02-30T12:00:00Z'),
        ('bad-base64', ('encryption', 'user_key', 'key_check'), 'not/base64?!'),
        ('future', ('rights', 'start'), '2999-01-01T00:00:00Z'),
    ]:
        l = copy.deepcopy(license)
        obj = l
        for key in where[:-1]:
            obj = obj[key]
        obj[where[-1]] = val
        save(name, l)
    for name, old, new in [
        ('resource-algorithm', AES, 'urn:unsupported:resource'),
        ('compression', 'Method="8"', 'Method="99"'),
        ('unsafe-path', 'URI="EPUB/chapter%20one.xhtml"', 'URI="../../escape.xhtml"'),
        ('length', 'OriginalLength="0"', 'OriginalLength="1"'),
        ('oversize', 'OriginalLength="0"', 'OriginalLength="99999999999"'),
    ]:
        b = dict(protected)
        b['META-INF/encryption.xml'] = xml.replace(old, new).encode()
        save(name, book=b)
    b = dict(protected)
    b['EPUB/chapter one.xhtml'] = b['EPUB/chapter one.xhtml'][:-1]
    save('truncated', book=b)
    save('duplicate', raw=b'{"id":"a","id":"b"}')
    save('json-depth', raw=b'{"extension":' + b'[' * 40 + b'0' + b']' * 40 + b'}')
    save('json-trailing', raw=signed(license) + b'\x00')
    b = dict(protected)
    b['META-INF/encryption.xml'] = xml.replace('<encryption ', '<encryption><!DOCTYPE x><encryption ', 1).encode()
    save('bad-xml', book=b)
    b = dict(entries)
    b['META-INF/rights.xml'] = b'<adept:rights xmlns:adept="http://ns.adobe.com/adept"/>'
    packed(args.output / 'adept-marker.epub', b)
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.glob('*.epub'))}
    (args.output / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Generated {len(manifest)} EPUBs in {args.output}')


if __name__ == '__main__':
    main()
