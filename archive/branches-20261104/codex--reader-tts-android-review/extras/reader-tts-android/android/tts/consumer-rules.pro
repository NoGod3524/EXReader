# The native entry point and the engine callback name are referenced from
# reader_tts_android.c; names must survive any host-side shrinking.
-keepclasseswithmembernames class org.exreader.tts.Backend { native <methods>; }
-keep class org.exreader.tts.Backend { *; }
