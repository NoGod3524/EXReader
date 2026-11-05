    private void saveEvidence(String name,String value)throws Exception {
        Files.write(new File(context.getFilesDir(),name).toPath(),value.getBytes(StandardCharsets.UTF_8));
    }
    private void syncStatus(String value){
        until(node->description(node,"同步状态")&&text(node).contains(value),null,"sync "+value,120000);
    }
    private void syncField(String label,String value){
        until(node->description(node,label),node->{Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);need(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args),"real account field");},label,30000);
    }
    private void commitUi(String label,Check action)throws Exception {
        // Existing historical Debug gate pauses only after the real product
        // commit, before the app clears its own original durable request.
        gate("committed");
        try {
            action.run();arrived("committed");
            byte[] request=Files.readAllBytes(new File(context.getFilesDir(),"reading-request.json").toPath());
            Files.write(new File(context.getFilesDir(),"android340-request-"+label+".json").toPath(),request);
        } finally {
            Files.write(new File(context.getFilesDir(),"reading-committed-gate-release").toPath(),new byte[]{1});
        }
        settled();
    }
    @Override public void onStart(){
        context=getTargetContext();phase="sender";Throwable failure=null;Bundle result=new Bundle();
        JSONObject identity=new JSONObject();
        try {
            readerMonitor=addMonitor(MainActivity.class.getName(),null,false);
            AccessibilityServiceInfo service=getUiAutomation().getServiceInfo();
            service.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            getUiAutomation().setServiceInfo(service);
            need(BuildConfig.READER_READING&&BuildConfig.READER_NAVIGATION&&BuildConfig.READER_SEARCH&&BuildConfig.READER_SYNC,"historical features enabled");
            String[] sdkIdentity=NativeLibrary.syncIdentity();
            need(sdkIdentity.length==4&&sdkIdentity[0].equals("3.40.0")&&sdkIdentity[1].contains("libexreader.so")&&sdkIdentity[1].equals(sdkIdentity[2]),"actual loaded SDK is exactly 3.40.0");
            identity.put("runtime",new JSONArray(Arrays.asList(sdkIdentity)));
            identity.put("maps",new String(Files.readAllBytes(new File("/proc/self/maps").toPath()),StandardCharsets.UTF_8));
            input=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"reading-input.json").toPath()),StandardCharsets.UTF_8));
            check("public_sdk_import_originals_without_prefilled_records",()->{
                importOriginals();launch();open("txt");need(revisions()==0,"no product revision prefill");
                panel();status("0 条记录");capture("empty-records");closePanel();
            });
            check("actual_txt_ui_progress_and_bookmark",()->{
                panel();commitUi("progress",()->click("保存进度"));
                ReadingRecord progress=records("txt").progress;
                need(progress.readable()&&progress.capture.start==progress.capture.end&&progress.anchorVersion==2,"real SDK progress selector");
                click("添加书签");setText("Android 3.40 actual TXT bookmark");commitUi("bookmark",()->click("保存"));
                ReadingRecord point=record("txt","Android 3.40 actual TXT bookmark");
                need(point.readable()&&point.capture.mode==ReadingCapture.REFLOW&&point.capture.start==point.capture.end,"real SDK bookmark selector");
                capture("txt-progress-bookmark");closePanel();
            });
            check("actual_txt_gesture_annotation_and_ui_edit",()->{
                selectText();panel();click("标注选中文本");setText("Android 3.40 original annotation");commitUi("annotation",()->click("保存"));
                ReadingRecord before=record("txt","Android 3.40 original annotation");
                need(before.capture.end>before.capture.start,"actual gesture captures a range");
                contains("Android 3.40 original annotation");click("编辑文字");setText("Android 3.40 edited annotation");commitUi("edit",()->click("保存"));
                ReadingRecord after=record("txt","Android 3.40 edited annotation");
                need(Arrays.equals(before.capture.numbers(),after.capture.numbers())&&Arrays.equals(before.capture.route(),after.capture.route())&&Arrays.deepEquals(before.capture.bytes(),after.capture.bytes())&&before.anchorVersion==after.anchorVersion,"UI edit preserves selector and parser");
                capture("txt-annotation-edited");closePanel();
            });
            saveEvidence("android340-before-sync.json",snapshot());
            saveEvidence("android340-books.json",books.toString(2));
            check("actual_ui_authenticated_https_sync",()->{
                until(node->id(node,"back_button")&&node.isVisibleToUser()&&node.isEnabled(),this::tap,"back to shelf",30000);
                until(node->id(node,"import_button")&&node.isVisibleToUser(),null,"shelf",30000);
                click("More");click("同步");syncStatus("");click("云盘账号");
                JSONObject credentials=new JSONObject(new String(Files.readAllBytes(new File(context.getFilesDir(),"android340-account.json").toPath()),StandardCharsets.UTF_8));
                Files.delete(new File(context.getFilesDir(),"android340-account.json").toPath());
                syncField("云盘地址",credentials.getString("root"));syncField("云盘用户名",credentials.getString("user"));syncField("云盘密码",credentials.getString("password"));
                click("仅本次使用");syncStatus("仅本次使用凭据");click("立即同步");syncStatus("本轮同步结束");
                capture("actual-sync-complete");click("断开");
                long end=SystemClock.elapsedRealtime()+30000;while(NativeSyncProbe.sessions()!=0&&SystemClock.elapsedRealtime()<end)SystemClock.sleep(100);
                need(NativeSyncProbe.sessions()==0,"actual native session closed");
            });
            saveEvidence("android340-after-sync.json",snapshot());
        } catch(Throwable error) {failure=error;}
        try {
            JSONObject report=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id")).put("attempt",arguments.getString("attempt"))
                .put("historical_host_sha","047648865e509d5835b7d6e1389681e314d94e28").put("sdk_sha","9854061be331fe603a1822d9b2b36ee357154927")
                .put("scope","TXT progress, bookmark, selection annotation and note edit only").put("sdk_version","3.40.0")
                .put("pid",android.os.Process.myPid()).put("passed",failure==null).put("checks",checks).put("observations",observations).put("loaded_sdk",identity);
            if(failure!=null)report.put("failed_check",active).put("failure",failure.toString()).put("trace",android.util.Log.getStackTraceString(failure));
            saveEvidence("android340-sender-report.json",report.toString(2));
        }catch(Throwable reporting){failure=reporting;}
        result.putString("stream",failure==null?"ANDROID340_SENDER_PASS":"ANDROID340_SENDER_FAIL");
        finish(failure==null?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
    }
