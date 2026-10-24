# The C ABI (src/android.c) resolves these bridge methods by name over JNI.
-keep class org.exreader.credentials.CredentialStore {
    static int bridgePut(android.content.Context, java.lang.String, java.lang.String, byte[]);
    static int bridgeGet(android.content.Context, java.lang.String, java.lang.String, byte[], int[]);
    static int bridgeDelete(android.content.Context, java.lang.String, java.lang.String);
}
