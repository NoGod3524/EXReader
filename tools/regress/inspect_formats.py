"""Independently inventory source structure; persist only metadata, never content.

PyMuPDF is a reference reader here, not the renderer under test. This optional
inspection command is separate from the stdlib-only regression driver.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from run_realbooks import file_hash, read_json, write_json


def inspect(book):
    path = Path(book['path'])
    assert file_hash(path) == book['sha256'], book['id']
    result = dict(id=book['id'], sha256=book['sha256'])
    if path.suffix.lower() == '.pdf':
        import pymupdf
        with pymupdf.open(path) as document:
            result['encrypted'] = document.is_encrypted
            if document.is_encrypted:
                import os
                assert document.authenticate(os.environ[book['password_env']])
            result.update(page_count=len(document),
                          text_bytes=sum(len(p.get_text().encode('utf-8')) for p in document),
                          image_pages=sum(bool(p.get_images()) for p in document),
                          reference='PyMuPDF ' + pymupdf.VersionBind)
    elif path.suffix.lower() in ('.epub', '.cbz'):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result['image_members'] = sum(n.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')) for n in names)
            if path.suffix.lower() == '.epub':
                if 'META-INF/encryption.xml' in names:
                    encryption = ET.fromstring(archive.read('META-INF/encryption.xml'))
                    result['encryption_algorithms'] = [e.attrib['Algorithm'] for e in encryption.iter()
                                                        if e.tag.endswith('EncryptionMethod')]
                    result['encrypted_resource_count'] = sum(e.tag.endswith('CipherReference') for e in encryption.iter())
                    result['embedded_lcp_license'] = 'META-INF/license.lcpl' in names
                root = ET.fromstring(archive.read('META-INF/container.xml'))
                opf = next(e.attrib['full-path'] for e in root.iter() if e.tag.endswith('rootfile'))
                package = ET.fromstring(archive.read(opf))
                result['spine_item_count'] = sum(e.tag.endswith('itemref') for e in package.iter())
                result['rendition_metadata'] = [{k: v for k, v in e.attrib.items()} | {'value': e.text or ''}
                                                for e in package.iter() if e.tag.endswith('meta') and
                                                ('rendition' in str(e.attrib) or e.attrib.get('name') == 'fixed-layout')]
                result['media_members'] = [dict(name=n, bytes=archive.getinfo(n).file_size)
                                           for n in names if n.lower().endswith(('.mp3', '.mp4', '.smil'))]
    else:
        text = path.read_bytes().decode(book['encoding'])
        result.update(encoding=book['encoding'], unicode_characters=len(text),
                      contains_cjk=any('\u4e00' <= c <= '\u9fff' for c in text))
    return result


def matrix(run, reference):
    refs = {r['id']: r for r in reference['books']}
    lines = ['| 格式 | 样本 | 能打开 | 页数 | 首屏 | 缩放/重排 | 文字可选 | 图片 | 备注 |',
             '|---|---|---|---|---|---|---|---|---|']
    for b in run['books']:
        ref = refs[b['id']]
        opened = b.get('open') or {}
        error = b.get('error') or {}
        code = opened.get('code', error.get('code', '未测'))
        opening = '是(0)' if code == 0 else f'不支持({code})'
        count = f"{b['page_count']}"
        if 'page_count' in ref:
            count += f"；参考 {ref['page_count']}"
        first = b.get('first_screen')
        screen = (f"{first['width']}×{first['height']}；非白分量 {first['nonwhite_components']}" if first else
                  f"不支持({error.get('code', code)})")
        zoom = b.get('zoom_2x')
        alt = b.get('alternate') or {}
        resizing = (f"2×→{zoom['width']}×{zoom['height']}；无重排" if zoom else
                    f"480×800/36px：{alt['page_count']}页({alt.get('status')})" if alt.get('status') == 'ok' else
                    f"不支持({(alt.get('error') or error).get('code', code)})")
        selection = b.get('selection')
        if selection:
            if 'select' in selection:
                selectable = f"查找{selection['search']['code']}/选择{selection['select']['code']}；{selection['regions']}区域"
            else:
                selectable = f"查找{selection['search']['code']}；匹配{int(selection['search_matched'])}/命中{int(selection['hit_in_source'])}"
        elif b.get('status') == 'ok':
            selectable = f"不支持；无文字层/字形({b['text_bytes']}字节)"
            empty = b.get('empty_text_probe')
            if empty:
                selectable += f"；查找{empty['search']['code']}/命中{int(empty['matched'])}；选择{empty['select']['code']}"
        else:
            selectable = f"不支持({error.get('code', code)})"
        if b['category'].startswith('PDF'):
            images = f"参考{ref.get('image_pages', 0)}页有图；SDK已绘{b.get('rendered_page_count', 0)}页"
        elif b['category'].startswith('CBZ'):
            images = f"{ref['image_members']}图；SDK已绘{b.get('rendered_page_count', 0)}页"
        elif b['category'].startswith('TXT'):
            images = '源无图(0)'
        else:
            images = f"源{ref['image_members']}图；SDK图片框{b.get('image_boxes', 0)}"
        if b.get('status') == 'error' and not b.get('rendered_page_count') and not b['category'].startswith('TXT'):
            images = f"不支持({error.get('code', code)})；" + images
        notes = [b['regression']]
        if b.get('fixed_entry'):
            notes.append(f"固定入口{b['fixed_entry']['code']}")
        if b.get('epub_pcm_entry'):
            notes.append(f"EPUB→PCM {b['epub_pcm_entry']['code']}")
            notes += [f"{Path(a['member']).suffix}→PCM {a['open']['code']}" for a in b.get('audio_assets', [])]
        if b.get('without_password'):
            notes.append(f"无/错密码 {b['without_password']['code']}/{b['wrong_password']['code']}")
        if b.get('text_matches_source') is not None:
            notes.append(f"文本一致{int(b['text_matches_source'])}")
        if error:
            notes.append(f"{error['stage']}:{error['code']}")
        if b.get('max_render_pages'):
            notes.append(f"仅尝试前{b['max_render_pages']}页")
        lines.append('| ' + ' | '.join([b['category'], b['id'], opening, count, screen,
                                       resizing, selectable, images, '；'.join(notes)]) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--matrix', type=Path)
    args = parser.parse_args()
    reference = {'books': [inspect(b) for b in read_json(args.manifest)['books']]}
    write_json(args.output, reference)
    if args.run and args.matrix:
        args.matrix.write_text(matrix(read_json(args.run), reference), encoding='utf-8')


if __name__ == '__main__':
    main()
