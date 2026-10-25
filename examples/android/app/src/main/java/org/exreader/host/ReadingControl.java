// SPDX-License-Identifier: MIT
package org.exreader.host;

/** One borrowed SDK/G04 control. Review gates exist only in Debug. */
final class ReadingControl {
    final HostTask task;private final java.io.File directory;private final String stage;private final boolean gate;private int polls;
    ReadingControl(HostTask task,java.io.File directory,String stage,boolean gate){this.task=task;this.directory=directory;this.stage=stage;this.gate=gate;}
    void check()throws Exception {
        task.check();++polls;if(!BuildConfig.DEBUG||!gate||directory==null||polls<3)return;
        java.io.File armed=new java.io.File(directory,"reading-"+stage+"-gate-arm");if(!armed.isFile())return;
        if(!armed.delete())throw new java.io.IOException("Reading review gate cannot be consumed");
        java.nio.file.Files.write(new java.io.File(directory,"reading-"+stage+"-gate-arrived").toPath(),new byte[]{1});
        java.io.File release=new java.io.File(directory,"reading-"+stage+"-gate-release");long end=android.os.SystemClock.elapsedRealtime()+20000;
        while(!release.isFile()){task.check();if(android.os.SystemClock.elapsedRealtime()>end)throw new java.io.IOException("Reading review gate not released");Thread.sleep(10);}
        if(!release.delete())throw new java.io.IOException("Reading review release cannot be consumed");task.check();
    }
}
