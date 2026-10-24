// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.CancellationSignal;
import android.text.InputType;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

/** Native organization UI. One 50-row page; no retained page/window cache. */
final class OrganizationPanel {
    interface Work<T> { T run(BookStore books,HostTask task) throws Exception; }
    interface Done<T> { void run(T result); }
    private final Activity activity;
    private final Executor worker;
    private final Supplier<BookStore> store;
    private final Runnable changed;
    private final LinearLayout panel;
    private final TextView heading,status;
    private final ListView list;
    private final EditText search;
    private final ArrayAdapter<String> adapter;
    private final Button previous,next,create,remove,mode,add,retry;
    private final AtomicLong generation=new AtomicLong();
    private final List<OrganizationStore.Group> path=new ArrayList<>();
    private final List<Object> rows=new ArrayList<>();
    private volatile boolean closed;
    private HostTask task;
    private int kind;
    private boolean removed,members,picking,busy;
    private OrganizationStore.Group currentGroup;
    private CatalogStore.ShelfBook selectedBook;
    private String query="";

    OrganizationPanel(Activity activity,Executor worker,Supplier<BookStore> store,Runnable changed) {
        this.activity=activity;this.worker=worker;this.store=store;this.changed=changed;
        panel=new LinearLayout(activity);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(12,12,12,12);panel.setBackgroundColor(0xffffffff);
        panel.setContentDescription("Organize panel");panel.setClickable(true);panel.setVisibility(View.GONE);
        heading=new TextView(activity);heading.setTextSize(20);panel.addView(heading);
        search=new EditText(activity);search.setSingleLine(true);search.setHint("Search books");search.setContentDescription("Organize book search");
        LinearLayout navigation=row();
        button(navigation,"Close",v->hide());button(navigation,"Up",v->up());
        button(navigation,"Kind",v->new AlertDialog.Builder(activity).setTitle("Organize")
            .setItems(new String[]{"Shelves","Tags","Series"},(d,n)->{kind=n;reset();load(null,false);}).show());
        remove=button(navigation,"Removed",v->{removed=!removed;members=false;picking=false;path.clear();currentGroup=null;load(null,false);});
        LinearLayout actions=row();
        create=button(actions,"New",v->editGroup(null,0));
        mode=button(actions,"Books",v->{members=!members;load(null,false);});
        add=button(actions,"Add book",v->{picking=true;query="";search.setText("");load(null,false);});
        retry=button(actions,"Saved intent",v->saved());
        panel.addView(search);
        search.setOnEditorActionListener((v,action,event)->{query=search.getText().toString();load(null,false);return true;});
        list=new ListView(activity);list.setContentDescription("Organization items");panel.addView(list,new LinearLayout.LayoutParams(-1,0,1));
        adapter=new ArrayAdapter<>(activity,android.R.layout.simple_list_item_1,new ArrayList<>());list.setAdapter(adapter);
        list.setOnItemClickListener((parent,view,position,id)->{if(!busy&&position>=0&&position<rows.size())select(rows.get(position));});
        LinearLayout paging=row();previous=button(paging,"Previous",v->load(rows.isEmpty()?null:rows.get(0),true));
        next=button(paging,"Next",v->load(rows.isEmpty()?null:rows.get(rows.size()-1),false));
        button(paging,"Refresh",v->load(null,false));button(paging,"Cancel",v->{if(task!=null)task.cancel();});
        status=new TextView(activity);status.setContentDescription("Organization status");status.setMinHeight(48);panel.addView(status);
        FrameLayout root=activity.findViewById(R.id.root);root.addView(panel,root.getChildCount()-1,new FrameLayout.LayoutParams(-1,-1));
    }
    private LinearLayout row() { LinearLayout row=new LinearLayout(activity);row.setOrientation(LinearLayout.HORIZONTAL);panel.addView(row);return row; }
    private Button button(LinearLayout row,String label,View.OnClickListener action) {
        Button b=new Button(activity);b.setText(label);b.setContentDescription(label);b.setOnClickListener(action);row.addView(b,new LinearLayout.LayoutParams(0,-2,1));return b;
    }
    boolean visible() { return panel.getVisibility()==View.VISIBLE; }
    void show(long sdkId) {
        panel.setVisibility(View.VISIBLE);reset();selectedBook=null;
        if(sdkId>0)run((books,t)->books.localShelfBook(sdkId),book->{selectedBook=book;load(null,false);});else load(null,false);
    }
    private void reset() { removed=false;members=false;picking=false;path.clear();currentGroup=null;query="";search.setText(""); }
    void hide() { invalidate();panel.setVisibility(View.GONE);rows.clear();adapter.clear();changed.run(); }
    void close() { closed=true;invalidate(); }
    private void invalidate() { generation.incrementAndGet();if(task!=null)task.cancel();task=null;busy=false; }
    private String parent() { return kind!=0||path.isEmpty()?"":path.get(path.size()-1).id; }
    private void up() {
        if(picking){picking=false;load(null,false);return;}
        if(members){members=false;load(null,false);return;}
        if(!path.isEmpty()){path.remove(path.size()-1);currentGroup=path.isEmpty()?null:path.get(path.size()-1);load(null,false);return;}
        hide();
    }
    private void updateControls() {
        String title=removed?"Removed "+OrganizationStore.KINDS[kind]:OrganizationStore.KINDS[kind];
        for(OrganizationStore.Group group:path)title+=" / "+group.name;
        if(selectedBook!=null)title+=" · choose for "+selectedBook.title;
        heading.setText(picking?"Choose a book":title+(members?" / Books":""));
        remove.setText(removed?"Active":"Removed");
        create.setEnabled(!busy&&!removed&&!members&&!picking);mode.setEnabled(!busy&&!removed&&currentGroup!=null&&!picking);
        mode.setText(members?"Children":"Books");add.setEnabled(!busy&&!removed&&currentGroup!=null&&!picking);
        previous.setEnabled(!busy&&!rows.isEmpty());next.setEnabled(!busy&&rows.size()==50);retry.setEnabled(!busy);
        search.setVisibility(members||picking?View.VISIBLE:View.GONE);list.setEnabled(!busy);
    }
    private <T> void run(Work<T> work,Done<T> done) {
        invalidate();final long token=generation.get();final HostTask request=new HostTask(()->closed||generation.get()!=token);
        task=request;busy=true;status.setText("Working…");updateControls();
        worker.execute(()->{
            T result=null;Throwable failure=null;
            try { BookStore books=store.get();if(books==null)throw new IllegalStateException("Library is still opening");request.check();result=work.run(books,request); }
            catch(Throwable error) { failure=error; }
            final T value=result;final Throwable error=failure;
            activity.runOnUiThread(()->{
                if(closed||generation.get()!=token||!visible())return;
                task=null;busy=false;updateControls();
                if(error!=null)status.setText(error instanceof HostTask.Cancelled?"Canceled before publication; any saved intent remains available":String.valueOf(error.getMessage()));
                else { status.setText("");done.run(value); }
            });
        });
    }
    private void load(Object cursor,boolean before) {
        load(cursor,before,"");
    }
    private void load(Object cursor,boolean before,String outcome) {
        final int requestedKind=kind;final boolean trash=removed,booksMode=members,choose=picking;
        final String requestedParent=parent(),group=currentGroup==null?"":currentGroup.id,filter=query;
        run((books,t)->{
            if(choose)return new ArrayList<Object>(books.shelfPage(filter,cursor==null?null:((CatalogStore.ShelfBook)cursor).key,before,false,new CancellationSignal()));
            if(booksMode)return new ArrayList<Object>(books.organization().members(requestedKind,group,(OrganizationStore.Member)cursor,before,filter));
            return new ArrayList<Object>(books.organization().groups(requestedKind,requestedParent,(OrganizationStore.Group)cursor,before,trash));
        },found->{
            if(found.isEmpty()&&cursor!=null){status.setText("End of list");return;}
            rows.clear();rows.addAll(found);adapter.clear();
            for(Object item:found)adapter.add(item instanceof CatalogStore.ShelfBook?((CatalogStore.ShelfBook)item).title:item.toString());
            status.setText((outcome.isEmpty()?"":outcome+". ")+found.size()+" items · at most 50 retained");updateControls();
        });
    }
    private void select(Object item) {
        if(item instanceof CatalogStore.ShelfBook){picking=false;editMember((CatalogStore.ShelfBook)item);return;}
        if(item instanceof OrganizationStore.Member){editMember(((OrganizationStore.Member)item).book);return;}
        OrganizationStore.Group group=(OrganizationStore.Group)item;
        final int capturedKind=kind;
        run((books,t)->books.organization().group(capturedKind,group.id),edit->{
            if(!edit.selection.editable()){status.setText("Unresolved group revisions; refresh after reviewing conflicts");return;}
            if(edit.group.deleted) {
                new AlertDialog.Builder(activity).setTitle("Restore "+edit.group.name+"?")
                    .setMessage(edit.group.parent.isEmpty()?"Restore this item":"If its parent is removed, restore the parent in Removed first.")
                    .setPositiveButton("Restore",(d,w)->editGroup(edit,2)).setNegativeButton("Close",null).show();return;
            }
            ArrayList<String> actions=new ArrayList<>();actions.add("Books");if(kind==0)actions.add("Children");
            actions.add("Edit");actions.add("Delete");if(selectedBook!=null)actions.add("Add this book");
            new AlertDialog.Builder(activity).setTitle(group.name).setItems(actions.toArray(new String[0]),(d,n)->{
                String choice=actions.get(n);
                if(choice.equals("Edit")){editGroup(edit,0);return;}
                if(choice.equals("Delete")){confirmDelete(edit);return;}
                if(choice.equals("Add this book")){currentGroup=group;editMember(selectedBook);return;}
                if(path.size()>=8){status.setText("Shelf depth limit reached");return;}
                if(kind!=0)path.clear();currentGroup=edit.group;path.add(edit.group);members=choice.equals("Books");load(null,false);
            }).show();
        });
    }
    private EditText field(LinearLayout form,String hint,String value,boolean number) {
        EditText input=new EditText(activity);input.setHint(hint);input.setContentDescription(hint);input.setText(value);input.setSingleLine(true);
        if(number)input.setInputType(InputType.TYPE_CLASS_NUMBER);form.addView(input);return input;
    }
    private void editGroup(OrganizationStore.GroupEdit edit,int operation) {
        final int capturedKind=kind;final String capturedParent=parent();
        if(edit!=null)edit.selection.requireEditable();
        OrganizationStore.Group group=edit==null?null:edit.group;
        LinearLayout form=new LinearLayout(activity);form.setOrientation(LinearLayout.VERTICAL);
        EditText name=field(form,"Name",group==null?"":group.name,false);
        final String[] selectedParent={group==null?capturedParent:group.parent};
        Button parent=new Button(activity);parent.setText(selectedParent[0].isEmpty()?"Parent: Root":"Parent: Current shelf");parent.setContentDescription("Choose parent shelf");form.addView(parent);
        parent.setOnClickListener(v->parentPicker("",null,false,0,chosen->{selectedParent[0]=chosen==null?"":chosen.id;parent.setText("Parent: "+(chosen==null?"Root":chosen.name));}));
        EditText ordinal=field(form,"Order — smaller first",group==null?"0":Long.toString(group.ordinal),true);
        parent.setVisibility(capturedKind==0?View.VISIBLE:View.GONE);ordinal.setVisibility(capturedKind==0?View.VISIBLE:View.GONE);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle(operation==2?"Restore item":edit==null?"New item":"Edit item")
            .setView(form).setPositiveButton(operation==2?"Restore":"Save",null).setNegativeButton("Cancel",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            try {
                String value=IntentJournal.text(name.getText().toString());if(value.trim().isEmpty())throw new IllegalArgumentException("Enter a name");
                String p=capturedKind==0?selectedParent[0]:"";
                long order=capturedKind==0?Long.parseLong(ordinal.getText().toString()):0;if(order<0)throw new IllegalArgumentException("Order must be nonnegative");
                IntentJournal.Command command=IntentJournal.Command.group(capturedKind,operation,group==null?NativeCatalog.newId():group.id,value,p,order,
                        edit==null?new String[0]:edit.selection.heads);
                dialog.dismiss();submit(command,null);
            } catch(Exception error) { name.setError(error.getMessage()); }
        }));dialog.show();
        if(group!=null&&edit.selection.heads.length==0)status.setText("Saving initializes history for this existing item");
    }
    private void parentPicker(String parent,OrganizationStore.Group cursor,boolean before,int depth,Done<OrganizationStore.Group> choose) {
        run((books,t)->books.organization().groups(0,parent,cursor,before,false),groups->{
            ArrayList<String> labels=new ArrayList<>();for(OrganizationStore.Group group:groups)labels.add(group.name);
            AlertDialog picker=new AlertDialog.Builder(activity).setTitle("Choose parent shelf")
                .setItems(labels.toArray(new String[0]),(d,n)->{
                    OrganizationStore.Group group=groups.get(n);
                    new AlertDialog.Builder(activity).setTitle(group.name).setItems(new String[]{"Use as parent","Children"},(dd,action)->{
                        if(action==0)choose.run(group);else if(depth<8)parentPicker(group.id,null,false,depth+1,choose);else status.setText("Shelf depth limit reached");
                    }).setNegativeButton("Cancel",null).show();
                }).setPositiveButton("Root",(d,w)->choose.run(null)).setNegativeButton("Previous",null).setNeutralButton("Next",null).create();
            picker.setOnShowListener(d->{
                picker.getButton(AlertDialog.BUTTON_NEGATIVE).setEnabled(!groups.isEmpty()||cursor!=null);
                picker.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener(v->{picker.dismiss();parentPicker(parent,groups.isEmpty()?cursor:groups.get(0),true,depth,choose);});
                picker.getButton(AlertDialog.BUTTON_NEUTRAL).setEnabled(groups.size()==50);
                picker.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->{picker.dismiss();parentPicker(parent,groups.get(groups.size()-1),false,depth,choose);});
            });picker.show();
        });
    }
    private void confirmDelete(OrganizationStore.GroupEdit edit) {
        if(edit.selection.heads.length==0){status.setText("Save this legacy item once to initialize history before deleting");editGroup(edit,0);return;}
        final int capturedKind=kind;
        new AlertDialog.Builder(activity).setTitle("Delete "+edit.group.name+"?").setMessage("You can restore it from Removed.")
            .setPositiveButton("Delete",(d,w)->submit(IntentJournal.Command.group(capturedKind,1,edit.group.id,edit.group.name,edit.group.parent,edit.group.ordinal,edit.selection.heads),null))
            .setNegativeButton("Cancel",null).show();
    }
    private void editMember(CatalogStore.ShelfBook book) {
        final int capturedKind=kind;final String group=currentGroup.id;
        run((books,t)->books.organization().member(capturedKind,group,book,t),edit->{
            LinearLayout form=new LinearLayout(activity);form.setOrientation(LinearLayout.VERTICAL);
            EditText order=field(form,"Order — smaller first",Long.toString(edit.ordinal),true);order.setVisibility(capturedKind==1?View.GONE:View.VISIBLE);
            TextView explanation=new TextView(activity);explanation.setText(edit.selection.deleted?"Previously removed. Restore uses the observed delete head.":
                    edit.bootstrap!=null?"The original will be verified and book history initialized before membership.":"Change this book's membership.");form.addView(explanation);
            AlertDialog dialog=new AlertDialog.Builder(activity).setTitle(book.title).setView(form)
                .setPositiveButton(edit.selection.deleted?"Restore":edit.present?"Save order":"Add",null)
                .setNeutralButton(edit.present?"Remove":"Cancel",null).setNegativeButton("Close",null).create();
            dialog.setOnShowListener(d->{
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{try {
                    long ordinal=capturedKind==1?0:Long.parseLong(order.getText().toString());if(ordinal<0)throw new IllegalArgumentException("Order must be nonnegative");
                    IntentJournal.Command command=IntentJournal.Command.member(capturedKind,edit.selection.deleted?2:0,group,edit.key,ordinal,edit.selection.heads);
                    dialog.dismiss();submit(command,edit.bootstrap);
                } catch(Exception error){order.setError(error.getMessage());}});
                dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->{
                    dialog.dismiss();if(edit.present) {
                        if(edit.selection.heads.length==0){status.setText("Save the legacy membership once before removing it");return;}
                        submit(IntentJournal.Command.member(capturedKind,1,group,edit.key,edit.ordinal,edit.selection.heads),edit.bootstrap);
                    }
                });
            });dialog.show();
        });
    }
    private void submit(IntentJournal.Command command,IntentJournal.Command bootstrap) {
        run((books,t)->books.organization().submit(command,bootstrap,t),outcome->{if(outcome.equals("Change committed"))load(null,false,outcome);else status.setText(outcome);changed.run();});
    }
    private void saved() {
        run((books,t)->books.organization().journal.read(),pending->{
            if(pending==null){status.setText("No saved intent");return;}
            new AlertDialog.Builder(activity).setTitle("Saved intent")
                .setMessage(pending.outcome+"\n"+(pending.command.operation==1?"Remove":pending.command.operation==2?"Restore":"Save")+" "+
                    OrganizationStore.KINDS[pending.command.kind]+(pending.command.type==0?": "+pending.command.name:" book membership")+
                    (pending.command.kind==1?"":"\nOrder: "+pending.command.ordinal))
                .setPositiveButton("Retry exact intent",(d,w)->run((books,t)->books.organization().retry(t),outcome->{if(outcome.equals("Change committed"))load(null,false,outcome);else status.setText(outcome);changed.run();}))
                .setNeutralButton("Discard and review",(d,w)->new AlertDialog.Builder(activity).setTitle("Discard recovery intent?")
                    .setMessage("Committed book history remains. Refresh and review current state before creating another intent.")
                    .setPositiveButton("Discard",(dd,ww)->run((books,t)->{books.organization().journal.clear();return "Intent discarded; refresh before editing";},status::setText))
                    .setNegativeButton("Keep",null).show())
                .setNegativeButton("Close",null).show();
        });
    }
}
