// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;
import android.util.Log;

import org.exreader.EXReader;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

/**
 * Reflow reader state. Owned by the host worker thread: the document, pager and
 * font are opened and released on that thread only. Pages are rendered to an
 * owned bitmap and the native page handle is closed before returning.
 */
final class ReflowSession implements AutoCloseable {
    static final float PAGE_WIDTH = 600f;
    static final float PAGE_HEIGHT = 860f;
    static final float MARGIN = 32f;

    private final EXReader.Document document;
    private final byte[] text;
    private final byte[] font;
    private EXReader.Pager pager;
    private float fontSize;
    private int index = -1;
    private boolean atEnd;
    private boolean closed;
    private final String title;
    private final long bookId;
    private long nativeNextCalls;
    private long recoveryCalls;
    private BoundedEpub bounded;
    private ReadingPreferences appearance;
    private PageTheme theme=PageTheme.ORIGINAL;
    private ThemeReflow themed;
    private long themedPager;

    ReflowSession(BookStore store,long bookId,byte[] font,ReadingPreferences value,PageTheme theme){
        this(store,bookId,font,value);this.theme=theme;bounded.theme=theme;
    }
    ReflowSession(long bookId,String path,byte[] font,ReadingPreferences value,PageTheme theme){
        this.bookId=bookId;this.font=font;this.fontSize=value.font;this.appearance=value;this.theme=theme;
        if(theme.enabled){
            document=null;themed=new ThemeReflow(path,font);
            try{text=themed.text();title=themed.title();}catch(RuntimeException|Error error){themed.close();throw error;}
        }else{
            document=new EXReader.Document(path);
            try{text=document.utf8();title=document.title();}catch(RuntimeException|Error error){document.close();throw error;}
        }
    }

    ReflowSession(BookStore store,long bookId,byte[] font,ReadingPreferences value) {
        this(store,bookId,font,value.font);appearance=value;bounded.appearance=value;
    }
    ReflowSession(long bookId,String path,byte[] font,ReadingPreferences value) {
        this(bookId,path,font,value.font);appearance=value;
    }

    ReflowSession(BookStore store,long bookId,byte[] font,float size) {
        this.bookId=bookId; this.font=font; fontSize=size; document=null; text=null; title="EPUB";
        bounded=new BoundedEpub(store.nativeLibrary(),bookId,font,size);
    }
    boolean bounded() { return bounded!=null; }
    PageLoad restore(int displayIndex,HostTask task) throws Exception { return bounded.restore(displayIndex,task); }
    PageLoad seek(NativeLibrary.Note note,HostTask task) throws Exception {
        return bounded!=null?bounded.seek(note,task):seek(note.start,task);
    }
    PageLoad seekSearch(NativeSearch.Hit hit,NativeSearch.Match match,HostTask task)throws Exception {
        return bounded!=null?bounded.seekSearch(hit,task):seek(match.start,task);
    }
    PageLoad seekNavigation(NativeNavigation.Destination destination,HostTask task)throws Exception {
        return bounded!=null?bounded.seekNavigation(destination,task):seek(destination.result.offset,task);
    }
    PageLoad seekReading(NativeReadingSdk.Match match,HostTask task)throws Exception {
        if(!match.found())throw new IllegalArgumentException("Reading location is not FOUND");
        if(bounded==null&&match.recaptured.mode!=ReadingCapture.REFLOW)throw new NativeReadingSdk.Projection();
        return bounded!=null?bounded.seekReading(match,task):seek(match.recaptured.start,task);
    }
    void saveProgress(PageSnapshot page) { bounded.saveProgress(page); }
    void saveBoundedNote(long id,long start,long end,String text) { bounded.saveNote(id,start,end,text); }
    void refreshSource() { if(bounded!=null) bounded.refresh(); }
    void reviewChapterBudget(long bytes) { if(bounded!=null) bounded.chapterBudget=bytes; }

    ReflowSession(long bookId, String path, byte[] font, float size) {
        this.bookId = bookId;
        this.font = font;
        this.fontSize = size;
        document = new EXReader.Document(path);
        try {
            text = document.utf8();
            title = document.title();
        } catch (RuntimeException | Error error) { document.close(); throw error; }
    }

    String title() {
        return title;
    }

    byte[] text() {
        return text;
    }

    int index() {
        return index;
    }

    float fontSize() {
        return fontSize;
    }

    private EXReader.LayoutConfig config(float size) {
        EXReader.LayoutConfig config = new EXReader.LayoutConfig();
        config.width = PAGE_WIDTH;
        config.height = PAGE_HEIGHT;
        config.margin = appearance==null?MARGIN:appearance.margin;
        config.fontSize = size;
        config.lineHeight = appearance==null?1.6f:appearance.line;
        config.paragraphSpacing = appearance==null?12f:appearance.paragraph;
        config.documentCSS = true;
        config.embeddedFonts = true;
        config.direction = 0;
        return config;
    }

    PageLoad next(HostTask task) throws Exception {
        if(bounded!=null) return bounded.next(task);
        if(themed!=null)return themeNext(task);
        if (pager == null) return prepare(index + 1, -1, fontSize, task);
        task.check();
        long started = System.nanoTime();
        try (EXReader.ReflowPage page = nextPage(pager, false)) {
            if (page == null) return null;
            EXReader.LayoutSnapshot layout = page.snapshot();
            task.check();
            EXReader.Bitmap rendered = page.render();
            task.check();
            if (rendered == null) throw new IllegalStateException("No page bitmap");
            PageSnapshot snapshot = build(layout, toBitmap(rendered), index + 1, fontSize);
            return new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L,
                    () -> { index = snapshot.index; lastStart = snapshot.start; logSteps(); },
                    this::recoverAcceptedCursor);
        } catch (Exception | Error error) { recoverAcceptedCursor(); throw error; }
    }

    private EXReader.ReflowPage nextPage(EXReader.Pager source, boolean recovery) {
        nativeNextCalls++;
        if (recovery) recoveryCalls++;
        return source.next();
    }

    private void logSteps() {
        Log.i("EXRHost", "paging {\"book\":" + bookId + ",\"index\":" + index +
                ",\"native_next_calls\":" + nativeNextCalls + ",\"recovery_calls\":" + recoveryCalls + "}");
    }

    private void recoverAcceptedCursor() {
        if(themed!=null){recoverTheme();return;}
        if (pager != null) pager.close();
        pager = null;
        if (closed) return;
        EXReader.Pager restored = null;
        try {
            restored = document.pager(font, 0, config(fontSize));
            if (index >= 20000) throw new IllegalStateException("Recovery exceeds the host page budget");
            for (int at = 0; at <= index; at++) {
                try (EXReader.ReflowPage page = nextPage(restored, true)) {
                    if (page == null) throw new IllegalStateException("Accepted page no longer exists");
                }
            }
            pager = restored;
            restored = null;
        } catch (RuntimeException error) {
            Log.w("EXRHost", "Cursor recovery failed; next request must rebuild: " + error.getMessage());
        } finally { if (restored != null) restored.close(); }
    }
    PageLoad previous(HostTask task) throws Exception {
        if(bounded!=null) return bounded.previous(task);
        return index <= 0 ? null : prepare(index - 1, -1, fontSize, task);
    }
    PageLoad seek(long offset, HostTask task) throws Exception {
        if (offset < 0 || offset > text.length) throw new IllegalArgumentException("Text position is outside the document");
        return prepare(-1, offset, fontSize, task);
    }
    PageLoad setFontSize(float size, HostTask task) throws Exception {
        return bounded!=null?bounded.font(size,task):prepare(-1,lastStart,size,task);
    }

    private long lastStart = 0;

    private PageLoad prepare(int target, long offset, float size, HostTask task) throws Exception {
        if (closed) throw new IllegalStateException("Reader is closed");
        if(themed!=null)return themePrepare(target,offset,size,task);
        task.check();
        long started = System.nanoTime();
        final EXReader.Pager candidate = document.pager(font, 0, config(size));
        boolean transferred = false;
        try {
            // The installed Java binding exposes sequential pagers. Replay an
            // independent candidate so a render/database failure cannot advance
            // the accepted cursor. Preceding pages are not rasterized.
            for (int at = 0; at < 20000; at++) {
                task.check();
                try (EXReader.ReflowPage page = nextPage(candidate, false)) {
                    if (page == null) {
                        if (target >= 0) return null;
                        throw new IllegalArgumentException("No page contains the requested text position");
                    }
                    EXReader.LayoutSnapshot layout = page.snapshot();
                    boolean contains = offset >= layout.start && (offset < layout.end ||
                            (offset == text.length && layout.end == offset));
                    if (target >= 0 ? at != target : !contains) continue;
                    task.check();
                    EXReader.Bitmap rendered = page.render();
                    task.check();
                    if (rendered == null) throw new IllegalStateException("No page bitmap");
                    Bitmap bitmap = toBitmap(rendered);
                    final int acceptedIndex = at;
                    PageSnapshot snapshot = build(layout, bitmap, at, size);
                    PageLoad result = new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L,
                            () -> {
                                if (pager != null) pager.close();
                                pager = candidate;
                                index = acceptedIndex;
                                fontSize = size;
                                lastStart = snapshot.start;
                                logSteps();
                            }, candidate::close);
                    transferred = true;
                    return result;
                }
            }
            throw new IllegalStateException("Seek exceeds the 20000-page host budget");
        } finally { if (!transferred) candidate.close(); }
    }

    private PageSnapshot build(EXReader.LayoutSnapshot layout, Bitmap bitmap, int pageIndex, float layoutFont) {
        try { return buildSnapshot(layout, bitmap, pageIndex, layoutFont); }
        catch (RuntimeException | Error error) { bitmap.recycle(); throw error; }
    }

    private PageSnapshot themeSnapshot(BoundedEpub.Frame frame,int at,float size){
        int width=(int)frame.meta[2],height=(int)frame.meta[3],gc=(int)frame.meta[5],lc=(int)frame.meta[6];
        Bitmap bitmap=themeBitmap(width,height,frame.pixels);
        try{
            if(frame.meta[4]!=(long)width*4)throw new IllegalStateException("Unexpected theme bitmap stride");
            long[] starts=new long[gc],ends=new long[gc];float[] x=new float[gc],baseline=new float[gc],advance=new float[gc],sizes=new float[gc];
            for(int i=0;i<gc;i++){starts[i]=frame.spans[i*2];ends[i]=frame.spans[i*2+1];x[i]=frame.geometry[i*4];baseline[i]=frame.geometry[i*4+1];advance[i]=frame.geometry[i*4+2];sizes[i]=frame.geometry[i*4+3];}
            String[] lines=new String[lc];RectF[] bounds=new RectF[lc];
            for(int i=0;i<lc;i++){int n=gc+i;lines[i]=slice(text,frame.spans[n*2],frame.spans[n*2+1]).trim();bounds[i]=new RectF(frame.geometry[n*4],frame.geometry[n*4+1],frame.geometry[n*4]+frame.geometry[n*4+2],frame.geometry[n*4+1]+frame.geometry[n*4+3]);}
            PageSnapshot result=new PageSnapshot(bitmap,false,at,-1,frame.meta[0],frame.meta[1],text,1f,width,height,starts,ends,null,x,baseline,advance,sizes,lines,bounds,0,bookId);
            byte[] expected=java.util.Arrays.copyOfRange(text,(int)frame.meta[0],(int)frame.meta[1]);
            if(!java.util.Arrays.equals(expected,frame.text))throw new IllegalStateException("Rendered document text projection mismatch");
            if(!"3.41.0".equals(frame.sdk))throw new IllegalStateException("Page theme requires SDK3.41");
            result.pageTheme=theme;result.themeSdk=frame.sdk;result.themeBoxes=frame.boxes;result.layoutFont=size;result.layoutLine=appearance.line;result.layoutParagraph=appearance.paragraph;result.layoutMargin=appearance.margin;return result;
        }catch(RuntimeException|Error error){bitmap.recycle();throw error;}
    }
    static Bitmap themeBitmap(int width,int height,byte[] rgba){
        if(width<=0||height<=0||(long)width*height*4!=rgba.length)throw new IllegalArgumentException("Invalid native RGBA frame");
        int[] pixels=new int[width*height];for(int i=0;i<pixels.length;i++){int at=i*4;pixels[i]=(rgba[at+3]&255)<<24|(rgba[at]&255)<<16|(rgba[at+1]&255)<<8|(rgba[at+2]&255);}
        // setPixels converts SDK straight RGBA to Android's premultiplied storage.
        // Canvas cannot draw an explicitly unpremultiplied Bitmap.
        Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);bitmap.setPixels(pixels,0,width,0,0,width,height);return bitmap;
    }
    private PageLoad themeNext(HostTask task)throws Exception{
        if(themedPager==0)return themePrepare(index+1,-1,fontSize,task);
        long began=System.nanoTime();
        try{
            task.check();nativeNextCalls++;BoundedEpub.Frame frame=ThemeReflow.next(themedPager,task,true);if(frame==null)return null;
            task.check();PageSnapshot page=themeSnapshot(frame,index+1,fontSize);
            return new PageLoad(page,(System.nanoTime()-began)/1000000L,()->{index=page.index;lastStart=page.start;logSteps();},this::recoverTheme);
        }catch(Exception|Error error){recoverTheme();throw error;}
    }
    private PageLoad themePrepare(int target,long offset,float size,HostTask task)throws Exception{
        task.check();long began=System.nanoTime(),candidate=themed.pager(size,appearance,theme,task);boolean transferred=false;
        try{
            for(int at=0;at<20000;at++){
                task.check();nativeNextCalls++;BoundedEpub.Frame frame=ThemeReflow.next(candidate,task,false);
                if(frame==null){if(target>=0)return null;throw new IllegalArgumentException("No page contains requested text position");}
                boolean contains=offset>=frame.meta[0]&&(offset<frame.meta[1]||offset==text.length&&frame.meta[1]==offset);
                if(target>=0?at!=target:!contains)continue;
                frame=ThemeReflow.render(candidate,task);task.check();PageSnapshot page=themeSnapshot(frame,at,size);final int accepted=at;
                PageLoad load=new PageLoad(page,(System.nanoTime()-began)/1000000L,()->{if(themedPager!=0)ThemeReflow.close(themedPager);themedPager=candidate;index=accepted;fontSize=size;lastStart=page.start;logSteps();},()->ThemeReflow.close(candidate));
                transferred=true;return load;
            }
            throw new IllegalStateException("Seek exceeds the 20000-page host budget");
        }finally{if(!transferred)ThemeReflow.close(candidate);}
    }
    private void recoverTheme(){
        if(themedPager!=0)ThemeReflow.close(themedPager);themedPager=0;if(closed)return;
        long candidate=0;try{
            HostTask task=new HostTask(()->false);candidate=themed.pager(fontSize,appearance,theme,task);
            if(index>=20000)throw new IllegalStateException("Recovery exceeds host budget");
            for(int at=0;at<=index;at++){nativeNextCalls++;recoveryCalls++;if(ThemeReflow.next(candidate,task,false)==null)throw new IllegalStateException("Accepted page missing");}
            themedPager=candidate;candidate=0;
        }catch(RuntimeException error){Log.w("EXRHost","Theme cursor recovery failed: "+error.getMessage());}
        finally{if(candidate!=0)ThemeReflow.close(candidate);}
    }

    private PageSnapshot buildSnapshot(EXReader.LayoutSnapshot layout, Bitmap bitmap, int pageIndex, float layoutFont) {
        int glyphCount = layout.glyphs.length;
        long[] starts = new long[glyphCount];
        long[] ends = new long[glyphCount];
        float[] gx = new float[glyphCount];
        float[] baseline = new float[glyphCount];
        float[] advance = new float[glyphCount];
        float[] size = new float[glyphCount];
        for (int i = 0; i < glyphCount; i++) {
            EXReader.Glyph glyph = layout.glyphs[i];
            starts[i] = glyph.start;
            ends[i] = glyph.end;
            gx[i] = glyph.x;
            baseline[i] = glyph.baseline;
            advance[i] = glyph.advance;
            size[i] = glyph.size;
        }
        int lineCount = layout.lines.length;
        String[] lineText = new String[lineCount];
        RectF[] lineBounds = new RectF[lineCount];
        for (int i = 0; i < lineCount; i++) {
            EXReader.Line line = layout.lines[i];
            lineText[i] = slice(text, line.start, line.end).trim();
            lineBounds[i] = new RectF(line.x, line.y, line.x + line.width, line.y + line.height);
        }
        long start = layout.start == -1 ? 0 : layout.start;
        long end = layout.end == -1 ? text.length : layout.end;
        PageSnapshot snapshot = new PageSnapshot(bitmap, false, pageIndex, -1, start, end, text, 1f,
                bitmap.getWidth(), bitmap.getHeight(), starts, ends, null,
                gx, baseline, advance, size, lineText, lineBounds, 0, bookId);
        snapshot.layoutFont=layoutFont;
        if(appearance!=null){snapshot.layoutLine=appearance.line;snapshot.layoutParagraph=appearance.paragraph;snapshot.layoutMargin=appearance.margin;}
        return snapshot;
    }

    static Bitmap toBitmap(EXReader.Bitmap source) {
        Bitmap bitmap = Bitmap.createBitmap(source.width, source.height, Bitmap.Config.ARGB_8888);
        int row = source.width * 4;
        if (source.stride != row) {
            byte[] packed = new byte[row * source.height];
            for (int y = 0; y < source.height; y++) {
                System.arraycopy(source.pixels, y * source.stride, packed, y * row, row);
            }
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(packed));
        } else {
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(source.pixels));
        }
        return bitmap;
    }

    static String slice(byte[] bytes, long start, long end) {
        if (bytes == null || start < 0 || end < start || end > bytes.length) return "";
        return new String(bytes, (int) start, (int) (end - start), StandardCharsets.UTF_8);
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        if(bounded!=null) { bounded.close(); return; }
        if(themed!=null){if(themedPager!=0)ThemeReflow.close(themedPager);themedPager=0;themed.close();return;}
        if (pager != null) {
            pager.close();
            pager = null;
        }
        document.close();
    }
}
