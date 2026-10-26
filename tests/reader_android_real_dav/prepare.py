"""Prepare test-only copies of the existing actual Android UI runners."""
from pathlib import Path
import os
import re
assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = Path('build/android-page-theme/candidate/host-session/java/org/exreader/host/HostSyncTest.java')
s = p.read_text()
needle = '            if(phase.equals("first")){' 
assert s.count(needle) == 1
s = s.replace(needle, '''            if(phase.equals("interop-send")){
                check("actual_activity_restores_shelf",()->{context.startActivity(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));until(node->node.isVisibleToUser()&&node.isEnabled()&&(id(node,"back_button")||"More shelf actions".contentEquals(node.getContentDescription()==null?"":node.getContentDescription())),node->{if(id(node,"back_button"))tap(node);},30000);until(node->node.isVisibleToUser()&&"More shelf actions".contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),null,30000);});
                check("open_sync_panel",this::panel);
                check("configure_session_credentials",()->settings(false));
                check("actual_activity_syncs_existing_record_sender",()->{click("立即同步");status("本轮同步结束");});
                check("actual_session_closes",()->{click("断开");closed();});
            }else if(phase.equals("first")){''')
s = s.replace('}catch(Throwable error){failure=error;if("semantics".equals(phase))',
              '}catch(Throwable error){failure=error;if("interop-send".equals(phase))try{capture("interop-failure");}catch(Throwable ignored){}if("semantics".equals(phase))')
p.write_text(s)
p = Path('build/android-page-theme/candidate/preferences/java/org/exreader/host/RecordInteropTest.java')
s = p.read_text()
needle = '    @Override public void onStart(){'
assert s.count(needle) == 1
s = s.replace(needle, '''    private void receiveGtkSync()throws Exception{
        JSONObject incoming=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"gtk-reverse.json").toPath()),StandardCharsets.UTF_8));
        books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-books.json").toPath()),StandardCharsets.UTF_8));
        open("txt");idle();String before=snapshot();JSONArray rows=incoming.getJSONArray("records");need(rows.length()==2,"two actual GTK revisions expected");
        owner(store->{for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);String rid=row.getString("id");
            byte[] expected=Files.readAllBytes(new File(context.getFilesDir(),"gtk-reverse/"+rid+".json").toPath());
            byte[] retained=RecordWireProbe.retained(store.productOwner(),rid);need(Arrays.equals(expected,retained)&&digest(retained).equals(row.getString("sha256")),"actual synced original GTK wire bytes retained");
            boolean progress=row.getString("kind").equals("progress");ReadingRecord actual=NativeReadingProduct.selected(store,key("txt"),row.getString("annotation_id"),rid,progress,control());
            need(actual.readable()&&actual.missingParents==0&&actual.capture.parser.equals("3.41.0"),"actual selected GTK record is complete and parser preserved");
            NativeReadingSdk.Match found=resolve(store,book("txt"),actual.capture);
            need(found.found()&&found.start==row.getLong("start")&&found.end==row.getLong("end")&&Arrays.deepEquals(found.recaptured.bytes(),actual.capture.bytes()),"actual Android SDK independently resolves exact GTK selector");
            resolutionRows.put(new JSONObject().put("revision_id",rid).put("found",true).put("start",found.start).put("end",found.end));
        }return true;});need(snapshot().equals(before),"read-only reverse resolve preserves SDK and outbox");
    }
''' + needle)
s = s.replace('phase.equals("sender")||phase.equals("incoming")||phase.equals("missing-parent")',
              'phase.equals("sender")||phase.equals("incoming")||phase.equals("missing-parent")||phase.equals("gtk-receive")')
needle = '}else if(phase.equals("missing-parent"))'
assert s.count(needle) == 1
s = s.replace(needle, '}else if(phase.equals("gtk-receive")){check("actual_gtk_sync_wires_selected_and_found",this::receiveGtkSync);' + needle)
p.write_text(s)
p = Path('tests/reader_android_record_interop/run_ui.py')
s = p.read_text()
s, count = re.subn(r",'missing-parent':\[[^\]]*\]", '', s, count=1)
assert count == 1
old = "len({row['pid'] for row in reports})==2 and sum(row['count'] for row in reports)==8"
assert old in s
s = s.replace(old, "len(reports)==1 and sum(row['count'] for row in reports)==6")
Path('build/android-page-theme/candidate/record_sender_only.py').write_text(s)
