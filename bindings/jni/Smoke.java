// SPDX-License-Identifier: GPL-3.0-only
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
        check(EXReader.version().startsWith("0."));
        byte[] pdf=Files.readAllBytes(root.resolve("fixed-pages/pdf-public.pdf"));
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
        System.out.println("JNI SDK: PDF text/render/font ownership, Unicode paths, owned multilingual metadata and WAVE samples passed");
    }
}
