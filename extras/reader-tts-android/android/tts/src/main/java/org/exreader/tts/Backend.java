// SPDX-License-Identifier: MIT
package org.exreader.tts;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Android system {@link TextToSpeech} binding used by the reader TTS C ABI.
 *
 * <p>The native library calls the static entry points with the handle cookie it
 * assigned. Engine creation, the init handshake and shutdown run on a private
 * {@link HandlerThread}; the framework delivers {@code OnInitListener} on the
 * process main thread and every {@link UtteranceProgressListener} callback on
 * an engine binder thread. The request entry points ({@code speak},
 * {@code stop}, {@code voices}, {@code synthesizeToFile}) are synchronous
 * binder calls made on the caller's thread and never need that thread to have
 * a {@link android.os.Looper}. Every callback is converted into a bounded
 * native event and never calls back into the host.
 *
 * <p>The host must load the shared library that implements
 * {@code reader_tts_android_deliver} and exposes {@code nativeEvent} before it
 * creates a state, for example from its own JNI glue:
 *
 * <pre>
 * System.loadLibrary("exreader_tts_host");
 * reader_tts_android_initialize(env, context);   // C side, from the same library
 * </pre>
 *
 * <p>This class is not a second state machine: it holds no request state of its
 * own beyond the text needed to translate UTF-16 offsets and the audio-file
 * waiters. Accepting, ordering, limits and the single-active-request rule live
 * in {@code reader_tts_android.c}.
 */
public final class Backend {
    static final int EVENT_INIT_OK = 0;
    static final int EVENT_INIT_FAILED = 1;
    static final int EVENT_STARTED = 2;
    static final int EVENT_RANGE = 3;
    static final int EVENT_FINISHED = 4;
    static final int EVENT_STOPPED = 5;
    static final int EVENT_FAILED = 6;
    static final int EVENT_RELEASED = 7;

    static final int RESULT_OK = 0;
    static final int RESULT_UNKNOWN_VOICE = 1;
    static final int RESULT_ENGINE_REJECTED = 2;
    static final int RESULT_NOT_READY = 3;
    static final int RESULT_TOO_LONG = 4;
    static final int RESULT_INTERNAL = 5;
    static final int RESULT_TIMEOUT = 6;

    private static final int MAX_VOICES = 1024;
    private static final int MAX_FIELD_BYTES = 255;
    private static final String AUDIO_PREFIX = "audio-";
    private static final Map<Long, Backend> INSTANCES = new HashMap<>();

    private static native void nativeEvent(long cookie, int kind, String utteranceId, int start, int end);

    private final long cookie;
    private final Context context;
    private final HandlerThread thread;
    private final Handler handler;
    private final Object lock = new Object();
    private final Map<String, String> texts = new HashMap<>();
    private final Map<String, CountDownLatch> audio = new HashMap<>();

    private volatile TextToSpeech engine;
    private volatile int initStatus = TextToSpeech.ERROR;
    private volatile boolean initSettled;
    private volatile boolean closing;
    /** True once this handle selected an explicit voice on the shared engine state. */
    private volatile boolean voicePinned;
    private long audioSequence;

    private final UtteranceProgressListener listener = new UtteranceProgressListener() {
        @Override public void onStart(String utteranceId) {
            deliver(EVENT_STARTED, utteranceId, 0, 0);
        }
        @Override public void onDone(String utteranceId) {
            finishUtterance(EVENT_FINISHED, utteranceId, 0, 0);
        }
        @Override public void onStop(String utteranceId, boolean interrupted) {
            finishUtterance(EVENT_STOPPED, utteranceId, 0, 0);
        }
        @Override public void onError(String utteranceId) {
            finishUtterance(EVENT_FAILED, utteranceId, TextToSpeech.ERROR, 0);
        }
        @Override public void onError(String utteranceId, int errorCode) {
            finishUtterance(EVENT_FAILED, utteranceId, errorCode, 0);
        }
        @Override public void onRangeStart(String utteranceId, int start, int end, int frame) {
            int[] range = byteRange(utteranceId, start, end);
            if (range != null) deliver(EVENT_RANGE, utteranceId, range[0], range[1]);
        }
    };

    private Backend(Context context, long cookie) {
        this.cookie = cookie;
        Context application = context.getApplicationContext();
        this.context = application != null ? application : context;
        this.thread = new HandlerThread("exreader-tts");
        this.thread.start();
        this.handler = new Handler(thread.getLooper());
        handler.post(this::startEngine);
    }

    /** Creates one engine binding; the result of construction is not readiness. */
    public static Backend create(Context context, long cookie) {
        if (context == null) return null;
        Backend backend = new Backend(context, cookie);
        synchronized (INSTANCES) {
            INSTANCES.put(cookie, backend);
        }
        return backend;
    }

    private static Backend find(long cookie) {
        synchronized (INSTANCES) {
            return INSTANCES.get(cookie);
        }
    }

    static int speak(long cookie, long requestId, byte[] text, byte[] voice, double rate) {
        Backend backend = find(cookie);
        if (backend == null || text == null) return RESULT_NOT_READY;
        String voiceId = voice == null ? null : new String(voice, StandardCharsets.UTF_8);
        return backend.speak(requestId, new String(text, StandardCharsets.UTF_8), voiceId, rate);
    }

    static int stop(long cookie) {
        Backend backend = find(cookie);
        if (backend == null) return RESULT_NOT_READY;
        TextToSpeech current = backend.engine;
        if (current == null) return RESULT_NOT_READY;
        try {
            return current.stop() == TextToSpeech.SUCCESS ? RESULT_OK : RESULT_ENGINE_REJECTED;
        } catch (RuntimeException error) {
            return RESULT_ENGINE_REJECTED;
        }
    }

    static byte[] voices(long cookie) {
        Backend backend = find(cookie);
        return backend == null ? null : backend.voices();
    }

    static int release(long cookie) {
        Backend backend = find(cookie);
        if (backend == null) return RESULT_NOT_READY;
        return backend.release();
    }

    private void startEngine() {
        try {
            engine = new TextToSpeech(context, this::onInit);
        } catch (RuntimeException error) {
            initStatus = TextToSpeech.ERROR;
            initSettled = true;
            nativeEvent(cookie, EVENT_INIT_FAILED, null, TextToSpeech.ERROR, 0);
            return;
        }
        TextToSpeech current = engine;
        if (current != null && initStatus == TextToSpeech.SUCCESS) {
            current.setOnUtteranceProgressListener(listener);
        }
    }

    private void onInit(int status) {
        initStatus = status;
        initSettled = true;
        if (status == TextToSpeech.SUCCESS) {
            TextToSpeech current = engine;
            if (current != null) current.setOnUtteranceProgressListener(listener);
            nativeEvent(cookie, EVENT_INIT_OK, null, 0, 0);
        } else {
            nativeEvent(cookie, EVENT_INIT_FAILED, null, status, 0);
        }
    }

    private int speak(long requestId, String text, String voiceId, double rate) {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS || closing) return RESULT_NOT_READY;
        if (text.length() > TextToSpeech.getMaxSpeechInputLength()) return RESULT_TOO_LONG;
        int selection = selectVoice(current, voiceId);
        if (selection != RESULT_OK) return selection;
        try {
            current.setSpeechRate((float) rate);
        } catch (RuntimeException error) {
            return RESULT_ENGINE_REJECTED;
        }
        /* The C ABI accepts the whole uint64 range, so a request id at or above
           2^63 arrives here as a negative Java long. The utterance id is the
           unsigned decimal form of the same bits; the native side parses it
           back into the original uint64 and nothing is lost. */
        String utterance = Long.toUnsignedString(requestId);
        synchronized (lock) {
            /* Only the active request needs its text for offset conversion, so
               a request whose terminal callback never arrives cannot leave the
               text resident forever. */
            texts.clear();
            texts.put(utterance, text);
        }
        int outcome;
        try {
            outcome = current.speak(text, TextToSpeech.QUEUE_FLUSH, new Bundle(), utterance);
        } catch (RuntimeException error) {
            synchronized (lock) {
                texts.remove(utterance);
            }
            return RESULT_ENGINE_REJECTED;
        }
        if (outcome != TextToSpeech.SUCCESS) {
            synchronized (lock) {
                texts.remove(utterance);
            }
            return RESULT_ENGINE_REJECTED;
        }
        return RESULT_OK;
    }

    private byte[] voices() {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS || closing) return null;
        Set<Voice> available;
        try {
            available = current.getVoices();
        } catch (RuntimeException error) {
            return null;
        }
        List<Voice> sorted = new ArrayList<>();
        if (available != null) sorted.addAll(available);
        sorted.sort((left, right) -> left.getName().compareTo(right.getName()));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int written = 0;
        for (Voice voice : sorted) {
            if (written >= MAX_VOICES) return null;
            String id = voice.getName();
            if (id == null || id.isEmpty()) continue;
            /* id selects the voice, name is what a picker shows, language is a
               BCP 47 tag. The engine id is not a display name, and
               android.speech.tts.Voice exposes no display name of its own, so
               the localized locale name is the human readable label. */
            String name = voice.getLocale() == null ? id : voice.getLocale().getDisplayName();
            if (name == null || name.isEmpty()) name = id;
            String language = voice.getLocale() == null ? "und" : voice.getLocale().toLanguageTag();
            if (language.isEmpty()) language = "und";
            if (!writeField(out, id) || !writeField(out, name) || !writeField(out, language)) return null;
            written++;
        }
        return out.toByteArray();
    }

    private static boolean writeField(ByteArrayOutputStream out, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0 || bytes.length > MAX_FIELD_BYTES) return false;
        out.write(bytes, 0, bytes.length);
        out.write(0);
        return true;
    }

    /**
     * Selects the voice of the next request. An empty id returns to the system
     * default voice, so a request never inherits the voice of an earlier one.
     */
    private int selectVoice(TextToSpeech engine, String voiceId) {
        try {
            if (voiceId != null && !voiceId.isEmpty()) {
                Voice voice = findVoice(engine, voiceId);
                if (voice == null) return RESULT_UNKNOWN_VOICE;
                if (engine.setVoice(voice) != TextToSpeech.SUCCESS) return RESULT_ENGINE_REJECTED;
                voicePinned = true;
                return RESULT_OK;
            }
            if (voicePinned) {
                Voice fallback = engine.getDefaultVoice();
                if (fallback != null && engine.setVoice(fallback) == TextToSpeech.SUCCESS) {
                    voicePinned = false;
                }
            }
            return RESULT_OK;
        } catch (RuntimeException error) {
            return RESULT_ENGINE_REJECTED;
        }
    }

    private static Voice findVoice(TextToSpeech engine, String voiceId) {
        Set<Voice> available = engine.getVoices();
        if (available == null) return null;
        for (Voice voice : available) {
            if (voiceId.equals(voice.getName())) return voice;
        }
        return null;
    }

    private int release() {
        if (closing) return RESULT_OK;
        closing = true;
        handler.post(() -> {
            TextToSpeech current = engine;
            try {
                if (current != null) {
                    current.stop();
                    current.shutdown();
                }
            } catch (RuntimeException error) {
                /* A failed shutdown must not keep the native state open. */
            } finally {
                engine = null;
                synchronized (lock) {
                    texts.clear();
                    audio.clear();
                }
                synchronized (INSTANCES) {
                    INSTANCES.remove(cookie);
                }
                nativeEvent(cookie, EVENT_RELEASED, null, 0, 0);
                thread.quitSafely();
            }
        });
        return RESULT_OK;
    }

    private void deliver(int kind, String utteranceId, int start, int end) {
        if (utteranceId == null) return;
        if (utteranceId.startsWith(AUDIO_PREFIX)) return;
        nativeEvent(cookie, kind, utteranceId, start, end);
    }

    private void finishUtterance(int kind, String utteranceId, int start, int end) {
        if (utteranceId == null) return;
        if (utteranceId.startsWith(AUDIO_PREFIX)) {
            CountDownLatch latch;
            synchronized (lock) {
                latch = audio.get(utteranceId);
            }
            if (latch != null) latch.countDown();
            return;
        }
        synchronized (lock) {
            texts.remove(utteranceId);
        }
        nativeEvent(cookie, kind, utteranceId, start, end);
    }

    /** Converts engine UTF-16 offsets into UTF-8 byte offsets of the request text. */
    private int[] byteRange(String utteranceId, int start, int end) {
        String text;
        synchronized (lock) {
            text = texts.get(utteranceId);
        }
        if (text == null || start < 0 || end < start || end > text.length()) return null;
        if (start > 0 && Character.isLowSurrogate(text.charAt(start))) return null;
        if (end < text.length() && Character.isLowSurrogate(text.charAt(end))) return null;
        return new int[] { utf8Length(text, 0, start), utf8Length(text, 0, end) };
    }

    private static int utf8Length(String text, int from, int to) {
        int bytes = 0;
        for (int index = from; index < to; index++) {
            char current = text.charAt(index);
            if (current < 0x80) {
                bytes += 1;
            } else if (current < 0x800) {
                bytes += 2;
            } else if (Character.isHighSurrogate(current)) {
                bytes += 4;
                index++;
            } else {
                bytes += 3;
            }
        }
        return bytes;
    }

    /** Engine package actually selected by the framework, or null before readiness. */
    public String enginePackage() {
        TextToSpeech current = engine;
        if (current == null) return null;
        try {
            return current.getDefaultEngine();
        } catch (RuntimeException error) {
            return null;
        }
    }

    /**
     * Identifier of the voice selected for the next request, or null while the
     * engine still uses its own default.
     */
    public String activeVoiceId() {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS) return null;
        try {
            Voice voice = current.getVoice();
            return voice == null ? null : voice.getName();
        } catch (RuntimeException error) {
            return null;
        }
    }

    /** Identifier of the current default voice, or null when no engine is ready. */
    public String defaultVoiceId() {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS) return null;
        try {
            Voice voice = current.getDefaultVoice();
            return voice == null ? null : voice.getName();
        } catch (RuntimeException error) {
            return null;
        }
    }

    /** Framework init result; {@link TextToSpeech#SUCCESS} means the engine bound. */
    public int initResult() {
        return initStatus;
    }

    public boolean isReady() {
        return initStatus == TextToSpeech.SUCCESS && engine != null && !closing;
    }

    /** True once the framework init callback has been delivered either way. */
    public boolean initSettled() {
        return initSettled;
    }

    /** Releases the engine binding; the native side observes the RELEASED event. */
    public void close() {
        release();
    }

    /**
     * Identifier of an installed local voice in the device language, or null
     * when the engine is not ready or only offers voices that need a network
     * connection. Audio-file hosts use it instead of a network voice.
     */
    public String localVoiceId() {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS) return null;
        Set<Voice> available;
        try {
            available = current.getVoices();
        } catch (RuntimeException error) {
            return null;
        }
        if (available == null) return null;
        String language = java.util.Locale.getDefault().getLanguage();
        Voice best = null;
        for (Voice voice : available) {
            if (voice.isNetworkConnectionRequired()) continue;
            if (best == null) best = voice;
            if (voice.getLocale() != null && language.equals(voice.getLocale().getLanguage())) {
                best = voice;
                break;
            }
        }
        return best == null ? null : best.getName();
    }

    /** Hard engine text ceiling in UTF-16 units, or -1 when no engine is ready. */
    public static int maxInputLength() {
        return TextToSpeech.getMaxSpeechInputLength();
    }

    /**
     * Renders a request to a real audio file (WAV on the reference engine) and
     * waits for the engine terminal callback. This is an audio-artifact helper
     * for hosts and automated checks; the C ABI speaks instead.
     */
    public int synthesizeToFile(byte[] utf8, String voiceId, double rate, String path, long timeoutMs) {
        TextToSpeech current = engine;
        if (current == null || initStatus != TextToSpeech.SUCCESS || closing) return RESULT_NOT_READY;
        String text = new String(utf8, StandardCharsets.UTF_8);
        if (text.length() > TextToSpeech.getMaxSpeechInputLength()) return RESULT_TOO_LONG;
        int selection = selectVoice(current, voiceId);
        if (selection != RESULT_OK) return selection;
        try {
            current.setSpeechRate((float) rate);
        } catch (RuntimeException error) {
            return RESULT_ENGINE_REJECTED;
        }
        String utterance;
        CountDownLatch latch = new CountDownLatch(1);
        synchronized (lock) {
            audioSequence += 1;
            utterance = AUDIO_PREFIX + audioSequence;
            audio.put(utterance, latch);
        }
        int outcome;
        try {
            outcome = current.synthesizeToFile(text, new Bundle(), new File(path), utterance);
        } catch (RuntimeException error) {
            synchronized (lock) {
                audio.remove(utterance);
            }
            return RESULT_ENGINE_REJECTED;
        }
        if (outcome != TextToSpeech.SUCCESS) {
            synchronized (lock) {
                audio.remove(utterance);
            }
            return RESULT_ENGINE_REJECTED;
        }
        boolean done;
        try {
            done = latch.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            done = false;
        }
        synchronized (lock) {
            audio.remove(utterance);
        }
        return done ? RESULT_OK : RESULT_TIMEOUT;
    }
}
