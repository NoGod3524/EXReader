// SPDX-License-Identifier: MIT
package org.exreader.credentials.probe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;

import org.exreader.credentials.CredentialStore;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.Key;
import java.security.KeyStore;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * am instrument -w -e phase uninitialized|suite|reopen|cleanup
 * Reads files/credentials-input.txt (removed after reading), runs the shared C
 * suite through the installed C ABI and the Java checks, and writes check lines
 * to files/credentials-result.txt. No secret is ever logged or reported.
 */
public final class CredentialsProbe extends Instrumentation {
    static { System.loadLibrary("credentials_probe"); }

    private static native String runNative(Context context, String phase, String input, boolean bind);

    private final List<String> out = new ArrayList<>();
    private int failed, total;
    private String phase;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        phase = arguments == null ? null : arguments.getString("phase");
        start();
    }

    @Override public void onStart() {
        super.onStart();
        Context context = getTargetContext();
        File io = context.getFilesDir();
        Bundle result = new Bundle();
        try {
            File inputFile = new File(io, "credentials-input.txt");
            byte[] raw = Files.readAllBytes(inputFile.toPath());
            if (!inputFile.delete()) report("harness-input-removed", false, "kept");
            String text = new String(raw, StandardCharsets.US_ASCII);
            Arrays.fill(raw, (byte) 0);
            Input in = Input.parse(text);
            switch (phase == null ? "" : phase) {
                case "uninitialized":
                    nativeLines(runNative(context, "unavailable", text, false));
                    report("java-null-context-or-namespace-refused",
                            CredentialStore.open(null, in.ns) == null && CredentialStore.open(context, null) == null,
                            "ARGUMENT");
                    summary("java-uninitialized");
                    break;
                case "suite":
                    nativeLines(runNative(context, "suite", text, true));
                    javaSuite(context, in);
                    summary("java-suite");
                    break;
                case "reopen":
                    javaReopen(context, in);
                    summary("java-reopen");
                    nativeLines(runNative(context, "reopen", text, true));
                    break;
                case "cleanup":
                    nativeLines(runNative(context, "cleanup", text, true));
                    javaCleanup(context, in);
                    summary("java-cleanup");
                    break;
                default:
                    report("harness-phase", false, "unknown");
            }
        } catch (Throwable t) {
            report("probe-exception", false, t.getClass().getSimpleName());
        }
        try (FileOutputStream f = new FileOutputStream(new File(io, "credentials-result.txt"))) {
            f.write((String.join("\n", out) + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            failed++;
        }
        result.putInt("failed", failed);
        result.putInt("lines", out.size());
        finish(failed == 0 ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }

    private void nativeLines(String text) {
        for (String line : text.split("\n")) {
            if (line.isEmpty()) continue;
            out.add(line);
            if (line.startsWith("check ") && !line.contains(" pass ")) failed++;
        }
    }

    private void report(String id, boolean ok, String detail) {
        out.add("check " + id + (ok ? " pass " : " fail ") + detail);
        total++;
        if (!ok) failed++;
    }

    private void summary(String name) {
        int f = 0, t = 0;
        for (String line : out) {
            if (!line.startsWith("check java-")) continue;
            t++;
            if (!line.contains(" pass ")) f++;
        }
        out.add("phase " + name + " " + (t - f) + "/" + t);
    }

    // ----- Java API checks -----

    private static final byte SENTINEL = (byte) 0xA5;

    private boolean exact(CredentialStore store, String account, byte[] expected) {
        byte[] buffer = new byte[CredentialStore.SECRET_MAX + 16];
        Arrays.fill(buffer, SENTINEL);
        int[] length = {-1};
        int status = store.get(account, buffer, length);
        boolean ok = status == CredentialStore.OK && length[0] == expected.length
                && Arrays.equals(Arrays.copyOf(buffer, expected.length), expected);
        for (int i = expected.length; i < buffer.length; ++i) if (buffer[i] != SENTINEL) ok = false;
        Arrays.fill(buffer, (byte) 0);
        return ok;
    }

    private int status(CredentialStore store, String account) {
        byte[] buffer = new byte[CredentialStore.SECRET_MAX];
        int[] length = {-1};
        int s = store.get(account, buffer, length);
        Arrays.fill(buffer, (byte) 0);
        return length[0] == 0 ? s : -1;
    }

    private static String javaNs(String ns) { return ns + "-j"; }

    private static File recordDir(Context context, String ns) {
        return new File(new File(context.getNoBackupFilesDir(), "exreader-credentials"), ns);
    }

    private void javaSuite(Context context, Input in) throws Exception {
        String ns = javaNs(in.ns), ns2 = javaNs(in.ns2);
        String a = in.accounts.get("a"), b = in.accounts.get("b"), c = in.accounts.get("c"), d = in.accounts.get("d");
        report("java-open-rejects-invalid",
                CredentialStore.open(context, "Upper") == null && CredentialStore.open(context, "") == null
                        && CredentialStore.open(context, ".lead") == null && CredentialStore.open(context, "a/b") == null
                        && CredentialStore.open(context, new String(new char[65]).replace('\0', 'a')) == null
                        && CredentialStore.open(context, new String(new char[64]).replace('\0', 'a')) != null
                        && CredentialStore.VERSION.equals("0.1.0"), "ARGUMENT");
        CredentialStore store = CredentialStore.open(context, ns), store2 = CredentialStore.open(context, ns2);
        report("java-empty-not-found", status(store, a) == CredentialStore.NOT_FOUND
                && store.delete(a) == CredentialStore.NOT_FOUND, "NOT_FOUND");
        int put1 = store.put(a, in.secret("primary"));
        boolean first = put1 == CredentialStore.OK && exact(store, a, in.secret("primary"));
        int put2 = store.put(a, in.secret("update"));
        report("java-write-read-exact-update", first && put2 == CredentialStore.OK && exact(store, a, in.secret("update")),
                "put=" + CredentialStore.statusName(put1) + "," + CredentialStore.statusName(put2));

        byte[] oversize = new byte[CredentialStore.SECRET_MAX + 1];
        byte[] small = new byte[10];
        Arrays.fill(small, SENTINEL);
        int[] length = {-1};
        int smallStatus = store.get(a, small, length);
        boolean untouched = true;
        for (byte x : small) if (x != SENTINEL) untouched = false;
        boolean bounds = store.put(b, oversize) == CredentialStore.ARGUMENT && store.put(b, new byte[0]) == CredentialStore.ARGUMENT
                && store.put(b, null) == CredentialStore.ARGUMENT && store.put(b, small, 11) == CredentialStore.ARGUMENT
                && store.put(a.toUpperCase(), small) == CredentialStore.ARGUMENT && store.put("{" + a + "}", small) == CredentialStore.ARGUMENT
                && store.delete(a.substring(1)) == CredentialStore.ARGUMENT && store.get(a, null, length) == CredentialStore.ARGUMENT
                && store.get(a, small, null) == CredentialStore.ARGUMENT
                && smallStatus == CredentialStore.ARGUMENT && untouched && status(store, b) == CredentialStore.NOT_FOUND;
        length[0] = -1;
        smallStatus = store.get(a, small, length);
        bounds = bounds && smallStatus == CredentialStore.ARGUMENT && length[0] == in.secret("update").length;
        report("java-bounds-and-arguments", bounds && exact(store, a, in.secret("update")), "ARGUMENT");

        boolean values = store.put(c, in.secret("unicode")) == CredentialStore.OK && exact(store, c, in.secret("unicode"))
                && store.put(c, in.secret("binary")) == CredentialStore.OK && exact(store, c, in.secret("binary"))
                && store.put(d, in.secret("max")) == CredentialStore.OK && exact(store, d, in.secret("max"));
        report("java-unicode-binary-maximum", values, "exact");

        boolean deleted = store.put(b, in.secret("other")) == CredentialStore.OK && exact(store, b, in.secret("other"))
                && store.delete(b) == CredentialStore.OK && status(store, b) == CredentialStore.NOT_FOUND
                && store.delete(b) == CredentialStore.NOT_FOUND && exact(store, a, in.secret("update"));
        report("java-delete-and-repeat-delete", deleted, "NOT_FOUND");

        // Every record file of both the Java and the JNI namespace must be ciphertext only.
        boolean sealed = true;
        int files = 0;
        for (String n : new String[] {ns, in.ns}) {
            File[] list = recordDir(context, n).listFiles();
            if (list == null) continue;
            for (File f : list) {
                files++;
                byte[] data = Files.readAllBytes(f.toPath());
                String ascii = new String(data, StandardCharsets.ISO_8859_1);
                for (byte[] s : in.secrets.values()) {
                    byte[] tail = Arrays.copyOfRange(s, Math.max(0, s.length - 16), s.length);
                    if (indexOf(data, tail) >= 0 || ascii.contains(Input.hex(tail))) sealed = false;
                }
                Arrays.fill(data, (byte) 0);
            }
        }
        report("java-encrypted-at-rest", sealed && files >= 3, "records=" + files);

        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        Key key = keyStore.getKey("EXReaderCredentials/" + ns, null);
        report("java-keystore-key-not-exportable", key != null && key.getEncoded() == null
                && "AES".equals(key.getAlgorithm()), "AndroidKeyStore");

        File dir = recordDir(context, ns);
        Files.copy(new File(dir, a + ".rec").toPath(), new File(dir, b + ".rec").toPath());
        int swapped = status(store, b);
        report("java-record-bound-to-account", swapped == CredentialStore.IO && store.delete(b) == CredentialStore.OK
                && exact(store, a, in.secret("update")), "swapped=" + CredentialStore.statusName(swapped));

        boolean put3 = store2.put(d, in.secret("ns2")) == CredentialStore.OK; // creates the second namespace key
        File dir2 = recordDir(context, ns2);
        Files.copy(new File(dir, a + ".rec").toPath(), new File(dir2, a + ".rec").toPath());
        int foreign = status(store2, a);
        report("java-record-bound-to-namespace", put3 && foreign == CredentialStore.IO
                && store2.delete(a) == CredentialStore.OK && exact(store2, d, in.secret("ns2"))
                && store2.delete(d) == CredentialStore.OK && exact(store, a, in.secret("update")),
                "foreign=" + CredentialStore.statusName(foreign));

        boolean own = store.delete(a) == CredentialStore.OK && store.delete(c) == CredentialStore.OK
                && store.delete(d) == CredentialStore.OK
                && store.put(in.accounts.get("r"), in.secret("reopen")) == CredentialStore.OK;
        report("java-reopen-record-written", own, own ? "OK" : "FAILED");
    }

    private void javaReopen(Context context, Input in) {
        CredentialStore jni = CredentialStore.open(context, in.ns);
        report("java-reads-jni-written-record", exact(jni, in.accounts.get("r"), in.secret("reopen")), "OK");
        CredentialStore store = CredentialStore.open(context, javaNs(in.ns));
        String r = in.accounts.get("r");
        report("java-new-process-reads-record", exact(store, r, in.secret("reopen"))
                && store.delete(r) == CredentialStore.OK && status(store, r) == CredentialStore.NOT_FOUND, "OK");
    }

    private void javaCleanup(Context context, Input in) throws Exception {
        boolean ok = true;
        for (String n : new String[] {in.ns, in.ns2, javaNs(in.ns), javaNs(in.ns2)}) {
            CredentialStore store = CredentialStore.open(context, n);
            for (String account : in.accounts.values()) {
                int s = store.delete(account);
                if (s != CredentialStore.OK && s != CredentialStore.NOT_FOUND) ok = false;
                if (status(store, account) != CredentialStore.NOT_FOUND) ok = false;
            }
            File dir = recordDir(context, n);
            File[] rest = dir.listFiles();
            if (rest != null && rest.length != 0) ok = false;
            dir.delete();
        }
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        for (String n : new String[] {in.ns, in.ns2, javaNs(in.ns), javaNs(in.ns2)}) {
            String alias = "EXReaderCredentials/" + n;
            if (keyStore.containsAlias(alias)) keyStore.deleteEntry(alias);
            if (keyStore.containsAlias(alias)) ok = false;
        }
        report("java-cleanup-own-records-and-keys", ok, ok ? "removed" : "residual");
    }

    private static int indexOf(byte[] data, byte[] needle) {
        outer:
        for (int i = 0; i + needle.length <= data.length; ++i) {
            for (int j = 0; j < needle.length; ++j) if (data[i + j] != needle[j]) continue outer;
            return i;
        }
        return -1;
    }

    private static final class Input {
        String ns, ns2;
        final Map<String, String> accounts = new HashMap<>();
        final Map<String, byte[]> secrets = new HashMap<>();

        byte[] secret(String name) { return secrets.get(name); }

        static Input parse(String text) {
            Input in = new Input();
            for (String line : text.split("\n")) {
                String[] p = line.trim().split(" ");
                if (p.length == 2 && p[0].equals("namespace")) in.ns = p[1];
                else if (p.length == 2 && p[0].equals("namespace2")) in.ns2 = p[1];
                else if (p.length == 3 && p[0].equals("account")) in.accounts.put(p[1], p[2]);
                else if (p.length == 3 && p[0].equals("secret")) in.secrets.put(p[1], unhex(p[2]));
            }
            return in;
        }

        static byte[] unhex(String s) {
            byte[] b = new byte[s.length() / 2];
            for (int i = 0; i < b.length; ++i) b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
            return b;
        }

        static String hex(byte[] b) {
            StringBuilder s = new StringBuilder();
            for (byte x : b) s.append(String.format("%02x", x & 0xff));
            return s.toString();
        }
    }
}
