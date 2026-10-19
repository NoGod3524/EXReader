// SPDX-License-Identifier: MIT
package org.exreader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class Smoke {
    private static void check(boolean value) { if(!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        check(args.length==2);
        Path root=Paths.get(args[0]),temporary=Paths.get(args[1]);
        EXReader.AudioBookMetadata audiobook=EXReader.readM4b(root.resolve("audio/metadata.m4b").toString());
        check(audiobook.durationMilliseconds==200 && audiobook.chapters.length==2 && audiobook.chapters[0].parent==-1 && audiobook.chapters[0].startMilliseconds==0 && audiobook.chapters[1].startMilliseconds==100 && audiobook.chapters[1].endMilliseconds==200);
        check(audiobook.entries[0].value.equals("Book 中文😀") && audiobook.entries[1].value.equals("作者") && audiobook.cover.length>0 && audiobook.coverMediaType.equals("image/jpeg"));
        check(EXReader.version().startsWith("0."));
        byte[] pdf=Files.readAllBytes(root.resolve("fixed-pages/pdf-public.pdf"));
        byte[] encrypted=Files.readAllBytes(root.resolve("fixed-pages/encrypted-r6.pdf"));
        try { new EXReader.Pdf(encrypted).close(); throw new AssertionError(); }
        catch(EXReaderException e) { check(e.code==EXReader.PASSWORD_REQUIRED); }
        byte[] password="reader".getBytes(StandardCharsets.UTF_8);
        try(EXReader.Pdf protectedPdf=new EXReader.Pdf(encrypted,password)) {
            Arrays.fill(password,(byte)0);
            check(protectedPdf.pageCount()==2 && protectedPdf.pdfSecurity.encrypted && protectedPdf.pdfSecurity.revision==6 && protectedPdf.pdfSecurity.keyBits==256);
            check(!protectedPdf.pdfSecurity.ownerAuthenticated && protectedPdf.pdfSecurity.permissions==0xfffff0c4L);
            check(protectedPdf.text(0).text().equals("Secret text"));
            try { protectedPdf.text(1); throw new AssertionError(); } catch(EXReaderException e) { check(e.code==5); }
            check(protectedPdf.text(0).text().equals("Secret text"));
        }
        try(EXReader.FixedDocument comic=new EXReader.FixedDocument(EXReader.FixedFormat.CBZ,Files.readAllBytes(root.resolve("fixed-pages/comic.cbz")))) {
            check(comic.pageCount()==4 && comic.metadata()[0].value.equals("SDK Comic") && comic.text(0).utf8.length==0);
            EXReader.Bitmap page=comic.render(0,1);
            check(page.width==2 && page.height==2 && page.channels==4 && page.pixels.length==16);
        }
        EXReader.Bitmap bitmap;
        EXReader.TextPage text;
        try(EXReader.Pdf document=new EXReader.Pdf(pdf)) {
            check(document.pageCount()==5 && document.metadata().length==0);
            text=document.text(0); check(text.text().equals("A") && text.ranges.length==2 && text.ranges[0]==0 && text.ranges[1]==1 && text.quads.length==8);
            bitmap=document.render(0,1); check(bitmap.width==12 && bitmap.height==12 && bitmap.stride==48 && bitmap.channels==4 && bitmap.pixels.length==576);
            try { document.render(3,1); throw new AssertionError(); } catch(EXReaderException e) { check(e.code==5 && !e.getMessage().isEmpty()); }
            document.close(); document.close();
            try { document.pageCount(); throw new AssertionError(); } catch(IllegalStateException expected) { }
            try { document.metadata(); throw new AssertionError(); } catch(IllegalStateException expected) { }
        }
        check(bitmap.pixels[3]==(byte)255 && text.utf8[0]==65); // Snapshots outlive native handles.
        try(EXReader.Pdf semantic=new EXReader.Pdf(Files.readAllBytes(root.resolve("fixed-pages/pdf-public-text.pdf")))) {
            EXReader.TextPage page=semantic.text(0);
            check(page.utf8.length==14 && page.text().indexOf(0)>=0 && page.text().contains("一") && page.text().contains("😀") && page.flags.length==8);
            check(page.ranges[2]==1 && page.ranges[3]==3 && page.ranges[6]==6 && page.ranges[7]==7);
        }
        String head="<r:RDF xmlns:r='http://www.w3.org/1999/02/22-rdf-syntax-ns#'><r:Description xmlns:dc='http://purl.org/dc/elements/1.1/'>";
        String tail="</r:Description></r:RDF>";
        byte[] packet=(head+"<dc:title>中文😀</dc:title><dc:creator><r:Seq><r:li>Alice</r:li><r:li>Bob</r:li></r:Seq></dc:creator>"+tail).getBytes(StandardCharsets.UTF_8);
        EXReader.MetadataEntry[] metadata=EXReader.readXMP(packet); Arrays.fill(packet,(byte)0);
        check(metadata.length==3 && metadata[0].key.equals("http://purl.org/dc/terms/title") && metadata[0].value.equals("中文😀") && metadata[1].value.equals("Alice") && metadata[2].value.equals("Bob"));
        StringBuilder many=new StringBuilder(head); for(int i=0;i<4096;i++) many.append("<dc:subject>词😀</dc:subject>"); many.append(tail);
        check(EXReader.readXMP(many.toString().getBytes(StandardCharsets.UTF_8)).length==4096);
        try { EXReader.readXMP("<bad/>".getBytes(StandardCharsets.UTF_8)); throw new AssertionError(); } catch(EXReaderException e) { check(e.code==5); }
        try { EXReader.readXMP(new byte[0]); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        byte[] font=Files.readAllBytes(root.resolve("fonts/collection.ttc"));
        try(EXReader.Pdf fallback=new EXReader.Pdf(pdf,font,1)) {
            Arrays.fill(font,(byte)0); Arrays.fill(pdf,(byte)0);
            check(fallback.render(1,1).height==16);
        }
        Files.createDirectories(temporary);
        Path chinese=temporary.resolve("声音😀.wav"); Files.copy(root.resolve("audio/pcm.wav"),chinese,java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        try(EXReader.Wave wave=new EXReader.Wave(chinese.toString())) {
            EXReader.WaveFormat format=wave.format(); check(format.sampleRate==16000 && format.channels==1 && format.frames==3200 && format.bitsPerSample==16);
            float[] samples=wave.read(0,1024); float peak=0; for(float value:samples) peak=Math.max(peak,Math.abs(value)); check(samples.length==1024 && peak==.5f);
            check(wave.read(3199,1024).length==1 && wave.read(3200,1).length==0);
            try { wave.read(0,65537); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
            wave.close(); wave.close();
            try { wave.format(); throw new AssertionError(); } catch(IllegalStateException expected) { }
        }
        try(EXReader.Pcm pcm=new EXReader.Pcm(chinese.toString())) {
            EXReader.PcmFormat format=pcm.format(); check(format.sampleRate==16000 && format.channels==1 && format.frames==3200);
            float[] samples=pcm.read(0,1024); float peak=0; for(float v:samples) peak=Math.max(peak,Math.abs(v)); check(samples.length==1024 && peak==.5f);
            check(pcm.read(3199,1024).length==1 && pcm.read(3200,1).length==0 && pcm.read(0,0).length==0);
            try { pcm.read(0,65537); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
            pcm.close(); pcm.close();
            try { pcm.format(); throw new AssertionError(); } catch(IllegalStateException expected) { }
        }
        Files.delete(chinese);
        try { new EXReader.Wave("bad\0name"); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { new EXReader.Wave("bad\ud800name"); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { new EXReader.Pcm("bad\0name"); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        try { new EXReader.Pcm("bad\ud800name"); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        EXReader.LayoutConfig config=new EXReader.LayoutConfig();
        config.width=220; config.height=180; config.margin=10; config.fontSize=14; config.paragraphSpacing=4;
        config.userCSS="p {background-color:#ff0000}";
        String html="<html><head><title>书😀</title></head><body><p id='hello' style='background-color:#ff0000'>A 中文😀</p>";
        StringBuilder book=new StringBuilder(html); for(int i=0;i<100;i++) book.append("<p>A paragraph with several words.</p>"); book.append("</body></html>");
        byte[] input=book.toString().getBytes(StandardCharsets.UTF_8);
        EXReader.Document reflow=new EXReader.Document(input,EXReader.Format.HTML); Arrays.fill(input,(byte)0);
        check(reflow.title()!=null);
        EXReader.Node[] nodes=reflow.nodes();
        check(nodes.length>0 && nodes[0].parent==-1 && new String(reflow.utf8(),StandardCharsets.UTF_8).contains("中文😀"));
        byte[] reflowFont=Files.readAllBytes(root.resolve("fonts/primary.ttf"));
        EXReader.Pager pager=reflow.pager(reflowFont,0,config); Arrays.fill(reflowFont,(byte)0);
        reflow.close(); reflow.close();
        try { reflow.utf8(); throw new AssertionError(); } catch(IllegalStateException expected) { }
        EXReader.ReflowPage first=pager.next(),second=pager.next(); check(first!=null && second!=null);
        EXReader.LayoutSnapshot snapshot=first.snapshot();
        EXReader.FontSource sourceFont=first.fontSource(0);
        check(sourceFont.faceIndex==0 && sourceFont.data.length>0 && sourceFont.axes.length==0 && first.image(99999)==null);
        check(snapshot.start<snapshot.end && snapshot.glyphs.length>0 && snapshot.lines.length>0 && snapshot.boxes.length>0);
        check(second.snapshot().start==snapshot.end);
        EXReader.Glyph glyph=snapshot.glyphs[0]; check(first.hitTest(glyph.x,glyph.baseline)>=snapshot.start);
        int pageCount=2; EXReader.ReflowPage more;
        while((more=pager.next())!=null) { pageCount++; more.close(); }
        check(pageCount>2 && pager.next()==null); pager.close(); pager.close();
        EXReader.Bitmap pageBitmap=first.render(); check(pageBitmap.width==220 && pageBitmap.height==180 && pageBitmap.channels==4);
        first.close(); second.close(); first.close();
        check(snapshot.glyphs.length>0 && pageBitmap.pixels.length==220*180*4 && nodes.length>0);
        try { first.render(); throw new AssertionError(); } catch(IllegalStateException expected) { }
        EXReader.Publication publication=new EXReader.Publication(root.resolve("books/layout.epub").toString());
        EXReader.Part[] parts=publication.parts(); check(parts.length>0 && parts[0].path!=null);
        EXReader.Document chapter=publication.load(0); publication.close();
        check(chapter.utf8().length>0 && chapter.nodes().length>0);
        boolean chapterAttribute=false;
        for(EXReader.Node node:chapter.nodes()) for(EXReader.MetadataEntry attr:node.attributes) if(attr.key.equals("id") && attr.value.equals("intro")) chapterAttribute=true;
        check(chapterAttribute);
        EXReader.Pager chapterPager=chapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,config); chapter.close();
        EXReader.ReflowPage chapterPage=chapterPager.next();
        EXReader.Bitmap savedImage=null;
        for(int i=0;i<30 && savedImage==null;i++) {
            try(EXReader.ReflowPage candidate=chapterPager.next()) {
                if(candidate==null) break;
                for(EXReader.Box box:candidate.snapshot().boxes) if(box.kind==2 && box.resource>=0) {
                    savedImage=candidate.image((int)box.resource); if(savedImage!=null) break;
                }
            }
        }
        check(savedImage!=null && savedImage.pixels.length>0); chapterPager.close();
        check(chapterPage!=null && chapterPage.render().width==220); chapterPage.close();
        try { new EXReader.Document(new byte[0],EXReader.Format.TXT); throw new AssertionError(); } catch(EXReaderException expected) { check(expected.code==1); }
        try(EXReader.Document invalid=new EXReader.Document("hello".getBytes(StandardCharsets.UTF_8),EXReader.Format.TXT)) {
            config.width=Float.NaN;
            try { invalid.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,config); throw new AssertionError(); } catch(EXReaderException expected) { check(expected.code==1); }
            config.width=220; config.userCSS="a\0b";
            try { invalid.pager(new byte[1],0,config); throw new AssertionError(); } catch(IllegalArgumentException expected) { }
        }
        config.userCSS=null;
        try(EXReader.Document variableDoc=new EXReader.Document("A".getBytes(StandardCharsets.UTF_8),EXReader.Format.TXT);
            EXReader.Pager variablePager=variableDoc.pager(Files.readAllBytes(root.resolve("fonts/variable.ttf")),0,config);
            EXReader.ReflowPage variablePage=variablePager.next()) {
            EXReader.FontSource source=variablePage.fontSource(0);
            check(source.axes.length==2 && source.axes[0].minimum<source.axes[0].maximum);
        }
        EXReader.LayoutConfig floatConfig=new EXReader.LayoutConfig();
        floatConfig.width=240; floatConfig.height=240; floatConfig.margin=20; floatConfig.fontSize=14;
        floatConfig.lineHeight=20f/14; floatConfig.paragraphSpacing=0;
        try(EXReader.Publication floats=new EXReader.Publication(root.resolve("books/float-both.epub").toString());
            EXReader.Document floatingChapter=floats.load(0);
            EXReader.Pager floatingPager=floatingChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,floatConfig);
            EXReader.ReflowPage floatingPage=floatingPager.next()) {
            check(floatingPage!=null);
            EXReader.LayoutSnapshot floatingSnapshot=floatingPage.snapshot();
            check(floatingSnapshot.glyphs.length>0 && Math.abs(floatingSnapshot.glyphs[0].clipLeft-80)<.01f && Math.abs(floatingSnapshot.glyphs[0].clipRight-160)<.01f);
            int images=0; for(EXReader.Box box:floatingSnapshot.boxes) if(box.kind==2) {
                images++; EXReader.Bitmap image=floatingPage.image((int)box.resource); check(image!=null && image.width==80 && image.height==60);
            }
            check(images==2); EXReader.Bitmap rendered=floatingPage.render(); int pixel=30*rendered.stride+30*4;
            check(rendered.pixels[pixel]==0 && rendered.pixels[pixel+1]==(byte)128 && rendered.pixels[pixel+2]==(byte)255);
        }
        try(EXReader.Publication floats=new EXReader.Publication(root.resolve("books/float-long-main.epub").toString());
            EXReader.Document floatingChapter=floats.load(0);
            EXReader.Pager floatingPager=floatingChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,floatConfig)) {
            int pages=0,letters=0; EXReader.ReflowPage page;
            while((page=floatingPager.next())!=null) {
                try(EXReader.ReflowPage owned=page) {
                    for(EXReader.Glyph g:owned.snapshot().glyphs) if(g.codepoint==65) letters++;
                    EXReader.Bitmap pixels=owned.render(); check(pixels.width==240 && pixels.height==240); pages++;
                }
            }
            check(pages>20 && letters==7500);
        }
        try(EXReader.Publication bookWithTable=new EXReader.Publication(root.resolve("books/float-bfc-stream.epub").toString());
            EXReader.Document tableChapter=bookWithTable.load(0);
            EXReader.Pager tablePager=tableChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,floatConfig)) {
            EXReader.Node[] tableNodes=tableChapter.nodes(); long table=-1;
            for(int i=0;i<tableNodes.length;i++) for(EXReader.MetadataEntry attr:tableNodes[i].attributes) if(attr.key.equals("id") && attr.value.equals("ordinary")) table=i;
            check(table>=0); int pages=0,letters=0,fragments=0; EXReader.ReflowPage page;
            while((page=tablePager.next())!=null) {
                try(EXReader.ReflowPage owned=page) {
                    EXReader.LayoutSnapshot view=owned.snapshot();
                    for(EXReader.Glyph g:view.glyphs) if(g.codepoint==65) letters++;
                    for(EXReader.Box b:view.boxes) if(b.node==table && (b.flags&2)==0) {
                        check(Math.abs(b.x-100)<.01f && Math.abs(b.width-100)<.01f); fragments++;
                    }
                    check(owned.render().width==240); pages++;
                }
            }
            check(pages>20 && fragments>20 && letters==3350);
        }
        EXReader.LayoutConfig hyphenConfig=new EXReader.LayoutConfig();
        hyphenConfig.width=55; hyphenConfig.height=100; hyphenConfig.margin=10; hyphenConfig.fontSize=14;
        hyphenConfig.userCSS="html,body,p {margin:0;padding:0;font-size:14px;line-height:20px}";
        byte[] patterns="aa1aaaa aaaa1aa".getBytes(StandardCharsets.UTF_8);
        EXReader.HyphenDictionary[] dictionaries={new EXReader.HyphenDictionary("en",patterns,1,1),
            new EXReader.HyphenDictionary("fr","é1té".getBytes(StandardCharsets.UTF_8),1,1)};
        Arrays.fill(patterns,(byte)0); // Dictionary input was copied by its value object.
        try(EXReader.Publication hyphenBook=new EXReader.Publication(root.resolve("books/hyphen-long.epub").toString());
            EXReader.Document hyphenChapter=hyphenBook.load(0);
            EXReader.Pager hyphenPager=hyphenChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,hyphenConfig)) {
            hyphenPager.setHyphenation(dictionaries,0);
            try { hyphenPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("en","\\patterns{a1b}".getBytes(StandardCharsets.UTF_8),1,1)},0); throw new AssertionError(); }
            catch(EXReaderException expected) { check(expected.code==11); }
            try(EXReader.ReflowPage page=hyphenPager.next()) {
                check(page!=null); int inserted=0;
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0) { check(g.start==g.end); inserted++; }
                check(inserted>0 && page.render().width==55);
            }
            try { hyphenPager.setHyphenation(new EXReader.HyphenDictionary[0],0); throw new AssertionError(); }
            catch(EXReaderException expected) { check(expected.code==1); }
        }
        try(EXReader.Publication canonicalBook=new EXReader.Publication(root.resolve("books/hyphen-canonical.epub").toString());
            EXReader.Document canonicalChapter=canonicalBook.load(0);
            EXReader.Pager canonicalPager=canonicalChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,hyphenConfig)) {
            canonicalPager.setHyphenation(dictionaries,0);
            try(EXReader.ReflowPage page=canonicalPager.next()) {
                check(page!=null); int inserted=0;
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0) {
                    check(g.start==g.end && g.start%8==3); inserted++;
                }
                check(inserted>0 && page.render().width==55);
            }
        }
        EXReader.LayoutConfig compoundConfig=new EXReader.LayoutConfig();
        compoundConfig.width=80; compoundConfig.height=100; compoundConfig.margin=10; compoundConfig.fontSize=14;
        compoundConfig.userCSS="html,body,p {margin:0;padding:0;font-size:14px;line-height:20px}";
        try(EXReader.Publication compoundBook=new EXReader.Publication(root.resolve("books/hyphen-compound.epub").toString());
            EXReader.Document compoundChapter=compoundBook.load(0);
            EXReader.Pager compoundPager=compoundChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            compoundPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("xx",
                "aaaa1aaaa\n.aa1aa.\nNEXTLEVEL\n.a1a.".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=compoundPager.next()) {
                check(page!=null);boolean compoundFirstBreak=false;
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0) {
                    check(g.start==g.end && g.start%9>=1 && g.start%9<=7);compoundFirstBreak|=g.start==5;
                }
                check(compoundFirstBreak && page.render().width==80);
            }
        }
        try(EXReader.Publication rewriteBook=new EXReader.Publication(root.resolve("books/hyphen-rewrite-long.epub").toString());
            EXReader.Document rewriteChapter=rewriteBook.load(0);
            EXReader.Pager rewritePager=rewriteChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            rewritePager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zz",
                ".aaaa1aaaa./aa=aaa,4,2".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=rewritePager.next()) {
                check(page!=null);boolean leftRewrite=false,rightRewrite=false;
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0) {
                    leftRewrite|=g.start==3 && g.end==4 && g.codepoint=='a';
                    rightRewrite|=g.start==4 && g.end==5 && g.codepoint=='a';
                }
                check(leftRewrite && rightRewrite && page.render().width==80);
            }
        }
        try(EXReader.Publication rematchBook=new EXReader.Publication(root.resolve("books/hyphen-rematch-long.epub").toString());
            EXReader.Document rematchChapter=rematchBook.load(0);
            EXReader.Pager rematchPager=rematchChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            rematchPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zm",
                ".abcd1efghijklmnopqr./d=xy,4,2 .xyfg1hijklmnopqr. .xyfghijk1lmnopqr./k=zz,8,2 .zzm1nopqr.".getBytes(StandardCharsets.UTF_8),1,1)},0);
            boolean rewrittenAgain=false,rematchedAgain=false;
            for(int i=0;i<2;i++) try(EXReader.ReflowPage page=rematchPager.next()) {
                check(page!=null);
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0) {
                    rewrittenAgain|=g.start==11 && g.end==12 && g.codepoint=='z';
                    rematchedAgain|=g.start==13 && g.end==13 && (g.codepoint=='-' || g.codepoint==0x2010);
                }
                check(page.render().width==80);
            }
            check(rewrittenAgain && rematchedAgain);
        }
        try(EXReader.Publication boundaryBook=new EXReader.Publication(root.resolve("books/hyphen-boundary-ri.epub").toString());
            EXReader.Document boundaryChapter=boundaryBook.load(0);
            EXReader.Pager boundaryPager=boundaryChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            boundaryPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zv",
                ".aaaa1a./=🇺,1,5".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=boundaryPager.next()) {
                check(page!=null);boolean joined=false,separated=false;
                for(EXReader.Glyph g:page.snapshot().glyphs) {
                    check((g.flags&~2559)==0);
                    if(g.codepoint==0x1f1f8 && g.start==5) { check(g.clusterStart==4 && g.clusterEnd==9 && g.boundaries==0);joined=true; }
                    if(g.codepoint==0x1f1e8 && g.start==9) { check(g.clusterStart==9 && g.clusterEnd==13 && (g.boundaries&1)!=0);separated=true; }
                }
                check(joined && separated && page.render().width==80);
            }
        }
        try(EXReader.Publication bidiBook=new EXReader.Publication(root.resolve("books/hyphen-bidi-long.epub").toString());
            EXReader.Document bidiChapter=bidiBook.load(0);
            EXReader.Pager bidiPager=bidiChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            bidiPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zb",
                ".aaaa1aaaaaaaa./ا1中=12ا,4,2".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=bidiPager.next()) {
                check(page!=null);int beforeCount=0;int[] visual={49,0x627,0x4e2d},levels={2,1,0};
                for(EXReader.Glyph g:page.snapshot().glyphs) {
                    check((g.flags&~2559)==0 && g.start>=0);
                    if((g.flags&2048)!=0 && g.start==3 && g.end==4) {
                        check(beforeCount<3 && g.codepoint==visual[beforeCount] && g.bidiLevel==levels[beforeCount]);beforeCount++;
                        check(page.hitTest(g.x+.1f,g.baseline-2)==((g.bidiLevel&1)!=0 ? 4 : 3));
                    }
                }
                check(beforeCount==3 && page.render().width==80);
            }
        }
        try(EXReader.Publication leadingBook=new EXReader.Publication(root.resolve("books/hyphen-bidi-leading.epub").toString());
            EXReader.Document leadingChapter=leadingBook.load(0);
            EXReader.Pager leadingPager=leadingChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            leadingPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("ze",
                ".aaaa1aaaaaaaa./=אב1,1,5".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=leadingPager.next()) {
                check(page!=null);var glyphs=page.snapshot().glyphs;check(glyphs.length>0);
                for(EXReader.Glyph g:glyphs) {
                    check(g.codepoint==49 && g.bidiLevel==2 && (g.flags&~2559)==0);
                    check(page.hitTest(g.x+.1f,g.baseline-2)==g.clusterStart);
                }
                check(page.render().width==80);
            }
        }
        try(EXReader.Publication futureBook=new EXReader.Publication(root.resolve("books/hyphen-bidi-future-neutral.epub").toString());
            EXReader.Document futureChapter=futureBook.load(0);
            EXReader.Pager futurePager=futureChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            futurePager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zf",
                ".aaaa1aaaaaaaa./א1中=12א,1,5".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=futurePager.next()) {
                check(page!=null);int pluses=0;
                for(EXReader.Glyph g:page.snapshot().glyphs) {
                    check((g.flags&~2559)==0 && (g.flags&2048)==0);
                    if(g.codepoint==43) { check(g.bidiLevel==1);pluses++;check(page.hitTest(g.x+.1f,g.baseline-2)==g.clusterEnd); }
                }
                check(pluses>0 && page.render().width==80);
            }
        }
        try(EXReader.Publication insertedBook=new EXReader.Publication(root.resolve("books/hyphen-insertion-long.epub").toString());
            EXReader.Document insertedChapter=insertedBook.load(0);
            EXReader.Pager insertedPager=insertedChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            insertedPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zi",
                ".aaaa1aaaa./=abcdefghijklmnop,5,0 .abcd1efghijklmnopaaaa./d=xy,4,2 .xyfg1hijklmnopaaaa./g=zz,4,2 .zzij1klmnopaaaa.".getBytes(StandardCharsets.UTF_8),1,1)},0);
            for(int index=0;index<2;index++) try(EXReader.ReflowPage page=insertedPager.next()) {
                check(page!=null);int inserted=0;
                for(EXReader.Glyph g:page.snapshot().glyphs) {
                    check((g.flags&~2559)==0 && (g.boundaries&~15)==0);
                    if((g.flags&2048)!=0 && g.start==4 && g.codepoint>='a' && g.codepoint<='z') {
                        check(g.end==4 && g.clusterStart==4 && g.clusterEnd==5);inserted++;
                        long hit=page.hitTest(g.x+.1f,g.baseline-2);check(hit==4 || hit==5);
                    }
                }
                check(inserted>0 && page.render().width==80);
            }
        }
        try(EXReader.Publication caseBook=new EXReader.Publication(root.resolve("books/hyphen-case-insertion.epub").toString());
            EXReader.Document caseChapter=caseBook.load(0);
            EXReader.Pager casePager=caseChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            casePager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("de",
                ".bbbb1bbbb./=abcdefghijklmnop,5,0 .abcd1efghijklmnopbbbb./d=ß,4,2 .ssfg1hijklmnopbbbb./g=ß,4,2 .ssij1klmnopbbbb.".getBytes(StandardCharsets.UTF_8),1,1)},0,EXReader.HyphenCasePolicy.WORD);
            for(int index=0;index<2;index++) try(EXReader.ReflowPage page=casePager.next()) {
                check(page!=null);int letters=0;
                for(EXReader.Glyph g:page.snapshot().glyphs) {
                    check((g.flags&~2559)==0 && (g.boundaries&~15)==0);
                    if((g.flags&2048)!=0 && g.codepoint!='-' && g.codepoint!=0x2010) {
                        check(g.codepoint>='A' && g.codepoint<='Z');letters++;
                        check(g.start==4 && g.end==4 && g.clusterStart==4 && g.clusterEnd==5);
                        long hit=page.hitTest(g.x+.1f,g.baseline-2);check(hit==4 || hit==5);
                    }
                }
                check(letters>0 && page.render().width==80);
            }
        }
        try(EXReader.Publication stemBook=new EXReader.Publication(root.resolve("books/hyphen-stem-long.epub").toString());
            EXReader.Document stemChapter=stemBook.load(0);
            EXReader.Pager stemPager=stemChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,compoundConfig)) {
            stemPager.setHyphenation(new EXReader.HyphenDictionary[]{new EXReader.HyphenDictionary("zk",
                ".abcdefg1hijk./gg=h,7,2\n.abcd1efgg.\nNEXTLEVEL\n.ab1cd.\n.hi1jk.".getBytes(StandardCharsets.UTF_8),1,1)},0);
            try(EXReader.ReflowPage page=stemPager.next()) {
                check(page!=null);boolean restoredStemBreak=false;
                for(EXReader.Glyph g:page.snapshot().glyphs) if((g.flags&2048)!=0 && g.start==4 && g.end==4) restoredStemBreak=true;
                check(restoredStemBreak && page.render().width==80);
            }
        }
        EXReader.LayoutConfig rowConfig=new EXReader.LayoutConfig();
        rowConfig.width=180;rowConfig.height=100;rowConfig.margin=10;rowConfig.fontSize=14;
        rowConfig.userCSS="html,body,p,table,tr,td {margin:0;padding:0;font-size:14px;line-height:20px}";
        try(EXReader.Publication rowBook=new EXReader.Publication(root.resolve("books/table-fragments-12.epub").toString());
            EXReader.Document rowChapter=rowBook.load(0);
            EXReader.Pager rowPager=rowChapter.pager(Files.readAllBytes(root.resolve("fonts/primary.ttf")),0,rowConfig)) {
            for(int index=0;index<3;index++) try(EXReader.ReflowPage page=rowPager.next()) {
                check(page!=null);EXReader.Glyph[] glyphs=page.snapshot().glyphs;check(glyphs.length>0);
                for(EXReader.Glyph g:glyphs) check(g.start<=g.end && (g.flags&~2559)==0 && (g.boundaries&~15)==0);
                check(page.render().width==180);
            }
        }
        System.out.println("JNI SDK: PDF/audio/metadata, floats, table BFCs, dictionary hyphenation and reflow lifetime passed");
    }
}
