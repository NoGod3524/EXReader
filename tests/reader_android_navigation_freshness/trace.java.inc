    private final JSONArray directoryTrace=new JSONArray();
    private int traceSequence;
    private void traceDirectory(String label,String action,Boolean cache,Boolean scroll)throws Exception {
        if(directoryTrace.length()>=4096)return;
        JSONObject value=new JSONObject().put("sequence",++traceSequence).put("elapsed",SystemClock.elapsedRealtime())
            .put("check",active).put("label",label).put("action",action).put("clear_cache_return",cache==null?JSONObject.NULL:cache)
            .put("scroll_return",scroll==null?JSONObject.NULL:scroll).put("native_live",NativeNavigationProbe.live());
        AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();JSONArray rows=new JSONArray();
        if(root!=null){try{value.put("window_id",root.getWindowId());traceNodes(root,rows,value,0);}finally{root.recycle();}}
        value.put("rows",rows);directoryTrace.put(value);
    }
    private void traceNodes(AccessibilityNodeInfo node,JSONArray rows,JSONObject value,int depth)throws Exception {
        need(depth<=32,"trace hierarchy bound");
        if(description(node,"目录状态"))value.put("ready",text(node));
        if(id(node,"text1")){
            AccessibilityNodeInfo.CollectionItemInfo item=node.getCollectionItemInfo();Rect rect=new Rect();node.getBoundsInScreen(rect);
            rows.put(new JSONObject().put("text",text(node)).put("visible",node.isVisibleToUser()).put("enabled",node.isEnabled())
                .put("row_index",item==null?-1:item.getRowIndex()).put("bounds",rect.toShortString()));
        }
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){try{traceNodes(child,rows,value,depth+1);}finally{child.recycle();}}}
    }
    private void flushDirectoryTrace()throws Exception {
        JSONObject value=new JSONObject().put("source_sha",arguments.getString("source_sha")).put("run_id",arguments.getString("run_id"))
            .put("attempt",arguments.getString("attempt")).put("phase",phase).put("cache_mode",arguments.getString("diagnostic_cache","trace"))
            .put("events",directoryTrace).put("truncated",directoryTrace.length()>=4096).put("accepted",false);
        Files.write(new File(context.getFilesDir(),"navigation-trace-"+phase+".json").toPath(),value.toString().getBytes(StandardCharsets.UTF_8));
    }
