// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.net.Uri;
import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import java.io.File;
import java.util.Locale;

/**
 * Original export: first a complete private original per selected book with a per-item receipt,
 * only then an explicit SAF save. Sharing through another app would need a content provider,
 * which the host manifest does not declare, so SAF is the only outward route.
 */
final class OriginalExportPanel extends Wave3Dialog {
    static final int REQUEST=1103;
    /** The private original the user may still save. */
    private static volatile File pending;
    private static final String STATE="wave3.original.pending";
    private long book;private String title="";private Button save,cancel;private boolean busy;
    OriginalExportPanel(android.app.Activity activity,Wave3Host host){super(activity,host);}
    void saveState(Bundle state){File file=pending;if(file!=null)state.putString(STATE,file.getPath());}
    void restoreState(Bundle state){pending=Wave3Files.restoreExport(activity.getFilesDir(),"original-export",state.getString(STATE));}
    @Override void build() {
        LinearLayout actions=row();
        save=button(actions,"保存到…",this::saveClicked);cancel=button(actions,"取消导出",this::cancelTask);
    }
    private static String mime(String name) {
        String lower=name.toLowerCase(Locale.ROOT);
        if(lower.endsWith(".epub"))return "application/epub+zip";
        if(lower.endsWith(".pdf"))return "application/pdf";
        if(lower.endsWith(".txt"))return "text/plain";
        if(lower.endsWith(".cbz"))return "application/vnd.comicbook+zip";
        return "application/octet-stream";
    }
    private void controls(boolean value){busy=value;if(save==null)return;save.setEnabled(!value&&pending!=null);cancel.setEnabled(value);}
    void start(long selected,String name) {
        book=selected;title=name==null?"":name;pending=null;open("导出原件","原件导出状态");controls(true);message("正在形成「"+title+"」的完整私有原件…");
        long stamp=request();
        host.originalExport(book,task,result->post(stamp,()->{
            StringBuilder out=new StringBuilder();File first=null;
            for(NativeOriginalExport.Item item:result.items) {
                out.append(item.saved()?"✓ ":"✗ ").append(title).append(" · ").append(item.bytes).append(" 字节 · ").append(item.reason());
                if(item.saved()){out.append(" · SHA-256 ").append(item.sha.substring(0,12));if(first==null)first=new File(item.path);}
                if(item.cleanup)out.append(" · 有待清理的临时文件");
                out.append('\n');
            }
            pending=first;controls(false);
            message(out.length()==0?"没有导出结果":out.toString().trim()+(first==null?"":"\n私有原件已完整形成；可选择位置保存。"));
        }),error->post(stamp,()->{pending=null;controls(false);message(error instanceof HostTask.Cancelled?"已取消导出；已完整形成的私有文件保留":"导出未完成："+reason(error));}));
    }
    private void saveClicked() {
        File source=pending;if(busy||source==null||!source.isFile()){message("没有可保存的私有原件");return;}
        host.create(REQUEST,source.getName(),mime(source.getName()));
    }
    /** Back from the system document creator, possibly in a recreated Activity. */
    void saved(Uri destination) {
        File source=pending;
        if(source==null||!source.isFile()){open("导出原件","原件导出状态");message("私有原件不可用，请重新导出后保存");return;}
        open("导出原件","原件导出状态");message("正在保存「"+source.getName()+"」");
        long stamp=request();controls(true);
        host.saveTo(source,destination,task,bytes->post(stamp,()->{controls(false);message("已保存 "+bytes+" 字节；私有原件保留");}),
            error->post(stamp,()->{controls(false);message("保存未完成，私有原件保留："+reason(error));}));
    }
}
