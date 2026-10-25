// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;

import org.exreader.EXReader;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * Fixed-page reader state. The whole fixed document is opened from the app-owned
 * copy; each page render is independent and the bitmap outlives document close.
 */
final class FixedSession implements AutoCloseable {
    static { System.loadLibrary("exreader_host"); }
    private static native double[] nativeViewports(byte[] bytes);
    private final EXReader.FixedDocument document;
    private final NativeCbz cbz;
    private final int pageCount;
    private final float baseScale;
    private int index;
    private boolean closed;
    private final long bookId;
    private final boolean imageOnly;
    private final double[] viewports;

    FixedSession(long bookId, String path, byte[] font, int format,HostTask task) throws Exception {
        this.bookId = bookId;
        imageOnly = format == NativeLibrary.FORMAT_CBZ;
        byte[] bytes = read(path);
        if(imageOnly&&BuildConfig.READER_READING){
            cbz=new NativeCbz(bytes,task);document=null;
        } else if (format == NativeLibrary.FORMAT_CBZ) {
            cbz=null;
            document = new EXReader.FixedDocument(EXReader.FixedFormat.CBZ, bytes);
        } else {
            cbz=null;
            document = new EXReader.Pdf(bytes, font, 0);
        }
        try {
            pageCount = cbz==null?document.pageCount():cbz.count();
            if (pageCount <= 0) throw new IllegalStateException("The document has no pages");
            task.check();
            viewports = imageOnly ? null : nativeViewports(bytes);
            task.check();
            if(!imageOnly&&(viewports==null||viewports.length!=pageCount*6))throw new IllegalStateException("Incomplete public PDF page viewport directory");
            int width=cbz==null?document.render(0,1.0).width:cbz.render(0,1.0,task).meta[0];
            if(width<=0)throw new IllegalStateException("The first page cannot be rendered");
            baseScale = Math.max(0.25f, Math.min(20f, 600f / width));
        } catch (Exception | Error error) {if(cbz!=null)cbz.close();else document.close();throw error;}
    }
    boolean cbz(){return cbz!=null;}
    String sourceKey(){return cbz==null?null:cbz.sourceKey;}
    int rendererIdentity(){return cbz==null?0:cbz.identity();}
    NativeReadingSdk.Match resolveCurrent(ReadingCapture capture,HostTask task)throws Exception{if(cbz==null)throw new IllegalStateException("No current public CBZ renderer");return cbz.resolve(capture,task);}

    int pageCount() {
        return pageCount;
    }

    int index() {
        return index;
    }

    PageLoad load(int page, float zoom, HostTask task) throws Exception {
        if (closed) return null;
        task.check();
        if (page < 0) page = 0;
        if (page >= pageCount) page = pageCount - 1;
        final int candidateIndex = page;
        long started = System.nanoTime();
        float scale = baseScale * zoom;
        NativeCbz.Frame cbzFrame=cbz==null?null:cbz.render(page,scale,task);
        EXReader.Bitmap nativeBitmap = cbz==null?document.render(page,scale):null;
        task.check();
        if(nativeBitmap==null&&cbzFrame==null)throw new IllegalStateException("No page bitmap");
        Bitmap bitmap=cbzFrame==null?ReflowSession.toBitmap(nativeBitmap):cbzFrame.bitmap();
        boolean transferred = false;
        try {
        EXReader.TextPage textPage = null;
        if(cbzFrame==null&&!imageOnly)textPage=document.text(page);
        task.check();
        byte[] text=cbzFrame!=null?cbzFrame.text:textPage==null||textPage.utf8==null?new byte[0]:textPage.utf8;
        int regions=cbzFrame!=null?cbzFrame.meta[6]:textPage==null?0:textPage.flags.length;
        long[] starts = new long[regions];
        long[] ends = new long[regions];
        float[][] quads = new float[regions][8];
        for (int i = 0; i < regions; i++) {
            starts[i] = textPage.ranges[i * 2];
            ends[i] = textPage.ranges[i * 2 + 1];
            // Public PDF text is in native source coordinates. Match the same
            // crop/rotation/y-axis viewport used by exr_fixed_render at scale 1.
            int matrix = page * 6;
            for (int k = 0; k < 8; k += 2) {
                double x=textPage.quads[i*8+k],y=textPage.quads[i*8+k+1];
                quads[i][k]=(float)(viewports[matrix]*x+viewports[matrix+2]*y+viewports[matrix+4]);
                quads[i][k+1]=(float)(viewports[matrix+1]*x+viewports[matrix+3]*y+viewports[matrix+5]);
            }
        }
        String[] lineText;
        RectF[] lineBounds;
        LineSet lines = buildLines(text, starts, ends, quads, textPage == null ? null : textPage.flags);
        lineText = lines.text;
        lineBounds = lines.bounds;
        float contentWidth = bitmap.getWidth() / scale;
        float contentHeight = bitmap.getHeight() / scale;
        PageSnapshot snapshot = new PageSnapshot(bitmap, true, page, pageCount, 0, text.length,
                text, scale, contentWidth, contentHeight, starts, ends, quads,
                null, null, null, null, lineText, lineBounds, 0, bookId);
        snapshot.layoutZoom=zoom;
        snapshot.fixedTextProvided=cbzFrame!=null||textPage!=null;
        snapshot.fixedPageId=cbzFrame==null?null:cbzFrame.pageId;
        snapshot.fixedRendererSourceKey=cbz==null?null:cbz.sourceKey;
        snapshot.fixedRendererIdentity=cbz==null?0:cbz.identity();
        PageLoad result = new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L,
                () -> index = candidateIndex, () -> {});
        transferred = true;
        return result;
        } finally { if (!transferred) bitmap.recycle(); }
    }

    private static final class LineSet {
        final String[] text;
        final RectF[] bounds;

        LineSet(String[] text, RectF[] bounds) {
            this.text = text;
            this.bounds = bounds;
        }
    }

    private static LineSet buildLines(byte[] pageText, long[] starts, long[] ends,
                                      float[][] quads, int[] flags) {
        java.util.List<StringBuilder> texts = new java.util.ArrayList<>();
        java.util.List<RectF> boxes = new java.util.ArrayList<>();
        java.util.List<Float> centers = new java.util.ArrayList<>();
        java.util.List<Boolean> verticals = new java.util.ArrayList<>();
        for (int i = 0; i < quads.length; i++) {
            if (flags != null && (flags[i] & 2) != 0) continue;
            RectF box = box(quads[i]);
            if (box.width() <= 0 || box.height() <= 0) continue;
            String value = ReflowSession.slice(pageText, starts[i], ends[i]);
            if (value.isEmpty()) continue;
            float dx=quads[i][2]-quads[i][0],dy=quads[i][3]-quads[i][1];
            boolean vertical=Math.abs(dy)>Math.abs(dx);
            float normal=vertical?box.width():box.height(),center=vertical?box.centerX():box.centerY();
            int group = -1;
            for (int g = 0; g < centers.size(); g++) {
                float tolerance = Math.max(normal, vertical?boxes.get(g).width():boxes.get(g).height()) * 0.6f;
                if (verticals.get(g)==vertical && Math.abs(center - centers.get(g)) <= tolerance) {
                    group = g;
                    break;
                }
            }
            if (group < 0) {
                texts.add(new StringBuilder(value));
                boxes.add(new RectF(box));
                centers.add(center);
                verticals.add(vertical);
            } else {
                RectF current = boxes.get(group);
                StringBuilder builder = texts.get(group);
                float gap=vertical?(dy>=0?box.top-current.bottom:current.top-box.bottom):(dx>=0?box.left-current.right:current.left-box.right);
                if (gap > Math.max(2f, normal * 0.2f)) builder.append(' ');
                builder.append(value);
                current.union(box);
                centers.set(group, vertical?current.centerX():current.centerY());
            }
        }
        String[] text = new String[texts.size()];
        RectF[] bounds = new RectF[texts.size()];
        for (int i = 0; i < text.length; i++) {
            text[i] = texts.get(i).toString().trim();
            bounds[i] = boxes.get(i);
        }
        return new LineSet(text, bounds);
    }

    private static RectF box(float[] quad) {
        float left = Math.min(Math.min(quad[0], quad[2]), Math.min(quad[4], quad[6]));
        float top = Math.min(Math.min(quad[1], quad[3]), Math.min(quad[5], quad[7]));
        float right = Math.max(Math.max(quad[0], quad[2]), Math.max(quad[4], quad[6]));
        float bottom = Math.max(Math.max(quad[1], quad[3]), Math.max(quad[5], quad[7]));
        return new RectF(left, top, right, bottom);
    }

    private static byte[] read(String path) throws IOException {
        File file = new File(path);
        if (file.length() > 32L * 1024 * 1024) throw new IOException("File exceeds 32 MiB");
        ByteArrayOutputStream out = new ByteArrayOutputStream((int) Math.max(1024, file.length()));
        FileInputStream in = new FileInputStream(file);
        try {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = in.read(buffer)) > 0) {
                if (out.size() > 32L * 1024 * 1024 - count) throw new IOException("File exceeds 32 MiB");
                out.write(buffer, 0, count);
            }
        } finally {
            in.close();
        }
        return out.toByteArray();
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        if(cbz!=null)cbz.close();else document.close();
    }
}
