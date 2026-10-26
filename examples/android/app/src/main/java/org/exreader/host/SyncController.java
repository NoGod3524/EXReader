// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import org.exreader.credentials.CredentialStore;

/** One process-owned controller; no Activity or SDK handle enters the session. */
final class SyncController {
    interface Host {
        void prepareOriginals(HostTask task,Runnable done,Consumer<Throwable> failed);
        void receive(NativeSync.RemoteBook book,File cached,HostTask task,Consumer<Long> done,Consumer<Throwable> failed);
        default void projectionChanged(){}
    }
    interface Listener {
        void update(String status,String root,List<NativeSync.RemoteBook> books,boolean busy);
        default void view(String[][] rows){}
        default void projected(){}
    }
    private static SyncController instance;
    static synchronized SyncController get(Context context){if(instance==null)instance=new SyncController(context.getApplicationContext());return instance;}
    private final ScheduledExecutorService worker=Executors.newSingleThreadScheduledExecutor(r->new Thread(r,"reader-sync-controls"));
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final AccountStore account;
    private final File product,cache,originals;
    private final List<NativeSync.RemoteBook> books=new ArrayList<>();
    private volatile Listener listener;
    private long session,epoch;
    private boolean preparing,receiving,pollQueued,projecting,projectionResumable;
    private final IntentJournal journal;
    private static final String[] PROJECT_KINDS={"book","shelf","tag","series","membership"};
    private int projectKind,projectPages,projectUnresolved,shelfUnresolved,shelfPass;
    private String projectCursor="";
    private HostTask sdkTask;
    private volatile String[][] view;
    private String status="就绪",accountNotice="";
    private int state=NativeSync.CLOSED;
    private SyncController(Context context){
        account=new AccountStore(context);journal=new IntentJournal(context.getSharedPreferences("organization",Context.MODE_PRIVATE));product=new File(context.getFilesDir(),"reader-catalog.db");cache=new File(context.getFilesDir(),"sync-cache");originals=new File(context.getFilesDir(),"sync-originals");
        worker.execute(()->{if(NativeSync.bind()!=0)status="同步暂不可用";publish();});
    }
    void attach(Listener value){worker.execute(()->{listener=value;publish();});}
    void detach(Listener value){worker.execute(()->{if(listener==value){listener=null;closeOwned();}});}
    private boolean busy(){return preparing||receiving||projecting||state==NativeSync.RUNNING||state==NativeSync.CANCELLING||state==NativeSync.CLOSING;}
    private void captureView(){if(!BuildConfig.READER_WAVE3){return;}if(session==0){view=null;return;}try{view=NativeSync.view(session,product.getAbsolutePath());}catch(Throwable failure){view=new String[0][];}}
    private void publish(){Listener target=listener;if(target==null)return;captureView();final String[][] shown=view;String message=accountNotice.isEmpty()?status:accountNotice,root=account.root();boolean active=busy();List<NativeSync.RemoteBook> rows=Collections.unmodifiableList(new ArrayList<>(books));ui.post(()->{if(listener==target){target.update(message,root,rows,active);target.view(shown);}});}
    private void error(Throwable error){status=error instanceof HostTask.Cancelled?"已取消，可重试":error.getMessage()==null?"操作未完成，可重试":error.getMessage();publish();}
    void configure(String root,byte[] secret,boolean remember){byte[] copy=secret.clone();worker.execute(()->{
        try{closeOwned();int code=account.configure(root,copy,remember);accountNotice=code==CredentialStore.OK?(remember?"凭据已安全保存":"仅本次使用凭据"):code==CredentialStore.UNAVAILABLE?"安全存储不可用，可选择仅本次使用":"凭据保存失败";publish();}
        catch(Throwable failure){error(failure);}finally{Arrays.fill(copy,(byte)0);}
    });}
    void forget(){worker.execute(()->{try{closeOwned();account.forgetSecret();accountNotice="凭据已移除；书库和云盘绑定保留";publish();}catch(Throwable failure){error(failure);}});}
    void start(Host host){worker.execute(()->{
        accountNotice="";
        if(busy()){status="请等待当前操作结束";publish();return;}
        if(account.root().isEmpty()){status="请先设置云盘账号";publish();return;}
        final byte[] secret;try{secret=account.authorization();}catch(Throwable failure){error(failure);return;}
        long request=++epoch;preparing=true;sdkTask=new HostTask(()->false);HostTask task=sdkTask;status="准备原件";publish();
        ui.post(()->host.prepareOriginals(task,()->worker.execute(()->{
            try{
                if(request!=epoch)return;preparing=false;sdkTask=null;
                if(!cache.isDirectory()&&!cache.mkdirs())throw new IllegalStateException("同步目录创建失败");
                if(session==0){session=NativeSync.create(product.getAbsolutePath(),cache.getAbsolutePath(),originals.getAbsolutePath(),account.id(),account.root(),secret);if(session==0)throw new IllegalStateException("同步会话创建失败");}
                NativeSync.Snapshot snapshot=new NativeSync.Snapshot(NativeSync.command(session,1));if(snapshot.code!=0)throw new IllegalStateException("同步尚不能开始");state=snapshot.state;status=snapshot.label();publish();schedulePoll();
            }catch(Throwable failure){error(failure);}finally{Arrays.fill(secret,(byte)0);}
        }),failure->worker.execute(()->{Arrays.fill(secret,(byte)0);if(request==epoch){preparing=false;sdkTask=null;error(failure);}})));
    });}
    void cancel(){worker.execute(()->{if(projecting){projectionResumable=true;++epoch;finishProjection("投影已暂停，可继续");return;}if(sdkTask!=null)sdkTask.cancel();if(session!=0){NativeSync.Snapshot view=new NativeSync.Snapshot(NativeSync.command(session,2));state=view.state;status=view.label();schedulePoll();}else status="已请求取消";publish();});}
    void close(){worker.execute(this::closeOwned);}
    private void closeOwned(){
        ++epoch;if(sdkTask!=null)sdkTask.cancel();sdkTask=null;preparing=receiving=projecting=projectionResumable=false;account.clearMemory();
        if(session!=0){NativeSync.Snapshot view=new NativeSync.Snapshot(NativeSync.command(session,3));state=view.state;status=view.label();schedulePoll();}else{state=NativeSync.CLOSED;status="已断开";}
        publish();
    }
    private void schedulePoll(){if(!pollQueued){pollQueued=true;worker.schedule(this::poll,200,TimeUnit.MILLISECONDS);}}
    private void poll(){
        pollQueued=false;if(session==0)return;
        try{
            NativeSync.Snapshot view=new NativeSync.Snapshot(NativeSync.command(session,0));int before=state;state=view.state;status=view.label();
            if(state==NativeSync.CLOSED){NativeSync.Snapshot destroyed=new NativeSync.Snapshot(NativeSync.command(session,4));if(destroyed.code!=0)throw new IllegalStateException("同步会话仍在关闭");session=0;}
            if(state==NativeSync.FINISHED&&before!=NativeSync.FINISHED){loadBooks("");beginProjection();}publish();
            if(state==NativeSync.RUNNING||state==NativeSync.CANCELLING||state==NativeSync.CLOSING)schedulePoll();
        }catch(Throwable failure){error(failure);}
    }
    void refresh(String after){worker.execute(()->{try{loadBooks(after);publish();}catch(Throwable failure){error(failure);}});}
    void continueProjection(){worker.execute(()->{if(!busy()){if(projectionResumable){projecting=true;projectPages=0;status="正在继续更新书架";publish();long request=++epoch;worker.execute(()->projectPage(request));}else beginProjection();}});}
    private void beginProjection(){
        if(projecting)return;projecting=true;projectionResumable=false;projectKind=projectPages=projectUnresolved=shelfUnresolved=shelfPass=0;projectCursor="";
        status="同步记录已接收，正在更新书架";publish();long request=++epoch;worker.execute(()->projectPage(request));
    }
    private void projectPage(long request){
        if(!projecting||request!=epoch)return;
        try{
            if(++projectPages>200){projectionResumable=true;finishProjection("书架更新达到本轮上限，可继续");return;}
            int count;
            synchronized(IntentJournal.LOCK){
                if(journal.read()!=null){projectionResumable=true;finishProjection("有待恢复的本地修改；请先处理后继续");return;}
                if(projectKind==0){
                    String[][] rows=NativeSync.books(product.getAbsolutePath(),projectCursor);count=rows.length;
                    for(String[] row:rows){NativeSync.RemoteBook book=new NativeSync.RemoteBook(row);projectCursor=book.key;
                        if(book.selection!=4){projectUnresolved++;continue;}
                        String sort=java.text.Normalizer.normalize(book.title,java.text.Normalizer.Form.NFC);
                        if(NativeSync.projectBook(product.getAbsolutePath(),book.key,book.revision,sort)!=0)projectUnresolved++;
                    }
                }else{
                    String[][] rows=NativeSync.projectOrganization(product.getAbsolutePath(),PROJECT_KINDS[projectKind],projectCursor);count=rows.length;
                    for(String[] row:rows){projectCursor=row[0];if(!row[1].equals("0")){if(projectKind==1)shelfUnresolved++;else projectUnresolved++;}}
                }
            }
            if(count<50){
                if(projectKind==1&&shelfUnresolved>0&&++shelfPass<8){shelfUnresolved=0;projectCursor="";}
                else{if(projectKind==1)projectUnresolved+=shelfUnresolved;projectKind++;projectCursor="";}
            }
            if(projectKind==PROJECT_KINDS.length){finishProjection(projectUnresolved==0?"本轮同步结束，书架已更新":"书架有冲突或缺少依赖，可继续重试");return;}
            worker.execute(()->projectPage(request));
        }catch(Throwable failure){projecting=false;projectionResumable=false;status="书架更新未完成，可继续重试";publish();}
    }
    private void finishProjection(String message){projecting=false;status=message;try{loadBooks("");}catch(Throwable failure){status="书架更新未完成，可继续重试";}publish();Listener target=listener;if(target!=null)ui.post(()->{if(listener==target)target.projected();});}
    private void loadBooks(String after){String[][] rows=NativeSync.books(product.getAbsolutePath(),after);books.clear();for(String[] row:rows)books.add(new NativeSync.RemoteBook(row));}
    void receive(Host host,NativeSync.RemoteBook book){worker.execute(()->{
        if(busy()||!book.receivable()){status="当前不能接收这本书";publish();return;}
        File cached=new File(cache,book.sha+"."+book.format);if(!cached.isFile()){status="请先完成一轮同步";publish();return;}
        long request=++epoch;receiving=true;sdkTask=new HostTask(()->false);HostTask task=sdkTask;status="接收书籍";publish();
        ui.post(()->host.receive(book,cached,task,id->worker.execute(()->{if(request==epoch){receiving=false;sdkTask=null;status="书籍已接收";try{loadBooks("");}catch(Throwable failure){error(failure);}publish();}}),failure->worker.execute(()->{if(request==epoch){receiving=false;sdkTask=null;error(failure);}})));
    });}
}
