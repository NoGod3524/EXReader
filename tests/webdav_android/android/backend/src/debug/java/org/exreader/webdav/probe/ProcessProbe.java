// SPDX-License-Identifier: MIT
package org.exreader.webdav.probe;
import java.io.File;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;
final class ProcessProbe {
    static void run(File files)throws Exception{
        if(NativeDav.bind()!=0)throw new AssertionError("bind");
        JSONObject input=new JSONObject(new String(Files.readAllBytes(new File(files,"input.json").toPath()),StandardCharsets.UTF_8));
        File dir=new File(files,"process");dir.mkdirs();byte[] bytes=new byte[524288];for(int i=0;i<bytes.length;i++)bytes[i]=(byte)(i%251);
        Files.write(new File(dir,"source.bin").toPath(),bytes);
        byte[] result=NativeDav.request(input.getString("root"),input.getString("authorization"),dir.getAbsolutePath(),"put","process.bin","download.bin",new long[]{0,0,0,30000,-1,bytes.length},true);
        Files.write(new File(files,"process-result.json").toPath(),result);
    }
}
