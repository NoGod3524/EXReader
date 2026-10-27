// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.net.Uri;
import java.io.File;
import java.util.List;
import java.util.function.Consumer;

/** Everything the five reviewed modules need from the Activity; all work runs on its one SDK/product worker. */
interface Wave3Host {
    final class Export {
        final NativeWave3.ExportResult stats;final File jsonl,markdown;
        Export(NativeWave3.ExportResult stats,File jsonl,File markdown){this.stats=stats;this.jsonl=jsonl;this.markdown=markdown;}
    }
    final class Fonts {
        final List<NativeFonts.Font> fonts;final String selected;
        Fonts(List<NativeFonts.Font> fonts,String selected){this.fonts=fonts;this.selected=selected;}
    }
    void stage(Uri uri,String kind,long limit,HostTask task,Consumer<Wave3Files.Staged> done,Consumer<Throwable> failed);
    void saveTo(File source,Uri destination,HostTask task,Consumer<Long> done,Consumer<Throwable> failed);
    void pick(int request);
    void create(int request,String name,String mime);
    void annotationExport(long book,HostTask task,Consumer<Export> done,Consumer<Throwable> failed);
    void annotationImport(long book,File staged,boolean commit,String fingerprint,HostTask task,Consumer<NativeWave3.ImportResult> done,Consumer<Throwable> failed);
    void fontList(HostTask task,Consumer<Fonts> done,Consumer<Throwable> failed);
    void fontImport(File staged,String name,HostTask task,Consumer<NativeFonts.Imported> done,Consumer<Throwable> failed);
    void fontSelect(String hash,HostTask task,Runnable done,Consumer<Throwable> failed);
    void fontRemove(String hash,HostTask task,Consumer<Integer> done,Consumer<Throwable> failed);
    void originalExport(long book,HostTask task,Consumer<NativeOriginalExport.Result> done,Consumer<Throwable> failed);
    void jumpState(HostTask task,Consumer<NativeWave3.State> done,Consumer<Throwable> failed);
    void jumpMove(long book,int direction,HostTask task,Consumer<NativeWave3.Move> done,Consumer<Throwable> failed);
    void navigateJump(long book,NativeWave3.Move move);
    void dropJump(NativeWave3.Move move);
    void discard(File staged);
}
