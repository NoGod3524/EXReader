// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Service;
import android.content.Intent;
import android.os.*;
import android.os.Process;
import java.io.File;
import java.io.FileOutputStream;
import java.util.Arrays;

/** Each declared subclass runs in a separate process under the actual app UID. */
public abstract class C02ActorService extends Service {
    static final int SOURCE = 1, RELEASE = 2, PENDING = 3;
    private NativeLibrary library;
    private NativeLibrary.Source source;
    private long owner;
    private final Messenger endpoint = new Messenger(new Handler(Looper.getMainLooper(), message -> {
        Bundle result = new Bundle();
        try {
            if (message.what == SOURCE) {
                library = new NativeLibrary(this, new File(getFilesDir(), "library.db"));
                source = library.source(message.getData().getLong("book"));
                try (NativeLibrary.Borrow other = library.borrow()) {
                    boolean refused = false;
                    try { library.closePrimaryForAdmissionTest(); }
                    catch (NativeAdmission.Required expected) { refused = true; }
                    if (!refused || other.checked() == 0 || library.books().length != 1 || C02Probe.canOwn(this))
                        throw new AssertionError("Mixed borrow refusal did not retain Java/SDK/admission ownership");
                    result.putBoolean("mixed_borrow_refused", true);
                }
                library.closePrimaryForAdmissionTest();
                byte[] actual = new byte[C02Probe.ORIGINAL.length];
                if (source.read(0, actual, actual.length) != actual.length || !Arrays.equals(actual, C02Probe.ORIGINAL))
                    throw new AssertionError("SDK source did not survive primary close");
                result.putBoolean("source_read_after_sdk_close", true);
            } else if (message.what == RELEASE) {
                source.close(); source = null;
                library.close(); library = null;
            } else if (message.what == PENDING) {
                owner = C02Probe.begin(this);
                byte[] exact = C02Probe.pending(owner);
                try (FileOutputStream output = new FileOutputStream(new File(getFilesDir(), "c02-pending.bin"))) {
                    output.write(exact); output.getFD().sync();
                }
                result.putByteArray("pending", exact);
            } else throw new IllegalArgumentException("Unknown actor request");
            result.putInt("pid", Process.myPid()); result.putInt("uid", Process.myUid());
        } catch (Throwable error) {
            result.putString("error", android.util.Log.getStackTraceString(error));
        }
        Message reply = Message.obtain(null, message.what); reply.setData(result);
        try { message.replyTo.send(reply); } catch (RemoteException error) { stopSelf(); }
        return true;
    }));
    @Override public IBinder onBind(Intent intent) { return endpoint.getBinder(); }
    @Override public void onDestroy() {
        if (source != null) source.close();
        if (library != null) library.close();
        // A live pending owner belongs to this process until process death.
        super.onDestroy();
    }
}
