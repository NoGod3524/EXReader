// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.net.Uri;
import android.os.Bundle;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import java.io.File;
import java.util.ArrayList;

/** Portable annotations: private export then SAF save; SAF pick, read-only preview, then explicit confirmed import. */
final class AnnotationPanel extends Wave3Dialog {
    static final int REQUEST_PICK=1102,REQUEST_JSONL=1104,REQUEST_MARKDOWN=1105;
    static final long LIMIT=16L*1024*1024+1;
    private static volatile File pendingJsonl,pendingMarkdown;
    private static final String STATE_JSONL="wave3.annotation.jsonl",STATE_MARKDOWN="wave3.annotation.markdown";
    private long book;private String title="";
    private Button exportButton,importButton,saveJson,saveMarkdown,cancel,confirm;private ListView list;private ArrayAdapter<String> adapter;
    private Wave3Files.Staged staged;private NativeWave3.ImportResult preview;private boolean busy;
    AnnotationPanel(android.app.Activity activity,Wave3Host host){super(activity,host);}
    void saveState(Bundle state){File jsonl=pendingJsonl,markdown=pendingMarkdown;if(jsonl!=null)state.putString(STATE_JSONL,jsonl.getPath());if(markdown!=null)state.putString(STATE_MARKDOWN,markdown.getPath());}
    void restoreState(Bundle state){pendingJsonl=Wave3Files.restoreExport(activity.getFilesDir(),"annotation-export",state.getString(STATE_JSONL));pendingMarkdown=Wave3Files.restoreExport(activity.getFilesDir(),"annotation-export",state.getString(STATE_MARKDOWN));}
    @Override void build() {
        LinearLayout first=row();exportButton=button(first,"导出标注",this::export);importButton=button(first,"导入标注文件…",this::pick);
        LinearLayout second=row();saveJson=button(second,"保存 JSONL…",()->save(pendingJsonl,REQUEST_JSONL,"application/json"));saveMarkdown=button(second,"保存 Markdown…",()->save(pendingMarkdown,REQUEST_MARKDOWN,"text/markdown"));
        list=new ListView(activity);list.setContentDescription("标注预览与结果");adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);
        content.addView(list,new LinearLayout.LayoutParams(-1,dp(200)));
        LinearLayout third=row();confirm=button(third,"确认导入",this::commit);cancel=button(third,"取消",this::cancelTask);
    }
    @Override void released(){File file=staged==null?null:staged.file;staged=null;preview=null;if(file!=null)host.discard(file);}
    private void controls(boolean value) {
        busy=value;if(exportButton==null)return;
        exportButton.setEnabled(!value);importButton.setEnabled(!value);saveJson.setEnabled(!value&&pendingJsonl!=null);saveMarkdown.setEnabled(!value&&pendingMarkdown!=null);
        cancel.setEnabled(value);confirm.setEnabled(!value&&preview!=null&&preview.ok()&&staged!=null);list.setEnabled(!value);
    }
    private void lines(java.util.List<String> values){adapter.clear();adapter.addAll(values);adapter.notifyDataSetChanged();}
    void show(long selected,String name) {
        book=selected;title=name==null?"":name;open("标注导入 / 导出","标注状态");controls(false);
        message("导出会生成 JSONL（完整、可再导入）和 Markdown；导入先预览，确认后才写入。");
    }
    private void export() {
        if(busy)return;pendingJsonl=null;pendingMarkdown=null;controls(true);message("正在形成标注文件…");
        long stamp=request();
        host.annotationExport(book,task,result->post(stamp,()->{
            NativeWave3.ExportResult stats=result.stats;
            if(stats.ok()){
                pendingJsonl=result.jsonl;pendingMarkdown=result.markdown;controls(false);
                message("已形成 "+stats.annotations+" 条标注（当前 "+stats.current+"，已删除 "+stats.tombstones+"，并发 "+stats.concurrent+"，待补父版本 "+stats.pending+"）："
                    +"JSONL "+stats.jsonlBytes+" 字节，Markdown "+stats.markdownBytes+" 字节。可保存到所选位置。");
            } else { controls(false);message("导出未完成（状态 "+stats.status+"）："+stats.message+"；没有改动现有记录"); }
        }),error->post(stamp,()->{controls(false);message(error instanceof HostTask.Cancelled?"已取消导出；现有记录未改变":"导出未完成："+reason(error));}));
    }
    private void save(File source,int request,String mime){
        if(busy||source==null||!source.isFile()){message("请先导出标注");return;}
        host.create(request,source.getName(),mime);
    }
    /** Back from the system document creator, possibly in a recreated Activity. */
    void saved(int request,Uri destination) {
        File source=request==REQUEST_JSONL?pendingJsonl:pendingMarkdown;
        if(source==null||!source.isFile()){open("标注导入 / 导出","标注状态");message("私有标注文件不可用，请重新导出后保存");return;}
        open("标注导入 / 导出","标注状态");controls(true);message("正在保存 "+source.getName());
        long stamp=request();
        host.saveTo(source,destination,task,bytes->post(stamp,()->{controls(false);message("已保存 "+bytes+" 字节；私有导出文件保留");}),
            error->post(stamp,()->{controls(false);message("保存未完成，私有导出文件保留："+reason(error));}));
    }
    private void pick(){if(!busy)host.pick(REQUEST_PICK);}
    /** The picker returned: copy once into private storage, validate completely, write nothing yet. */
    void picked(Uri uri,long selected,String name) {
        if(selected<=0){activity.runOnUiThread(()->android.widget.Toast.makeText(activity,"请先打开要导入标注的书籍",android.widget.Toast.LENGTH_LONG).show());return;}
        show(selected,name);staged=null;preview=null;controls(true);message("正在复制所选文件…");
        long stamp=request();
        host.stage(uri,"annotations",LIMIT,task,file->post(stamp,()->{
            staged=file;message("正在预览（不写入）…");
            host.annotationImport(book,file.file,false,null,task,result->post(stamp,()->preview(result)),error->post(stamp,()->failed(error)));
        },()->host.discard(file.file)),error->post(stamp,()->failed(error)));
    }
    private void failed(Throwable error){
        File file=staged==null?null:staged.file;staged=null;preview=null;if(file!=null)host.discard(file);
        controls(false);lines(new ArrayList<>());message(error instanceof HostTask.Cancelled?"已取消；没有写入任何记录":"导入未完成，没有写入任何记录："+reason(error));
    }
    private void preview(NativeWave3.ImportResult result) {
        preview=result;ArrayList<String> rows=new ArrayList<>();for(NativeWave3.ImportItem item:result.items)rows.add(item.label());if(result.totalItems>result.items.length)rows.add("… 另有 "+(result.totalItems-result.items.length)+" 条");lines(rows);
        if(!result.ok()){File file=staged==null?null:staged.file;staged=null;preview=result;if(file!=null)host.discard(file);controls(false);message("不能导入："+result.reason()+"。没有写入任何记录。");return;}
        confirm.setText("确认导入");controls(false);
        message("预览（尚未写入）："+(staged==null?"":staged.name+" · ")+result.inputBytes+" 字节 · 标注 "+result.annotations+" · 版本头 "+result.heads+" · 将新增 "+result.wouldCreate+" · 已存在 "+result.wouldDuplicate
            +" · 位置已确认 "+result.found+" · 空选择器保留（不可跳转）"+result.nulls+" · 历史缺口 "+result.omitted+"（文件只含最新版本）\n指纹 "+result.fingerprint.substring(0,16)+"…  确认后才会写入。");
    }
    private void commit() {
        if(busy||preview==null||!preview.ok()||staged==null)return;
        final NativeWave3.ImportResult confirmed=preview;final Wave3Files.Staged file=staged;
        controls(true);message("正在导入…");long stamp=request();
        host.annotationImport(book,file.file,true,confirmed.fingerprint,task,result->post(stamp,()->{
            ArrayList<String> rows=new ArrayList<>();for(NativeWave3.ImportItem item:result.items)rows.add(item.label());lines(rows);
            if(result.ok()){
                File done=staged==null?null:staged.file;staged=null;preview=null;if(done!=null)host.discard(done);
            } else confirm.setText("重试导入");
            controls(false);
            message(result.ok()?"导入完成：新增 "+result.created+" · 已存在 "+result.duplicates+" · 已提交 "+result.committed+"。历史缺口 "+result.omitted+"（只含最新版本）。"
                :"导入未完成："+result.reason()+"；已提交 "+result.committed+" 条保留，下一项 "+(result.nextIndex+1)+"。可重试；已有记录会重新核对。");
        }),error->post(stamp,()->{confirm.setText("重试导入");controls(false);message("导入中断："+reason(error)+"。已提交的记录保留；可重试核对结果。");}));
    }
}
