#!/usr/bin/env python3
"""ISO 32000-1 RGB group arithmetic, independent 40-digit test reference.

This evaluates known full-coverage interior probes, not PDF syntax or geometry.
Raw renderer outputs remain separate. No EXReader code or runtime is loaded.
"""
# SPDX-License-Identifier: GPL-3.0-only
from decimal import Decimal as D, localcontext

ZERO=(D(0),)*4
ONE=D(1)


def color(values):return tuple(D(v)/255 for v in values)


def blend(b,s,mode):
    def lum(c):return sum(x*w for x,w in zip(c,(D('.3'),D('.59'),D('.11'))))
    def sat(c):return max(c)-min(c)
    def setlum(c,l):
        c=[x+l-lum(c) for x in c];low,high=min(c),max(c)
        if low<0:c=[l+(x-l)*l/(l-low) for x in c]
        if high>1:c=[l+(x-l)*(1-l)/(high-l) for x in c]
        return c
    def setsat(c,value):
        lo,mid,hi=sorted(range(3),key=lambda i:c[i]);result=[D(0)]*3
        if c[hi]>c[lo]:result[mid]=(c[mid]-c[lo])*value/(c[hi]-c[lo]);result[hi]=value
        return result
    if mode=='Hue':return setlum(setsat(s,sat(b)),lum(b))
    if mode=='Saturation':return setlum(setsat(b,sat(s)),lum(b))
    if mode=='Color':return setlum(s,lum(b))
    if mode=='Luminosity':return setlum(b,lum(s))
    def channel(cb,cs):
        if mode=='Normal':return cs
        if mode=='Multiply':return cb*cs
        if mode=='Screen':return cb+cs-cb*cs
        if mode=='Overlay':return 2*cb*cs if cb<=D('.5') else 1-2*(1-cb)*(1-cs)
        if mode=='Darken':return min(cb,cs)
        if mode=='Lighten':return max(cb,cs)
        if mode=='ColorDodge':return ONE if cs==1 else min(ONE,cb/(1-cs))
        if mode=='ColorBurn':return D(0) if cs==0 else 1-min(ONE,(1-cb)/cs)
        if mode=='HardLight':return 2*cb*cs if cs<=D('.5') else 1-2*(1-cb)*(1-cs)
        if mode=='SoftLight':
            curve=((16*cb-12)*cb+4)*cb if cb<=D('.25') else cb.sqrt()
            return cb-(1-2*cs)*cb*(1-cb) if cs<=D('.5') else cb+(2*cs-1)*(curve-cb)
        if mode=='Difference':return abs(cb-cs)
        if mode=='Exclusion':return cb+cs-2*cb*cs
        raise ValueError(mode)
    return tuple(channel(cb,cs) for cb,cs in zip(b,s))


def over(back,source,alpha,mode):
    cb=tuple(v/back[3] for v in back[:3]) if back[3] else (D(0),)*3
    mixed=blend(cb,source,mode)
    return tuple((1-alpha)*pb+alpha*((1-back[3])*cs+back[3]*bm)
        for pb,cs,bm in zip(back,source,mixed))+(alpha+back[3]*(1-alpha),)


def group(back,elements,isolated=False,knockout=False):
    """Evaluate one transparency group at a fully covered interior probe.

    knockout=False: each element composites with the accumulated result.
    knockout=True: each element composites with the group's *initial* backdrop;
    a fully covered probe therefore keeps only the newest covering element
    instead of accumulating earlier ones. Zero-coverage elements change nothing.
    """
    initial=ZERO if isolated else back
    result=initial;group_alpha=D(0)
    for source,alpha,mode in elements:
        if callable(source):
            source,inner_alpha=source(initial if knockout else result);alpha*=inner_alpha
        if knockout:
            if alpha:result=over(initial,source,alpha,mode)
        else:
            result=over(result,source,alpha,mode)
        group_alpha+=alpha*(1-group_alpha)
    if not group_alpha:return (D(0),)*3,D(0)
    return tuple((v-(1-group_alpha)*b)/group_alpha for v,b in zip(result[:3],initial)),group_alpha


def probe(row,mode):
    with localcontext() as context:
        context.prec=40
        a=D(128)/255;red=color((255,0,0));green=color((0,255,0));blue=color((0,0,255))
        base_alpha=D((255,128,192,0,64,192,255,1,128,255)[row])/255
        back=tuple(v*base_alpha for v in color((51,102,153)))+(base_alpha,)
        iso=lambda bg:group(bg,[(red,a,'Multiply'),(green,a,'Multiply')],True)
        nested=lambda bg:group(bg,[(blue,a,'Multiply'),(red,a,'Multiply')])
        paints=[[(color((255,51,128)),a,'Multiply')],[(green,a,'Multiply')],
            [(color((204,77,26)),a*a,'Multiply')],[(color((255,51,128)),a,'Multiply')],
            [(green,D(64)/255,'HardLight')],[(iso,a,'Multiply')],[(nested,a,'Multiply')],
            [(color((252,255,0)),D(1)/255,'ColorDodge')],[],[(color((255,255,0)),a,'Multiply')]]
        source,alpha=group(back,paints[row]);result=over(back,source,alpha*a,mode)
        byte=lambda x:max(0,min(255,int((x*255).to_integral_value(rounding='ROUND_HALF_UP'))))
        return bytes(map(byte,result)),bytes(byte(v+1-result[3]) for v in result[:3])+b'\xff'


def ap_probe(mode,white):
    with localcontext() as context:
        context.prec=40
        a=D(192)/255;back=tuple(v*a for v in color((51,102,153)))+(a,)
        if white:back=tuple(v+1-a for v in back[:3])+(ONE,)
        source,alpha=group(back,[(color((255,0,0)),a,'Normal'),(color((0,255,0)),D(128)/255,mode)])
        result=over(back,source,alpha,'Normal')
        return bytes(max(0,min(255,int((v*255).to_integral_value(rounding='ROUND_HALF_UP')))) for v in result)


def verify(directory):
    from pathlib import Path
    import json
    root=Path(directory);manifest=json.loads((root/'manifest.json').read_text())
    raw=(root/'flat-pdfium-alpha.rgba').read_bytes();maximum=0
    with localcontext() as context:
        context.prec=40
        for row,(bg,ba,fg,fa) in enumerate(manifest['color_cases']):
            back=tuple(v*D(ba)/255 for v in color(bg))+(D(ba)/255,)
            for col,mode in enumerate(manifest['modes']):
                expected=over(back,color(fg),D(fa)/255,mode)
                expected=bytes(max(0,min(255,int((v*255).to_integral_value(rounding='ROUND_HALF_UP')))) for v in expected)
                i=(((len(manifest['color_cases'])-1-row)*16+6)*256+col*16+6)*4
                difference=max(abs(a-b) for a,b in zip(expected,raw[i:i+4]));maximum=max(maximum,difference)
                assert difference<=3,(row,mode,expected,list(raw[i:i+4]))
    records=json.loads((root/'nonisolated-oracle.json').read_text())['probes']
    assert len(records)==160
    for record in records:
        alpha,white=probe(record['row'],record['mode'])
        assert record['premultiplied_expected']==list(alpha) and record['white_expected']==list(white)
    print('208 independent blend samples match PDFium within',maximum,'and 160 group probes reproduce exactly')


def self_test():
    """Knockout invariants that do not depend on any renderer output."""
    with localcontext() as context:
        context.prec=40
        a=D(128)/255;red=color((255,0,0));green=color((0,255,0));blue=color((0,0,255))
        ba=D(192)/255;back=tuple(v*ba for v in color((51,102,153)))+(ba,)
        elements=[(red,a,'Multiply'),(green,D(1)/255,'Normal'),(blue,a,'Screen')]
        knockout=group(back,elements,knockout=True)
        # Group alpha is the union of every element's coverage, not just the top one.
        last_alpha=D(1)/255;a_union=1-(1-a)*(1-last_alpha)*(1-a)
        expected=over(back,blue,a,'Screen')
        expected=tuple((v-(1-a_union)*b)/a_union for v,b in zip(expected[:3],back)),a_union
        assert knockout[1]==expected[1]
        for got,want in zip(knockout[0],expected[0]):
            assert abs(got-want)<D('1e-30'),(got,want)
        accumulated=group(back,elements)
        assert any(abs(x-y)>D('1e-6') for x,y in zip(knockout[0],accumulated[0]))
        swapped=group(back,list(reversed(elements)),knockout=True)
        assert any(abs(x-y)>D('1e-6') for x,y in zip(knockout[0],swapped[0]))
        assert knockout[1]==swapped[1]
        covered=group(back,[(red,a,'Normal')],knockout=True)
        zeroed=group(back,[(red,a,'Normal'),(green,D(0),'Normal')],knockout=True)
        assert covered==zeroed
        isolated=group(back,[(blue,a,'Normal')],isolated=True,knockout=True)
        # The group colour is unpremultiplied, so an isolated knockout keeps the source colour.
        assert isolated[1]==a and isolated[0]==blue
        print('knockout self-test: 5 invariants hold')


if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':self_test()
    else:verify(sys.argv[1])
