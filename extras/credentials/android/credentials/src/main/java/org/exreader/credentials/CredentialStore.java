// SPDX-License-Identifier: MIT
package org.exreader.credentials;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyStore;
import java.security.ProviderException;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Keystore-protected credential records with the same semantics as the C ABI in
 * exr_credentials.h. Each namespace owns a non-exportable AES-256 key in the
 * AndroidKeyStore; each account is one AES-GCM record in the app's no-backup
 * directory, authenticated with its namespace and account as associated data.
 * Nothing is ever stored without encryption and no record is ever logged.
 */
public final class CredentialStore {
    public static final String VERSION = "0.1.0";
    public static final int OK = 0, NOT_FOUND = 1, UNAVAILABLE = 2, ARGUMENT = 3, IO = 4;
    public static final int SECRET_MAX = 2048;
    public static final int NAMESPACE_MAX = 64;

    private static final String KEYSTORE = "AndroidKeyStore";
    private static final byte[] MAGIC = {'E', 'X', 'R', 'C', 1};
    private static final int IV_BYTES = 12, TAG_BITS = 128;
    private static final Object LOCK = new Object();

    private final File directory;
    private final String namespace;

    private CredentialStore(Context context, String namespace) {
        this.directory = new File(new File(context.getApplicationContext().getNoBackupFilesDir(),
                "exreader-credentials"), namespace);
        this.namespace = namespace;
    }

    /** Returns null when the context is null or the namespace is invalid (ARGUMENT). */
    public static CredentialStore open(Context context, String namespace) {
        return context != null && validNamespace(namespace) ? new CredentialStore(context, namespace) : null;
    }

    public static String statusName(int status) {
        switch (status) {
            case OK: return "OK";
            case NOT_FOUND: return "NOT_FOUND";
            case UNAVAILABLE: return "UNAVAILABLE";
            case ARGUMENT: return "ARGUMENT";
            case IO: return "IO";
            default: return "UNKNOWN";
        }
    }

    public static boolean validNamespace(String value) {
        if (value == null || value.isEmpty() || value.length() > NAMESPACE_MAX || !alnum(value.charAt(0))) return false;
        for (int i = 0; i < value.length(); ++i) {
            char c = value.charAt(i);
            if (!alnum(c) && c != '.' && c != '-') return false;
        }
        return true;
    }

    public static boolean validAccountId(String value) {
        if (value == null || value.length() != 36) return false;
        for (int i = 0; i < 36; ++i) {
            char c = value.charAt(i);
            if (i == 8 || i == 13 || i == 18 || i == 23) {
                if (c != '-') return false;
            } else if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
                return false;
            }
        }
        return true;
    }

    private static boolean alnum(char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }

    /** Creates or exactly replaces the record. The caller keeps ownership of secret. */
    public int put(String accountId, byte[] secret) {
        return put(accountId, secret, secret == null ? 0 : secret.length);
    }

    public int put(String accountId, byte[] secret, int length) {
        if (!validAccountId(accountId) || secret == null || length <= 0 || length > SECRET_MAX || length > secret.length)
            return ARGUMENT;
        synchronized (LOCK) {
            byte[] record = null;
            try {
                SecretKey key = key(true);
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, key);
                cipher.updateAAD(associatedData(accountId));
                byte[] sealed = cipher.doFinal(secret, 0, length);
                byte[] iv = cipher.getIV();
                if (iv == null || iv.length != IV_BYTES) return IO;
                record = new byte[MAGIC.length + IV_BYTES + sealed.length];
                System.arraycopy(MAGIC, 0, record, 0, MAGIC.length);
                System.arraycopy(iv, 0, record, MAGIC.length, IV_BYTES);
                System.arraycopy(sealed, 0, record, MAGIC.length + IV_BYTES, sealed.length);
                return publish(accountId, record);
            } catch (KeyStoreUnavailable e) {
                return UNAVAILABLE;
            } catch (ProviderException e) {
                return UNAVAILABLE;
            } catch (GeneralSecurityException e) {
                return IO;
            } finally {
                if (record != null) Arrays.fill(record, (byte) 0);
            }
        }
    }

    /**
     * Copies the record into buffer and writes its length to length[0]. When the
     * buffer is too small returns ARGUMENT, writes the needed length and leaves the
     * buffer untouched. length[0] is 0 for every other non-OK result.
     */
    public int get(String accountId, byte[] buffer, int[] length) {
        if (length == null || length.length < 1) return ARGUMENT;
        length[0] = 0;
        if (!validAccountId(accountId) || buffer == null) return ARGUMENT;
        synchronized (LOCK) {
            File file = recordFile(accountId);
            if (!file.isFile()) return NOT_FOUND;
            byte[] record = null, plain = null;
            try {
                record = read(file);
                if (record == null || record.length <= MAGIC.length + IV_BYTES
                        || !Arrays.equals(Arrays.copyOf(record, MAGIC.length), MAGIC)) return IO;
                SecretKey key = key(false);
                if (key == null) return IO; // ciphertext without its key cannot be recovered
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, record, MAGIC.length, IV_BYTES));
                cipher.updateAAD(associatedData(accountId));
                int offset = MAGIC.length + IV_BYTES;
                plain = cipher.doFinal(record, offset, record.length - offset);
                if (plain.length == 0 || plain.length > SECRET_MAX) return IO;
                length[0] = plain.length;
                if (plain.length > buffer.length) return ARGUMENT;
                System.arraycopy(plain, 0, buffer, 0, plain.length);
                return OK;
            } catch (KeyStoreUnavailable e) {
                return UNAVAILABLE;
            } catch (ProviderException e) {
                return UNAVAILABLE;
            } catch (GeneralSecurityException | IOException e) {
                return IO; // includes tampering, a swapped record and an invalidated key
            } finally {
                if (record != null) Arrays.fill(record, (byte) 0);
                if (plain != null) Arrays.fill(plain, (byte) 0);
            }
        }
    }

    /** Removes the record; NOT_FOUND when already absent. The namespace key is kept. */
    public int delete(String accountId) {
        if (!validAccountId(accountId)) return ARGUMENT;
        synchronized (LOCK) {
            File file = recordFile(accountId);
            if (!file.exists()) return NOT_FOUND;
            return file.delete() ? OK : IO;
        }
    }

    // Bridge used by the C ABI on Android (src/android.c).
    static int bridgePut(Context context, String namespace, String accountId, byte[] secret) {
        CredentialStore store = open(context, namespace);
        return store == null ? ARGUMENT : store.put(accountId, secret);
    }

    static int bridgeGet(Context context, String namespace, String accountId, byte[] buffer, int[] length) {
        CredentialStore store = open(context, namespace);
        return store == null ? ARGUMENT : store.get(accountId, buffer, length);
    }

    static int bridgeDelete(Context context, String namespace, String accountId) {
        CredentialStore store = open(context, namespace);
        return store == null ? ARGUMENT : store.delete(accountId);
    }

    private static final class KeyStoreUnavailable extends Exception {
        KeyStoreUnavailable(Throwable cause) { super(cause); }
    }

    private String alias() { return "EXReaderCredentials/" + namespace; }

    private byte[] associatedData(String accountId) {
        return ("exreader-credentials-v1\0" + namespace + "\0" + accountId).getBytes(StandardCharsets.US_ASCII);
    }

    private SecretKey key(boolean create) throws KeyStoreUnavailable, GeneralSecurityException {
        KeyStore store;
        try {
            store = KeyStore.getInstance(KEYSTORE);
            store.load(null);
        } catch (GeneralSecurityException | IOException e) {
            throw new KeyStoreUnavailable(e);
        }
        Key existing = store.getKey(alias(), null);
        if (existing instanceof SecretKey) return (SecretKey) existing;
        if (!create) return null;
        KeyGenerator generator;
        try {
            generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        } catch (GeneralSecurityException e) {
            throw new KeyStoreUnavailable(e);
        }
        generator.init(new KeyGenParameterSpec.Builder(alias(),
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build());
        return generator.generateKey();
    }

    private File recordFile(String accountId) { return new File(directory, accountId + ".rec"); }

    private int publish(String accountId, byte[] record) {
        if (!directory.isDirectory() && !directory.mkdirs() && !directory.isDirectory()) return IO;
        File temporary = new File(directory, accountId + ".tmp");
        try (FileOutputStream out = new FileOutputStream(temporary)) {
            out.write(record);
            out.getFD().sync();
        } catch (IOException e) {
            temporary.delete();
            return IO;
        }
        if (!temporary.renameTo(recordFile(accountId))) {
            temporary.delete();
            return IO;
        }
        return OK;
    }

    private static byte[] read(File file) throws IOException {
        long size = file.length();
        if (size <= 0 || size > SECRET_MAX + 64) return null;
        byte[] data = new byte[(int) size];
        try (FileInputStream in = new FileInputStream(file)) {
            int offset = 0;
            while (offset < data.length) {
                int n = in.read(data, offset, data.length - offset);
                if (n < 0) return null;
                offset += n;
            }
            if (in.read() != -1) return null;
        }
        return data;
    }
}
