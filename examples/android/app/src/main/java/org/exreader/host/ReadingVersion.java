// SPDX-License-Identifier: MIT
package org.exreader.host;

import org.json.JSONArray;
import org.json.JSONObject;

/** Retained immutable history, explicitly not a current selected head. */
final class ReadingVersion {
    final ReadingCapture capture;final String body,id,sha,operation;final String[] parents;final int wireBytes;
    ReadingVersion(ReadingCapture capture,String body,String id,String sha,String operation,byte[] wire)throws Exception {
        if(wire==null||wire.length>1048576)throw new IllegalArgumentException("Invalid retained reading wire");
        this.capture=capture;this.body=body;this.id=id;this.sha=sha;this.operation=operation;wireBytes=wire.length;
        JSONObject document=new JSONObject(ReadingCapture.decode(wire));JSONArray list=document.getJSONArray("parents");if(list.length()>32)throw new IllegalArgumentException("Retained parents exceed their limit");parents=new String[list.length()];for(int i=0;i<parents.length;i++){parents[i]=list.getString(i);ReadingRequests.requireId(parents[i]);}
    }
    boolean restorable(){return capture!=null&&!operation.equals("delete");}
    String label(){String quote=capture==null?"":capture.text(0);String text=body.isEmpty()?quote:body;return ReadingRecord.preview(text==null||text.isEmpty()?"保留的位置":text);}
}
