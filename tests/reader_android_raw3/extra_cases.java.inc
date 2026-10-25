    private final JSONObject rawDetails=new JSONObject();
    private static boolean nul(byte[] value){if(value==null)return false;for(byte item:value)if(item==0)return true;return false;}
    private void family(BookStore store)throws Exception{
        String[] actual=Raw3Probe.family(store.productOwner());String[] expected={"0.4.0","0.2.0","0.2.0","0.2.0","0.2.0","0.2.0","0.2.0"};
        need(actual.length==16&&actual[14].equals("2")&&actual[15].equals("explicit-raw-store"),"seven-module explicit family keeps legacy MAX2");
        JSONArray rows=new JSONArray();for(int i=0;i<7;i++){need(actual[2*i].equals(expected[i])&&actual[2*i+1].equals(actual[1])&&actual[1].contains("libexreader_product.so"),"actual versioned raw native provider");rows.put(new JSONObject().put("version",actual[2*i]).put("provider",actual[2*i+1]));}rawDetails.put("family",rows);
    }
    private boolean rawPhase(){return !phase.equals("sender")&&!phase.equals("incoming")&&!phase.equals("missing-parent");}
    private void loadInput(boolean imported)throws Exception{
        input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-input.json").toPath()),StandardCharsets.UTF_8));
        if(imported)books=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"preferences-books.json").toPath()),StandardCharsets.UTF_8));else seed();
    }
    private void editBody(String body){until(node->description(node,"阅读记录文字")&&node.isEnabled(),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,body);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"actual record editor");},"raw3 actual editor",30000);}
    private void bookmarkUi(String body,boolean settle)throws Exception{click("添加书签");editBody(body);click("保存");if(settle){owner(store->true);status(" 条记录");}}
    private void waitPrivate(String name)throws Exception{long end=SystemClock.elapsedRealtime()+60000;while(!new File(context.getFilesDir(),name).isFile()){need(SystemClock.elapsedRealtime()<end,"real owner boundary reached");SystemClock.sleep(40);}}
    private void killUi()throws Exception{
        loadInput(false);open("pdf");panel();Files.write(new File(context.getFilesDir(),"reading-committed-gate-arm").toPath(),new byte[]{1});bookmarkUi("actual raw3 UI pending",false);
        waitPrivate("reading-committed-gate-arrived");byte[] bytes=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());JSONObject pending=new JSONObject(ReadingCapture.decode(bytes));
        need(pending.getInt("version")==2&&pending.getInt("anchor_version")==3&&pending.length()==14,"actual UI persisted explicit private v2 writer3 before uncertain response");
        ReadingCapture copied=captureFrom(pending.getJSONObject("capture"));need(copied.start==0&&copied.end==0&&nul(copied.bytes()[2]),"pending retains actual public NUL point");
        JSONObject boundary=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt")).put("pid",android.os.Process.myPid()).put("revision",pending.getString("revision")).put("pending_sha256",digest(bytes)).put("pending_base64",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP)).put("control_gate_arrived",true);
        capture("raw3-before-real-kill");durable(new File(context.getFilesDir(),"raw3-kill-boundary.json"),boundary.toString(2).getBytes(StandardCharsets.UTF_8));
        Thread.sleep(60000);throw new AssertionError("actual process was not terminated at its committed boundary");
    }
    private void reopenUi()throws Exception{
        loadInput(true);open("pdf");panel();JSONObject boundary=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"raw3-kill-boundary.json").toPath()),StandardCharsets.UTF_8));
        byte[] prior=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());need(digest(prior).equals(boundary.getString("pending_sha256")),"fresh process opens identical pending bytes");JSONObject request=new JSONObject(ReadingCapture.decode(prior));
        need(boundary.getInt("pid")!=android.os.Process.myPid(),"actual fresh Android process");click("上次保存待确认");click("继续确认保存");status(" 条记录");owner(store->true);
        need(!new File(context.getFilesDir(),"reading-request.json").exists(),"successful exact retry clears only confirmed request");owner(store->{
            ReadingRecord selected=NativeReadingProduct.selected(store,key("pdf"),request.getString("annotation"),request.getString("revision"),false,control());byte[] wire=RecordWireProbe.retained(store.productOwner(),selected.head);JSONObject encoded=new JSONObject(ReadingCapture.decode(wire));
            need(selected.readable()&&selected.anchorVersion==3&&sameCapture(selected.capture,captureFrom(request.getJSONObject("capture"))),"actual UI retry retained same version and nullable counted selector bytes");
            need(encoded.getJSONArray("parents").toString().equals(request.getJSONArray("expected").toString()),"actual retry kept observed parent set");
            NativeReadingSdk.Match found=resolve(store,book("pdf"),selected.capture);need(found.found()&&Arrays.deepEquals(found.recaptured.bytes(),selected.capture.bytes()),"fresh UI owner FOUND and recapture of actual NUL point");
            rawDetails.put("revision",selected.head).put("wire_sha256",digest(wire)).put("original_pending_sha256",digest(prior)).put("original_pid",boundary.getInt("pid")).put("fresh_pid",android.os.Process.myPid());return true;
        });capture("raw3-after-real-reopen");
    }
    private void legacyPending()throws Exception{
        loadInput(false);open("pdf");ReadingRequests.Pending pending=owner(store->{
            PageSnapshot live=(PageSnapshot)ReadingReview.field(activity(),"current");ReadingCapture captured=NativeReadingSdk.capture(store,live,0,0,fontBytesForInterop(),24,originalPath(book("pdf")),task(),control());need(nul(captured.bytes()[2]),"legacy negative uses actual NUL suffix");
            NativeCatalog.Result boot=store.bootstrapBook(book("pdf"),NativeCatalog.newId(),new String[0],task());need(boot.status==0,"actual original bootstrap");
            ReadingRequests.Pending request=new ReadingRequests.Pending(book("pdf"),key("pdf"),NativeCatalog.newId(),NativeCatalog.newId(),NativeCatalog.newId(),new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,ReadingCapture.FIXED,captured,"old actual v2 pending");new ReadingRequests(context.getFilesDir(),true).save(request);return request;
        });
        byte[] saved=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());JSONObject legacy=new JSONObject(ReadingCapture.decode(saved));need(legacy.getInt("version")==1&&legacy.length()==13&&!legacy.has("anchor_version"),"legacy private v1 has original fields");
        String before=snapshot();owner(store->{NativeReadingProduct.Result refused=NativeReadingProduct.apply(store,pending.revision,pending.expected,pending.kind,pending.operation,pending.book,pending.id,pending.mode,pending.capture,pending.body);
            need(!refused.saved()&&!refused.created&&refused.gap!=0&&!NativeCatalog.retained(store.productOwner(),pending.revision),"old public writer2 still refuses genuine NUL");return true;});
        need(snapshot().equals(before),"old writer refusal changes no SDK or product outbox");rawDetails.put("legacy_pending_sha256",digest(saved)).put("legacy_revision",pending.revision);
        panel();click("上次保存待确认");click("继续确认保存");status("原请求未能保存");
        byte[] after=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());need(digest(after).equals(rawDetails.getString("legacy_pending_sha256")),"actual MainActivity raw replay never upgrades or rewrites private v1");
        owner(store->{need(!NativeCatalog.retained(store.productOwner(),rawDetails.getString("legacy_revision")),"failed legacy request did not publish a revision");return true;});capture("raw3-legacy-nul-still-pending");
    }
    private NativeReadingProduct.Result restoreUi(ReadingRecord target,ReadingVersion source)throws Exception{
        AtomicReference<NativeReadingProduct.Result> result=new AtomicReference<>();AtomicReference<Throwable> failure=new AtomicReference<>();java.util.concurrent.CountDownLatch done=new java.util.concurrent.CountDownLatch(1);
        ((MainActivity)activity()).readingWrite(book("txt"),new ReadingPanel.Action(NativeReadingProduct.BOOKMARK,NativeReadingProduct.RESTORE,target,source,source.body),task(),value->{result.set(value);done.countDown();},error->{failure.set(error);done.countDown();});
        need(done.await(90,java.util.concurrent.TimeUnit.SECONDS)&&failure.get()==null&&result.get()!=null&&result.get().saved(),"actual MainActivity owner restores explicit source version");return result.get();
    }
    private void rawContract()throws Exception{
        loadInput(false);open("txt");panel();JSONArray restored=new JSONArray();owner(store->{family(store);NativeCatalog.Result boot=store.bootstrapBook(book("txt"),NativeCatalog.newId(),new String[0],task());need(boot.status==0,"TXT actual source fact");return true;});
        for(int version:new int[]{1,2}){
            final int selectedVersion=version;String[] identity=owner(store->{PageSnapshot live=(PageSnapshot)ReadingReview.field(activity(),"current");ReadingCapture captured=NativeReadingSdk.capture(store,live,live.start,live.start,fontBytesForInterop(),24,originalPath(book("txt")),task(),control());String annotation=NativeCatalog.newId(),put=NativeCatalog.newId(),removed=NativeCatalog.newId();
                NativeReadingProduct.Result written=NativeReadingProduct.applyVersioned(store,put,new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,key("txt"),annotation,captured.mode,captured,"source "+selectedVersion,selectedVersion);need(written.saved(),"explicit real source version");
                NativeReadingProduct.Result deleted=NativeReadingProduct.applyVersioned(store,removed,new String[]{put},NativeReadingProduct.BOOKMARK,NativeReadingProduct.DELETE,key("txt"),annotation,captured.mode,null,"",selectedVersion);need(deleted.saved(),"explicit tombstone");return new String[]{annotation,put,removed};});
            ReadingRecord target=owner(store->NativeReadingProduct.selected(store,key("txt"),identity[0],identity[2],false,control()));ReadingVersion source=owner(store->NativeReadingProduct.version(store,key("txt"),identity[0],identity[1],false,control()));need(source.anchorVersion==version,"source version comes from retained validated wire");
            NativeReadingProduct.Result result=restoreUi(target,source);ReadingRecord actual=owner(store->NativeReadingProduct.selected(store,key("txt"),identity[0],result.request,false,control()));need(actual.anchorVersion==version,"restore kept source anchor_version without upgrade");
            final String head=result.request;owner(store->{NativeReadingProduct.Result note=NativeReadingProduct.applyVersioned(store,NativeCatalog.newId(),new String[]{head},NativeReadingProduct.NOTE_TEXT,NativeReadingProduct.PUT,key("txt"),identity[0],actual.mode,null,"edited with source version",3);need(note.saved(),"raw note edits keep actual source");ReadingRecord after=NativeReadingProduct.selected(store,key("txt"),identity[0],note.request,false,control());need(after.anchorVersion==selectedVersion,"NOTE_TEXT cannot invent writer3 on source1/2");return true;});
            restored.put(new JSONObject().put("source_version",version).put("restored_version",actual.anchorVersion));
        }
        rawDetails.put("restores",restored);click("关闭");open("pdf");String[] protocolIdentity=owner(store->{
            PageSnapshot live=(PageSnapshot)ReadingReview.field(activity(),"current");ReadingCapture captured=NativeReadingSdk.capture(store,live,0,0,fontBytesForInterop(),24,originalPath(book("pdf")),task(),control());NativeCatalog.Result boot=store.bootstrapBook(book("pdf"),NativeCatalog.newId(),new String[0],task());need(boot.status==0,"actual PDF original");
            String annotation=NativeCatalog.newId(),put=NativeCatalog.newId();NativeReadingProduct.Result written=NativeReadingProduct.applyVersioned(store,put,new String[0],NativeReadingProduct.BOOKMARK,NativeReadingProduct.PUT,key("pdf"),annotation,captured.mode,captured,"NULL protocol negative source",3);need(written.saved(),"actual counted source for negative");
            JSONObject protocol=new JSONObject(ReadingCapture.decode(RecordWireProbe.retained(store.productOwner(),put)));String id=NativeCatalog.newId(),other=NativeCatalog.newId();protocol.put("id",id).put("entity_key",key("pdf")+":"+other);protocol.getJSONObject("payload").put("annotation_id",other).getJSONObject("location").getJSONObject("selector").put("exact",new JSONObject().put("base64",JSONObject.NULL).put("size",0));
            NativeReadingProbe.receive(store.productOwner(),protocol.toString().getBytes(StandardCharsets.UTF_8));return new String[]{id,other};
        });
        String before=snapshot();owner(store->{
            ReadingRecord unavailable=NativeReadingProduct.selected(store,key("pdf"),protocolIdentity[1],protocolIdentity[0],false,control());ReadingVersion retained=NativeReadingProduct.version(store,key("pdf"),protocolIdentity[1],protocolIdentity[0],false,control());
            need(unavailable.state==ReadingRecord.SAFE&&unavailable.capture==null&&!unavailable.readable()&&retained.capture==null&&!retained.restorable(),"NULL exact protocol expression cannot grant hasLocation or restore");rawDetails.put("null_exact_protocol_only",true);
            long handle=store.productOwner();final boolean[] ownerRefused={false};Thread wrong=new Thread(()->{try{Raw3Probe.family(handle);}catch(IllegalStateException expected){ownerRefused[0]=true;}});wrong.start();wrong.join();need(ownerRefused[0],"raw actual JNI retains original owner thread requirement");return true;
        });need(snapshot().equals(before),"NULL read-only refusal changes no SDK or outbox");
    }
    private JSONObject peerManifest()throws Exception{return new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"raw3-peer-manifest.json").toPath()),StandardCharsets.UTF_8));}
    private NativeSync.Snapshot waitSession(long token,int state)throws Exception{long end=SystemClock.elapsedRealtime()+180000;while(SystemClock.elapsedRealtime()<end){NativeSync.Snapshot seen=new NativeSync.Snapshot(NativeSync.command(token,0));if(seen.state==state)return seen;need(seen.state!=NativeSync.FAILED&&seen.state!=NativeSync.CLOSED,"real raw HTTPS Session remained valid "+seen.status+"/"+seen.httpStatus);SystemClock.sleep(40);}throw new AssertionError("raw native Session timeout");}
    private void networkSession(boolean sending)throws Exception{
        File sourceFile=new File(context.getFilesDir(),"raw3-session-input.json");JSONObject config=new JSONObject(new String(Files.readAllBytes(sourceFile.toPath()),StandardCharsets.UTF_8));Files.delete(sourceFile.toPath());File cache=new File(context.getFilesDir(),"raw3-session-cache"),originals=new File(context.getFilesDir(),"raw3-session-originals");need((cache.isDirectory()||cache.mkdirs())&&(originals.isDirectory()||originals.mkdirs()),"private native Session directories");
        if(sending){loadInput(true);owner(store->{family(store);for(String role:new String[]{"txt","epub","pdf","cbz"}){BookStore.VerifiedSource actual=store.verifySource(book(role),null,0,task());File copy=new File(originals,actual.sha256+"."+actual.format);need(store.nativeLibrary().exportOriginal(book(role),copy.getPath(),task())==actual.bytes&&digest(Files.readAllBytes(copy.toPath())).equals(actual.sha256),"actual SDK original staged for native worker");}return true;});}
        else need(owner(store->store.nativeLibrary().books().length)==0,"fresh network receiver has no SDK originals before actual download");
        need(NativeSync.bind()==0,"actual Android native HTTPS backend bound");byte[] secret=config.getString("authorization").getBytes(StandardCharsets.UTF_8);long token=NativeSync.create(new File(context.getFilesDir(),"reader-catalog.db").getPath(),cache.getPath(),originals.getPath(),config.getString("account"),config.getString("root"),secret);Arrays.fill(secret,(byte)0);need(token!=0,"actual raw native Session created");try{
            need(new NativeSync.Snapshot(NativeSync.command(token,1)).code==0,"native Session starts on its owned worker");NativeSync.Snapshot complete=waitSession(token,NativeSync.FINISHED);need(complete.completedShards==256,"actual complete 256-shard native sweep");rawDetails.put("session",new JSONObject().put("shards",complete.completedShards).put("pushed",complete.pushed).put("pulled",complete.pulled));
            JSONArray originalsExpected=peerManifest().getJSONArray("originals");for(int i=0;i<originalsExpected.length();i++){JSONObject row=originalsExpected.getJSONObject(i);File downloaded=new File(cache,row.getString("sha256")+"."+row.getString("format"));byte[] actual=Files.readAllBytes(downloaded.toPath());need(actual.length==row.getLong("bytes")&&digest(actual).equals(row.getString("sha256")),"actual native downloaded original identity");}
        }finally{need(new NativeSync.Snapshot(NativeSync.command(token,3)).code==0,"nonblocking native Session close");waitSession(token,NativeSync.CLOSED);need(new NativeSync.Snapshot(NativeSync.command(token,4)).code==0,"CLOSED owner destroyed");}
        owner(store->{need(RecordWireProbe.outbox(store.productOwner()).length==0,"native receive never queues and sender ack emptied exact outbox");return true;});
    }
    private void networkReopen()throws Exception{
        JSONObject peer=peerManifest();JSONArray originals=peer.getJSONArray("originals"),revisions=peer.getJSONArray("revisions"),records=peer.getJSONArray("reading_records");books=new JSONObject();
        owner(store->{family(store);NativeLibrary library=store.nativeLibrary();need(library.books().length==0,"fresh Android process imports only actual downloaded originals");
            for(int i=0;i<originals.length();i++){JSONObject row=originals.getJSONObject(i);File actual=new File(context.getFilesDir(),"raw3-session-cache/"+row.getString("sha256")+"."+row.getString("format"));need(digest(Files.readAllBytes(actual.toPath())).equals(row.getString("sha256")),"reopen source is real downloaded cache");
                NativeLibrary.ImportResult imported=library.importFile(actual.getPath(),format(row.getString("format")),"actual downloaded "+row.getString("role"));BookStore.VerifiedSource verified=store.verifySource(imported.id,row.getString("sha256"),row.getLong("bytes"),task());store.finalizeImport(verified);books.put(row.getString("role"),new JSONObject().put("id",imported.id).put("title",verified.book.title).put("format",verified.format).put("sha256",verified.sha256));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+imported.id,actual.getPath()).putLong("size_"+imported.id,actual.length()).commit(),"actual downloaded original mapping");
            }
            for(int i=0;i<revisions.length();i++){JSONObject row=revisions.getJSONObject(i);byte[] stored=RecordWireProbe.retained(store.productOwner(),row.getString("id"));need(digest(stored).equals(row.getString("sha256"))&&Arrays.equals(stored,Files.readAllBytes(incomingFile(row.getString("file")).toPath())),"actual native received complete exact original wire, no public replay fixture");}
            need(RecordWireProbe.outbox(store.productOwner()).length==0,"fresh actual received graph has no outbox");return true;});click("Refresh");
        for(String role:new String[]{"txt","epub","pdf","cbz"}){open(role);idle();String before=snapshot();owner(store->{for(int i=0;i<records.length();i++){JSONObject row=records.getJSONObject(i);if(!row.getString("role").equals(role))continue;byte[] wire=RecordWireProbe.retained(store.productOwner(),row.getString("revision_id"));JSONObject value=new JSONObject(ReadingCapture.decode(wire));boolean progress=value.getString("entity_kind").equals("progress");String annotation=progress?"":value.getJSONObject("payload").getString("annotation_id");
                    ReadingRecord selected=NativeReadingProduct.selected(store,key(role),annotation,row.getString("revision_id"),progress,control());need(selected.readable()&&selected.anchorVersion==row.getLong("anchor_version")&&sameCapture(selected.capture,captureFrom(row.getJSONObject("capture"))),"fresh native received typed record retains actual source version/nullable bytes");
                    NativeReadingSdk.Match found=resolve(store,book(role),selected.capture);need(found.found()&&Arrays.deepEquals(found.recaptured.bytes(),selected.capture.bytes()),"real downloaded source independently FOUND and recaptured after process reopen");resolutionRows.put(new JSONObject().put("role",role).put("revision",selected.head).put("found",true).put("capture",captureJson(found.recaptured)));
                }return true;});need(snapshot().equals(before),"fresh received read-only SDK resolve changes no progress/notes/outbox");}
        need(resolutionRows.length()==11,"all 11 native sender records independently reopened");rawDetails.put("network_reopen_records",resolutionRows.length());
    }
    private void runRawPhase()throws Exception{
        if(phase.equals("kill-ui"))killUi();
        else if(phase.equals("reopen-ui"))check("actual_ui_private_v2_survives_real_kill_and_exact_owner_retry",this::reopenUi);
        else if(phase.equals("legacy-pending"))check("actual_private_v1_replay_stays_writer2_and_genuine_nul_failure_keeps_exact_bytes",this::legacyPending);
        else if(phase.equals("raw-contract"))check("actual_source_v1_v2_restore_note_and_null_location_owner_contract",this::rawContract);
        else if(phase.equals("session-push"))check("actual_android_raw_session_push_ack_close_256_shards",()->networkSession(true));
        else if(phase.equals("session-receive"))check("actual_android_raw_session_fresh_network_receive_256_shards",()->networkSession(false));
        else if(phase.equals("session-reopen"))check("fresh_android_owner_imports_downloaded_originals_and_resolves_11_exact_records",this::networkReopen);
        else throw new AssertionError("unknown actual raw phase");
    }
