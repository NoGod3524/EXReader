#!/usr/bin/env python3
"""Original EPUB cases for independent table-cell continuation and shared grids."""
# SPDX-License-Identifier: MIT
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]/'tests/fixtures'
with ZipFile(root/'float-both.epub') as z: base={n:z.read(n) for n in z.namelist()}
words='Abc def '*120;other='Xyz '*120
for test in range(24):
    mode=lead=decoration=inside=table=''
    if test==1:decoration='border:3px solid #30408080;background:#ffe080;padding:4px'
    if test==2:table='border-collapse:collapse;border:3px solid #30408080'
    if test==3:decoration='vertical-align:middle;background:#80ffaa'
    if test==4:decoration='vertical-align:bottom;background:#80ffaa'
    if test==5:lead='<p>Before<br/>table</p>'
    if test==6:mode='writing-mode:vertical-rl'
    if test==7:mode='writing-mode:vertical-lr'
    if test==8:inside="<div style='float:left;width:14px;height:100px'>X</div>"
    if test==9:inside="<img src='image.png' style='width:28px;height:40px'/>"
    body=f"{lead}<table style='width:140px;{table}'><tr><td style='{decoration}'>{inside}{words}</td><td style='font-size:18px;line-height:27px;border:2px solid blue'>{other}</td></tr><tr><td>Tail</td><td>End</td></tr></table><p>After table</p>"
    if test==10:body=f"<table style='width:140px'><tr><td rowspan='3'>{words}</td><td>First</td></tr><tr><td>Second</td></tr><tr><td>{other}</td></tr></table>"
    if test==11:body=f"<table style='width:140px;border-collapse:collapse;border:3px solid #30408080'><tr><td rowspan='2' style='vertical-align:bottom;background:#80ffaa'>{words}</td><td>{other}</td></tr><tr><td>{other}</td></tr></table>"
    if test==12:body=f"<table style='width:140px;border-collapse:collapse;border:2px solid blue'><tr><td rowspan='2'>{words}</td><td>{other}</td></tr><tr><td rowspan='2'>{words}</td></tr><tr><td>{other}</td></tr></table>"
    if test==13:body=f"<table style='width:140px'><tr><td rowspan='2' colspan='2'>{words}</td><td>{other}</td></tr><tr><td>{other}</td></tr></table>"
    if test==14:body=f"<table style='width:140px'><tr><td><p>Before nested</p><table style='width:60px;border:1px solid blue'><tr><td>{words}</td><td>{other}</td></tr></table><p>After nested</p></td><td>{other}</td></tr></table>"
    if test==15:body=f"<table style='width:140px'><tr><td><div style='writing-mode:vertical-rl;height:56px;width:28px'>{words}</div></td><td>{other}</td></tr></table>"
    if test==16:body="<table style='width:140px'><tr style='height:600px'><td style='vertical-align:bottom;background:#80ffaa'>Short</td><td>Peer</td></tr></table>"
    if test==17:body=f"<table style='width:140px;border-collapse:collapse;border:3px solid blue'><tr><td style='vertical-align:bottom;background:#80ffaa'></td><td>{words}</td></tr></table>"
    if test==18:body=f"<table style='width:140px'><tr><td rowspan='100'>{words}</td><td>Row 0</td></tr>"+''.join(f"<tr><td>Row {i}</td></tr>" for i in range(1,100))+"</table>"
    if test==19:body=f"<table style='width:140px'><tr><td rowspan='3' style='vertical-align:middle;background:#80ffaa'>{words}</td><td style='font-size:18px;line-height:27px'>{other}</td></tr><tr><td style='font-size:10px;line-height:17px'>{words}</td></tr><tr><td>{other}</td></tr></table>"
    if test==20:body="<p>Lead</p><table style='width:140px;table-layout:fixed;border-collapse:collapse;border:3px solid blue'><tr style='height:60px'><td style='vertical-align:middle'><ruby>Ab<rt>CD</rt></ruby></td><td style='vertical-align:bottom'>End</td></tr></table><p>After</p>"
    if test==21:body="<table style='width:140px;table-layout:fixed'><tr><td rowspan='100' style='vertical-align:bottom'>Span end</td><td>Row 0</td></tr>"+''.join(f"<tr><td style='vertical-align:middle'>Row {i}</td></tr>" for i in range(1,100))+"</table>"
    if test==22:body=f"<table style='width:140px;table-layout:fixed;border-collapse:collapse;border:3px solid #30408080'><tr><td style='vertical-align:middle'><div style='float:left;width:14px;height:80px'>X</div><ruby>Ab<rt>CD</rt></ruby><span dir='rtl'>שָׁלוֹם 123</span>{words}<img src='image.png' style='width:28px;height:40px'/></td><td style='vertical-align:bottom'><table style='width:60px'><tr><td>{other}</td></tr></table></td></tr></table>"
    if test==23:
        mode='writing-mode:vertical-lr'
        body=f"<table style='height:140px;table-layout:fixed'><tr><td style='vertical-align:bottom'><ruby>Ab<rt>CD</rt></ruby>{words}</td><td style='vertical-align:middle'><img src='image.png' style='width:28px;height:40px'/>{other}</td></tr></table>"
    files=dict(base)
    files['chapter.xhtml']=(f'<html xmlns="http://www.w3.org/1999/xhtml" style="{mode}"><head><title>Table fragments {test}</title><link rel="stylesheet" href="style.css"/></head><body>{body}</body></html>').encode()
    files['style.css']=b'html,body,p,div,table,tr,td {margin:0;padding:0;font-size:14px;line-height:20px}'
    with ZipFile(root/f'table-fragments-{test}.epub','w') as z:
        for key,data in files.items():
            info=ZipInfo(key,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if key=='mimetype' else ZIP_DEFLATED
            z.writestr(info,data)
for name,counts,outside in [('float-128',(64,64),False),('float-129',(64,64,1),False),('float-tree-129',(64,64),True)]:
    body="<div style='float:right;width:1px;height:1000px;background:blue'></div>" if outside else ''
    body+=f"<table style='width:{len(counts)*160}px'><tr>"
    for count in counts:body+="<td>"+"<div style='float:left;width:1px;height:1000px;background:blue'></div>"*count+"</td>"
    body+="</tr></table><p>After</p>"
    files=dict(base);files['style.css']=b'html,body,p,div,table,tr,td {margin:0;padding:0;font-size:14px;line-height:20px}'
    files['chapter.xhtml']=(f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{name}</title><link rel="stylesheet" href="style.css"/></head><body>{body}</body></html>').encode()
    with ZipFile(root/f'table-fragments-{name}.epub','w') as z:
        for key,data in files.items():
            info=ZipInfo(key,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if key=='mimetype' else ZIP_DEFLATED;z.writestr(info,data)
files=dict(base);files['style.css']=b'html,body,p,div,table,tr,td {margin:0;padding:0;font-size:14px;line-height:20px}'
files['chapter.xhtml']=('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Large fixed table</title><link rel="stylesheet" href="style.css"/></head><body><table style="width:360px;table-layout:fixed"><tr><td>'+('Abc def '*131072)+'</td><td>Peer</td></tr></table></body></html>').encode()
with ZipFile(root/'table-fragments-large-fixed.epub','w') as z:
    for key,data in files.items():
        info=ZipInfo(key,(2026,1,1,0,0,0));info.compress_type=ZIP_STORED if key=='mimetype' else ZIP_DEFLATED;z.writestr(info,data)
print('28 original table-fragment EPUBs generated')
