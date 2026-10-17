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
    public static final class Pdf implements AutoCloseable {
        private long handle;
        public Pdf(byte[] bytes) { this(bytes, null, 0); }
        public Pdf(byte[] bytes, byte[] fallbackFont, int faceIndex) {
            Objects.requireNonNull(bytes);
            if(faceIndex<0) throw new IllegalArgumentException("Negative face index");
            handle=nativePdfOpen(bytes, fallbackFont, faceIndex);
        }
        private long checked() { if(handle==0) throw new IllegalStateException("PDF is closed"); return handle; }
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
            Objects.requireNonNull(filePath);
            if(filePath.indexOf(0)>=0) throw new IllegalArgumentException("NUL in path");
            for(int i=0;i<filePath.length();i++) {
                char c=filePath.charAt(i);
                if(Character.isHighSurrogate(c)) {
                    if(i+1>=filePath.length() || !Character.isLowSurrogate(filePath.charAt(++i))) throw new IllegalArgumentException("Invalid UTF-16 path");
                } else if(Character.isLowSurrogate(c)) throw new IllegalArgumentException("Invalid UTF-16 path");
            }
            handle=nativeWaveOpen(filePath.getBytes(StandardCharsets.UTF_8));
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
    private static native String nativeVersion();
    private static native byte[][] nativeReadXMP(byte[] packet);
    private static native byte[][] nativePdfMetadata(long handle);
    private static native long nativePdfOpen(byte[] bytes,byte[] font,int faceIndex);
    private static native int nativePdfCount(long handle);
    private static native TextPage nativePdfText(long handle,int page);
    private static native Bitmap nativePdfRender(long handle,int page,double scale);
    private static native void nativePdfClose(long handle);
    private static native long nativeWaveOpen(byte[] path);
    private static native WaveFormat nativeWaveFormat(long handle);
    private static native float[] nativeWaveRead(long handle,long firstFrame,int count);
    private static native void nativeWaveClose(long handle);
}
