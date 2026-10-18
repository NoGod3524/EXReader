// SPDX-License-Identifier: GPL-3.0-only
package org.exreader;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

/** Owned JNI snapshots; native work on the same handle is serialized. */
public final class EXReader {
    private EXReader() {}
    static { System.loadLibrary("exreader_jni"); }
    public static String version() { return nativeVersion(); }
    public static final class MetadataEntry {
        public final String key,value;
        private MetadataEntry(byte[] key,byte[] value) {
            this.key=new String(key,StandardCharsets.UTF_8);
            this.value=new String(value,StandardCharsets.UTF_8);
        }
    }
    private static MetadataEntry[] metadataValues(byte[][] bytes) {
        MetadataEntry[] values=new MetadataEntry[bytes.length/2];
        for(int i=0;i<values.length;i++) values[i]=new MetadataEntry(bytes[i*2],bytes[i*2+1]);
        return values;
    }
    public static MetadataEntry[] readXMP(byte[] packet) {
        Objects.requireNonNull(packet);
        return metadataValues(nativeReadXMP(packet));
    }
    public static final class AudioChapter {
        public final String id,title;
        public final long parent,startMilliseconds,endMilliseconds; // -1: absent parent/unknown end.
        private AudioChapter(byte[] id,byte[] title,long parent,long start,long end) {
            this.id=utf8String(id); this.title=utf8String(title); this.parent=parent; startMilliseconds=start; endMilliseconds=end;
        }
    }
    public static final class AudioBookMetadata {
        public final MetadataEntry[] entries;
        public final AudioChapter[] chapters;
        public final long durationMilliseconds; // -1: unknown duration.
        public final byte[] cover; // null when absent, otherwise independently owned encoded bytes.
        public final String coverMediaType;
        private AudioBookMetadata(byte[][] entries,AudioChapter[] chapters,long duration,byte[] cover,byte[] mediaType) {
            this.entries=metadataValues(entries); this.chapters=chapters; durationMilliseconds=duration; this.cover=cover; coverMediaType=utf8String(mediaType);
        }
    }
    public static AudioBookMetadata readM4b(String path) { return nativeReadM4b(pathBytes(path)); }
    public static final class Bitmap {
        public final int width, height, stride, channels;
        public final byte[] pixels;
        private Bitmap(int width, int height, int stride, int channels, byte[] pixels) {
            this.width=width; this.height=height; this.stride=stride; this.channels=channels; this.pixels=pixels;
        }
    }
    public static final class TextPage {
        public final byte[] utf8;
        public final long[] ranges; // start,end per region, in UTF-8 bytes.
        public final double[] quads; // 8 source-coordinate components per region.
        public final int[] flags;
        private TextPage(byte[] utf8, long[] ranges, double[] quads, int[] flags) {
            this.utf8=utf8; this.ranges=ranges; this.quads=quads; this.flags=flags;
        }
        public String text() { return new String(utf8, StandardCharsets.UTF_8); }
    }
    public enum FixedFormat {
        PDF(8), CBZ(9);
        final int code; FixedFormat(int code) { this.code=code; }
    }
    public static final int PASSWORD_REQUIRED = 10;
    public static final class PdfSecurity {
        public final boolean encrypted,ownerAuthenticated,metadataEncrypted;
        public final int revision,keyBits;
        public final long permissions; // unsigned 32-bit /P; inspect together with revision/owner role.
        private PdfSecurity(long[] values) {
            encrypted=values[0]!=0; revision=(int)values[1]; keyBits=(int)values[2];
            ownerAuthenticated=values[3]!=0; permissions=values[4]; metadataEncrypted=values[5]!=0;
        }
    }
    public static class FixedDocument implements AutoCloseable {
        private long handle;
        public final PdfSecurity pdfSecurity; // null for CBZ.
        public FixedDocument(FixedFormat format,byte[] bytes) { this(format,bytes,null,0); }
        public FixedDocument(FixedFormat format,byte[] bytes, byte[] fallbackFont, int faceIndex) {
            this(format,bytes,fallbackFont,faceIndex,null);
        }
        /** Password bytes: PDFDocEncoding for R2-4; UTF-8 for R5-6. Borrowed only during construction. */
        public FixedDocument(FixedFormat format,byte[] bytes,byte[] fallbackFont,int faceIndex,byte[] password) {
            Objects.requireNonNull(format);
            Objects.requireNonNull(bytes);
            if(faceIndex<0) throw new IllegalArgumentException("Negative face index");
            long[] security=new long[6];
            handle=nativePdfOpen(bytes, fallbackFont, faceIndex, format.code,password,security);
            pdfSecurity=format==FixedFormat.PDF ? new PdfSecurity(security) : null;
        }
        private long checked() { if(handle==0) throw new IllegalStateException("Fixed document is closed"); return handle; }
        public synchronized int pageCount() { return nativePdfCount(checked()); }
        public synchronized MetadataEntry[] metadata() { return metadataValues(nativePdfMetadata(checked())); }
        public synchronized TextPage text(int page) {
            if(page<0) throw new IllegalArgumentException("Negative page");
            return nativePdfText(checked(),page);
        }
        public synchronized Bitmap render(int page, double scale) {
            if(page<0) throw new IllegalArgumentException("Negative page");
            return nativePdfRender(checked(),page,scale);
        }
        @Override public synchronized void close() {
            if(handle!=0) { nativePdfClose(handle); handle=0; }
        }
    }
    public static final class Pdf extends FixedDocument {
        public Pdf(byte[] bytes) { super(FixedFormat.PDF,bytes); }
        public Pdf(byte[] bytes,byte[] fallbackFont,int faceIndex) { super(FixedFormat.PDF,bytes,fallbackFont,faceIndex); }
        public Pdf(byte[] bytes,byte[] password) { super(FixedFormat.PDF,bytes,null,0,password); }
        public Pdf(byte[] bytes,byte[] fallbackFont,int faceIndex,byte[] password) { super(FixedFormat.PDF,bytes,fallbackFont,faceIndex,password); }
    }
    public static final class WaveFormat {
        public final int sampleRate,channels,bitsPerSample,validBits,channelMask;
        public final long frames;
        public final boolean floating;
        private WaveFormat(int rate,int channels,int bits,int valid,int mask,long frames,boolean floating) {
            sampleRate=rate; this.channels=channels; bitsPerSample=bits; validBits=valid; channelMask=mask; this.frames=frames; this.floating=floating;
        }
    }
    public static final class Wave implements AutoCloseable {
        private long handle;
        public Wave(String filePath) {
            handle=nativeWaveOpen(pathBytes(filePath));
        }
        private long checked() { if(handle==0) throw new IllegalStateException("WAVE is closed"); return handle; }
        public synchronized WaveFormat format() { return nativeWaveFormat(checked()); }
        public synchronized float[] read(long firstFrame,int count) {
            if(firstFrame<0 || count<0 || count>65536) throw new IllegalArgumentException("Invalid frame range");
            return nativeWaveRead(checked(),firstFrame,count);
        }
        @Override public synchronized void close() {
            if(handle!=0) { nativeWaveClose(handle); handle=0; }
        }
    }
    private static byte[] pathBytes(String filePath) {
        Objects.requireNonNull(filePath);
        if(filePath.indexOf(0)>=0) throw new IllegalArgumentException("NUL in path");
        for(int i=0;i<filePath.length();i++) {
            char c=filePath.charAt(i);
            if(Character.isHighSurrogate(c)) {
                if(i+1>=filePath.length() || !Character.isLowSurrogate(filePath.charAt(++i))) throw new IllegalArgumentException("Invalid UTF-16 path");
            } else if(Character.isLowSurrogate(c)) throw new IllegalArgumentException("Invalid UTF-16 path");
        }
        return filePath.getBytes(StandardCharsets.UTF_8);
    }
    public static final class PcmFormat {
        public final int sampleRate,channels,channelMask;
        public final long frames; // -1 when duration is not yet known.
        private PcmFormat(int rate,int channels,int mask,long frames) {
            sampleRate=rate; this.channels=channels; channelMask=mask; this.frames=frames;
        }
    }
    public static final class Pcm implements AutoCloseable {
        private long handle;
        public Pcm(String filePath) { handle=nativePcmOpen(pathBytes(filePath)); }
        private long checked() { if(handle==0) throw new IllegalStateException("PCM is closed"); return handle; }
        public synchronized PcmFormat format() { return nativePcmFormat(checked()); }
        public synchronized float[] read(long firstFrame,int count) {
            if(firstFrame<0 || count<0 || count>65536) throw new IllegalArgumentException("Invalid frame range");
            return nativePcmRead(checked(),firstFrame,count);
        }
        @Override public synchronized void close() {
            if(handle!=0) { nativePcmClose(handle); handle=0; }
        }
    }
    public enum Format {
        TXT(1),HTML(2),FB2(3),EPUB(4),DOCX(5),RTF(6),MOBI(7);
        final int code; Format(int code) { this.code=code; }
    }
    public static final class LayoutConfig {
        public float width=720,height=1040,margin=48,fontSize=24,lineHeight=1.6f,paragraphSpacing=12;
        public String userCSS;
        public boolean documentCSS=true,embeddedFonts=true;
        public int direction=0; // 0 auto, 1 LTR, 2 RTL.
        private float[] page() { return new float[]{width,height,margin,fontSize,lineHeight,paragraphSpacing}; }
    }
    /** All ranges are UTF-8 byte offsets in Document.utf8(), absent indices are -1. */
    public static final class Node {
        public final int kind;
        public final long parent,firstChild,nextSibling,chapter,start,end;
        public final String name,text;
        public final MetadataEntry[] attributes;
        private Node(int kind,long[] indices,byte[][] values) {
            this.kind=kind; parent=indices[0]; firstChild=indices[1]; nextSibling=indices[2]; chapter=indices[3]; start=indices[4]; end=indices[5];
            name=utf8String(values[0]); text=utf8String(values[1]);
            attributes=new MetadataEntry[(values.length-2)/2];
            for(int i=0;i<attributes.length;i++) attributes[i]=new MetadataEntry(values[2+i*2],values[3+i*2]);
        }
    }
    private static String utf8String(byte[] bytes) { return bytes==null ? null : new String(bytes,StandardCharsets.UTF_8); }
    public static final class Part {
        public final String id,path,title;
        public final boolean inReadingOrder;
        private Part(byte[] id,byte[] path,byte[] title,boolean reading) {
            this.id=utf8String(id); this.path=utf8String(path); this.title=utf8String(title); inReadingOrder=reading;
        }
    }
    public static final class Publication implements AutoCloseable {
        private final Object gate=new Object();
        private long handle;
        public Publication(String path) { handle=nativePublicationOpen(pathBytes(path),false); }
        public Publication(byte[] epub) { handle=nativePublicationOpen(Objects.requireNonNull(epub),true); }
        private long checked() { if(handle==0) throw new IllegalStateException("Publication is closed"); return handle; }
        public String title() { synchronized(gate) { return utf8String(nativePublicationTitle(checked())); } }
        public Part[] parts() { synchronized(gate) { return nativePublicationParts(checked()); } }
        public Document load(int part) {
            if(part<0) throw new IllegalArgumentException("Negative part");
            synchronized(gate) {
                Document result=new Document(gate);
                result.handle=nativePublicationLoad(checked(),part); return result;
            }
        }
        @Override public void close() { synchronized(gate) { if(handle!=0) { nativePublicationClose(handle); handle=0; } } }
    }
    public static final class Document implements AutoCloseable {
        private final Object gate;
        private long handle;
        private Document(Object gate) { this.gate=gate; }
        public Document(String path) { gate=new Object(); handle=nativeDocumentOpen(pathBytes(path),0); }
        public Document(byte[] bytes,Format format) {
            gate=new Object(); handle=nativeDocumentOpen(Objects.requireNonNull(bytes),Objects.requireNonNull(format).code);
        }
        private long checked() { if(handle==0) throw new IllegalStateException("Document is closed"); return handle; }
        public String title() { synchronized(gate) { return utf8String(nativeDocumentTitle(checked())); } }
        public byte[] utf8() { synchronized(gate) { return nativeDocumentText(checked()); } }
        public Node[] nodes() { synchronized(gate) { return nativeDocumentNodes(checked()); } }
        public Pager pager(byte[] font,int faceIndex,LayoutConfig config) {
            Objects.requireNonNull(font); Objects.requireNonNull(config);
            if(faceIndex<0) throw new IllegalArgumentException("Negative face index");
            byte[] css=config.userCSS==null ? null : pathBytes(config.userCSS);
            synchronized(gate) {
                Pager result=new Pager(gate);
                result.handle=nativePagerCreate(checked(),font,faceIndex,config.page(),css,config.documentCSS,config.embeddedFonts,config.direction);
                return result;
            }
        }
        @Override public void close() { synchronized(gate) { if(handle!=0) { nativeDocumentClose(handle); handle=0; } } }
    }
    public static final class Pager implements AutoCloseable {
        private final Object gate;
        private long handle;
        private Pager(Object gate) { this.gate=gate; }
        /** null at EOF; an engine error invalidates the pager. */
        public ReflowPage next() {
            synchronized(gate) {
                if(handle==0) throw new IllegalStateException("Pager is closed");
                ReflowPage page=new ReflowPage(gate);
                try { page.handle=nativePagerNext(handle); }
                catch(EXReaderException e) { close(); throw e; }
                return page.handle==0 ? null : page;
            }
        }
        @Override public void close() { synchronized(gate) { if(handle!=0) { nativePagerClose(handle); handle=0; } } }
    }
    public static final class Glyph {
        public final long start,end,node,clusterStart,clusterEnd,fontIndex;
        public final int codepoint,glyph,color,flags,boundaries,bidiLevel;
        public final float x,baseline,advance,size,clipLeft,clipRight,lineHeight,offsetX,offsetY;
        private Glyph(long[] d,float[] p,int i) {
            int a=i*12,b=i*9;
            start=d[a]; end=d[a+1]; codepoint=(int)d[a+2]; glyph=(int)d[a+3]; node=d[a+4]; color=(int)d[a+5]; flags=(int)d[a+6];
            clusterStart=d[a+7]; clusterEnd=d[a+8]; boundaries=(int)d[a+9]; fontIndex=d[a+10]; bidiLevel=(int)d[a+11];
            x=p[b]; baseline=p[b+1]; advance=p[b+2]; size=p[b+3]; clipLeft=p[b+4]; clipRight=p[b+5]; lineHeight=p[b+6]; offsetX=p[b+7]; offsetY=p[b+8];
        }
    }
    public static final class Line {
        public final long start,end,glyphStart,glyphCount;
        public final float x,y,width,height;
        private Line(long[] d,float[] p,int i) {
            int a=i*4; start=d[a]; end=d[a+1]; glyphStart=d[a+2]; glyphCount=d[a+3];
            x=p[a]; y=p[a+1]; width=p[a+2]; height=p[a+3];
        }
    }
    public static final class Box {
        public final int kind,background,borderColor,flags;
        public final long node,resource,start,end;
        public final float x,y,width,height,borderWidth;
        private Box(long[] d,float[] p,int i) {
            int a=i*8,b=i*5;
            kind=(int)d[a]; node=d[a+1]; resource=d[a+2]; start=d[a+3]; end=d[a+4]; background=(int)d[a+5]; borderColor=(int)d[a+6]; flags=(int)d[a+7];
            x=p[b]; y=p[b+1]; width=p[b+2]; height=p[b+3]; borderWidth=p[b+4];
        }
    }
    public static final class LayoutSnapshot {
        public final long start,end;
        public final int writingMode; // 0 horizontal-tb, 1 vertical-rl, 2 vertical-lr.
        public final Glyph[] glyphs;
        public final Line[] lines;
        public final Box[] boxes;
        private LayoutSnapshot(long start,long end,int mode,long[] gd,float[] gp,long[] ld,float[] lp,long[] bd,float[] bp) {
            this.start=start; this.end=end; writingMode=mode;
            glyphs=new Glyph[gd.length/12]; for(int i=0;i<glyphs.length;i++) glyphs[i]=new Glyph(gd,gp,i);
            lines=new Line[ld.length/4]; for(int i=0;i<lines.length;i++) lines[i]=new Line(ld,lp,i);
            boxes=new Box[bd.length/8]; for(int i=0;i<boxes.length;i++) boxes[i]=new Box(bd,bp,i);
        }
    }
    public static final class FontAxis {
        public final int tag,flags;
        public final double minimum,initial,maximum,value;
        private FontAxis(double[] a,int i) { i*=6; tag=(int)(long)a[i]; flags=(int)a[i+1]; minimum=a[i+2]; initial=a[i+3]; maximum=a[i+4]; value=a[i+5]; }
    }
    public static final class FontSource {
        public final byte[] data;
        public final int faceIndex;
        public final FontAxis[] axes;
        private FontSource(byte[] data,int face,double[] axes) {
            this.data=data; faceIndex=face; this.axes=new FontAxis[axes.length/6];
            for(int i=0;i<this.axes.length;i++) this.axes[i]=new FontAxis(axes,i);
        }
    }
    /** Owned native page; close after use. Snapshots/bitmaps survive close(). */
    public static final class ReflowPage implements AutoCloseable {
        private final Object gate;
        private long handle;
        private ReflowPage(Object gate) { this.gate=gate; }
        private long checked() { if(handle==0) throw new IllegalStateException("Page is closed"); return handle; }
        public LayoutSnapshot snapshot() { synchronized(gate) { return nativePageSnapshot(checked()); } }
        public FontSource fontSource(int index) {
            if(index<0) throw new IllegalArgumentException("Negative font index");
            synchronized(gate) { return nativePageFont(checked(),index); }
        }
        public Bitmap image(int resource) {
            if(resource<0) throw new IllegalArgumentException("Negative resource index");
            synchronized(gate) { return nativePageImage(checked(),resource); }
        }
        public long hitTest(float x,float y) { synchronized(gate) { return nativePageHit(checked(),x,y); } }
        public Bitmap render() { synchronized(gate) { return nativePageRender(checked()); } }
        @Override public void close() { synchronized(gate) { if(handle!=0) { nativePageClose(handle); handle=0; } } }
    }
    private static native long nativePublicationOpen(byte[] bytes,boolean memory);
    private static native byte[] nativePublicationTitle(long handle);
    private static native Part[] nativePublicationParts(long handle);
    private static native long nativePublicationLoad(long handle,int part);
    private static native void nativePublicationClose(long handle);
    private static native long nativeDocumentOpen(byte[] bytes,int format);
    private static native byte[] nativeDocumentTitle(long handle);
    private static native byte[] nativeDocumentText(long handle);
    private static native Node[] nativeDocumentNodes(long handle);
    private static native void nativeDocumentClose(long handle);
    private static native long nativePagerCreate(long handle,byte[] font,int face,float[] page,byte[] css,boolean documentCSS,boolean embeddedFonts,int direction);
    private static native long nativePagerNext(long handle);
    private static native void nativePagerClose(long handle);
    private static native LayoutSnapshot nativePageSnapshot(long handle);
    private static native FontSource nativePageFont(long handle,int index);
    private static native Bitmap nativePageImage(long handle,int resource);
    private static native long nativePageHit(long handle,float x,float y);
    private static native Bitmap nativePageRender(long handle);
    private static native void nativePageClose(long handle);
    private static native String nativeVersion();
    private static native AudioBookMetadata nativeReadM4b(byte[] path);
    private static native byte[][] nativeReadXMP(byte[] packet);
    private static native byte[][] nativePdfMetadata(long handle);
    private static native long nativePdfOpen(byte[] bytes,byte[] font,int faceIndex,int format,byte[] password,long[] security);
    private static native int nativePdfCount(long handle);
    private static native TextPage nativePdfText(long handle,int page);
    private static native Bitmap nativePdfRender(long handle,int page,double scale);
    private static native void nativePdfClose(long handle);
    private static native long nativeWaveOpen(byte[] path);
    private static native WaveFormat nativeWaveFormat(long handle);
    private static native float[] nativeWaveRead(long handle,long firstFrame,int count);
    private static native void nativeWaveClose(long handle);
    private static native long nativePcmOpen(byte[] path);
    private static native PcmFormat nativePcmFormat(long handle);
    private static native float[] nativePcmRead(long handle,long firstFrame,int count);
    private static native void nativePcmClose(long handle);
}
