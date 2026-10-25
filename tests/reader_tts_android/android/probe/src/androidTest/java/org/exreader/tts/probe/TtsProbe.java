// SPDX-License-Identifier: MIT
package org.exreader.tts.probe;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.ResolveInfo;
import android.os.Build;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;

import org.exreader.tts.Backend;
import org.exreader.tts.Chunker;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Real-device acceptance probe for the Android TextToSpeech backend.
 *
 * <p>One instrumentation run covers exactly one engine state: {@code mode=engine}
 * when a real engine is installed and {@code mode=none} after this workflow
 * removed every engine from the device. Every named case compares the observed
 * behaviour with that expectation, so neither run can pass by tolerating the
 * other state.
 */
public final class TtsProbe extends Instrumentation {
    private static final String AUDIO_PATH = "audio/tts-sample.wav";

    private interface Check {
        String call() throws Exception;
    }

    private static final class Skip extends RuntimeException {
        Skip(String message) { super(message); }
    }

    private Bundle args;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        args = arguments;
        start();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            String mode = text("mode", "engine");
            boolean engineExpected = "engine".equals(mode);
            JSONObject report = new JSONObject();
            report.put("source_sha", text("source_sha", ""))
                  .put("run_id", text("run_id", ""))
                  .put("attempt", text("attempt", ""))
                  .put("mode", mode)
                  .put("engine_expected", engineExpected)
                  .put("api", Build.VERSION.SDK_INT)
                  .put("abi", Build.SUPPORTED_ABIS[0])
                  .put("fingerprint", Build.FINGERPRINT);
            report.put("engine_packages", engineInventory());
            Context context = getTargetContext();
            NativeTts.setContext(context);
            NativeTts.setMode(engineExpected ? 1 : 0);
            JSONArray cases = new JSONArray();
            int count = NativeTts.caseCount();
            if (count < 46) throw new AssertionError("case table shrank to " + count);
            for (int id = 0; id < count; id++) cases.put(runNative(id));
            cases.put(check("chunker_boundaries_and_surrogates", this::chunkerCheck));
            cases.put(check("rotation_during_speaking", () -> rotationCheck(engineExpected)));
            cases.put(check("engine_identity_recorded", () -> identityCheck(report, engineExpected)));
            cases.put(check("synthesize_to_file_audio", () -> audioCheck(report, engineExpected)));
            cases.put(check("voice_names_match_engine", () -> voiceNamesCheck(engineExpected)));
            cases.put(check("voice_selection_returns_to_default", () -> voiceSelectionCheck(engineExpected)));
            report.put("cases", cases);
            report.put("case_count", cases.length());
            JSONArray failed = new JSONArray();
            int skipped = 0;
            for (int index = 0; index < cases.length(); index++) {
                JSONObject row = cases.getJSONObject(index);
                if ("fail".equals(row.getString("result"))) failed.put(row.getString("name"));
                if ("skip".equals(row.getString("result"))) skipped++;
            }
            boolean enginesPresent = report.getJSONArray("engine_packages").length() > 0;
            report.put("skipped_cases", skipped);
            report.put("failed_cases", failed);
            report.put("engine_packages_present", enginesPresent);
            report.put("mode_consistent", engineExpected == enginesPresent);
            report.put("pass", failed.length() == 0 && engineExpected == enginesPresent);
            Files.write(new File(context.getFilesDir(), "device-report.json").toPath(),
                report.toString(2).getBytes(StandardCharsets.UTF_8));
            result.putString("stream", "EXR_TTS_ANDROID_PROBE_RECORDED\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            result.putString("shortMsg", "TTS_PROBE_FAILED " + error);
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private String text(String key, String fallback) {
        if (args == null) return fallback;
        String value = args.getString(key);
        return value == null ? fallback : value;
    }

    private JSONArray engineInventory() {
        JSONArray engines = new JSONArray();
        Intent intent = new Intent(TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE);
        List<ResolveInfo> services = getTargetContext().getPackageManager().queryIntentServices(intent, 0);
        if (services == null) return engines;
        for (ResolveInfo info : services) {
            if (info.serviceInfo == null || info.serviceInfo.packageName == null) continue;
            boolean known = false;
            for (int index = 0; index < engines.length(); index++) {
                if (info.serviceInfo.packageName.equals(engines.optString(index))) known = true;
            }
            if (!known) engines.put(info.serviceInfo.packageName);
        }
        return engines;
    }

    private JSONObject runNative(int id) throws Exception {
        JSONObject row = new JSONObject();
        String name = NativeTts.caseName(id);
        int outcome = 1;
        try {
            outcome = NativeTts.runCase(id);
        } catch (Throwable error) {
            row.put("thrown", String.valueOf(error));
        }
        String detail = NativeTts.caseDetail();
        row.put("id", id)
           .put("name", name)
           .put("source", "native")
           .put("result", outcome == 0 ? "pass" : outcome == 2 ? "skip" : "fail")
           .put("detail", detail == null ? "" : detail);
        return row;
    }

    private JSONObject check(String name, Check body) throws Exception {
        JSONObject row = new JSONObject();
        row.put("name", name).put("source", "java");
        try {
            String detail = body.call();
            row.put("result", "pass").put("detail", detail == null ? "" : detail);
        } catch (Skip skip) {
            row.put("result", "skip").put("detail", skip.getMessage());
        } catch (Throwable error) {
            row.put("result", "fail").put("detail", String.valueOf(error));
        }
        return row;
    }

    private Backend openBackend(long cookie, long timeoutMs) throws Exception {
        Backend backend = Backend.create(getTargetContext(), cookie);
        if (backend == null) throw new AssertionError("Backend.create returned null");
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (!backend.initSettled() && System.currentTimeMillis() < deadline) Thread.sleep(25);
        if (!backend.initSettled()) throw new AssertionError("engine init did not settle");
        return backend;
    }

    private String chunkerCheck() {
        String text = "alpha beta\ngamma \u4e2d\u6587 \ud83d\ude00\ud83d\ude00 delta";
        List<String> chunks = Chunker.chunk(text, 7);
        StringBuilder joined = new StringBuilder();
        for (String chunk : chunks) {
            if (chunk.isEmpty()) throw new AssertionError("empty chunk");
            if (chunk.length() > 7) throw new AssertionError("chunk above the limit");
            if (Character.isLowSurrogate(chunk.charAt(0))) throw new AssertionError("chunk starts inside a pair");
            if (Character.isHighSurrogate(chunk.charAt(chunk.length() - 1))) {
                throw new AssertionError("chunk ends inside a pair");
            }
            joined.append(chunk);
        }
        if (!joined.toString().equals(text)) throw new AssertionError("chunking lost or reordered characters");
        List<String> wide = Chunker.chunk("\ud83d\ude00x", 1);
        if (wide.size() != 2 || !"\ud83d\ude00".equals(wide.get(0)) || !"x".equals(wide.get(1))) {
            throw new AssertionError("a code point smaller than the limit was split: " + wide);
        }
        if (!Chunker.chunk("", 4).isEmpty()) throw new AssertionError("empty text produced chunks");
        return "chunks=" + chunks.size() + " astral=" + wide.size();
    }

    /**
     * Rotates a real Activity while a long request is speaking and requires the
     * request to survive with exactly one terminal event.
     */
    private String rotationCheck(boolean engineExpected) throws Exception {
        if (!engineExpected) throw new Skip("no engine installed");
        int begin = NativeTts.rotationBegin();
        if (begin == 2) throw new Skip("the engine could not start a rotation request");
        if (begin != 0) throw new AssertionError("the rotation request was refused: " + begin);
        Context context = getTargetContext();
        int before = SessionActivity.creations();
        Intent intent = new Intent(context, SessionActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
        long deadline = System.currentTimeMillis() + 15000;
        while (SessionActivity.creations() == before && System.currentTimeMillis() < deadline) {
            Thread.sleep(50);
        }
        if (SessionActivity.creations() == before) {
            throw new AssertionError("the probe activity did not start");
        }
        SessionActivity first = SessionActivity.current();
        if (first == null) throw new AssertionError("no activity instance to rotate");
        int creations = SessionActivity.creations();
        runOnMainSync(() -> first.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
        deadline = System.currentTimeMillis() + 20000;
        while (SessionActivity.creations() == creations && System.currentTimeMillis() < deadline) {
            Thread.sleep(50);
        }
        boolean rotated = SessionActivity.creations() > creations;
        SessionActivity latest = SessionActivity.current();
        if (latest != null) {
            runOnMainSync(() -> {
                latest.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
                latest.finish();
            });
        }
        int finish = NativeTts.rotationFinish();
        String detail = NativeTts.caseDetail();
        if (!rotated) throw new AssertionError("the activity was not recreated by the rotation");
        if (finish != 0) throw new AssertionError("the request did not survive the rotation: " + finish);
        return "recreated=" + (SessionActivity.creations() - creations) + " " + (detail == null ? "" : detail);
    }

    private String identityCheck(JSONObject report, boolean engineExpected) throws Exception {
        Backend backend = openBackend(1L << 41, 30000);
        try {
            boolean ready = backend.isReady();
            report.put("backend_ready", ready)
                  .put("engine_package", backend.enginePackage() == null ? "" : backend.enginePackage())
                  .put("default_voice", backend.defaultVoiceId() == null ? "" : backend.defaultVoiceId())
                  .put("init_result", backend.initResult())
                  .put("max_input_length", Backend.maxInputLength());
            if (engineExpected) {
                if (!ready) throw new AssertionError("an installed engine did not become ready, init=" + backend.initResult());
                if (backend.enginePackage() == null || backend.enginePackage().isEmpty()) {
                    throw new AssertionError("no engine package was selected");
                }
            } else {
                if (ready) throw new AssertionError("a removed engine still became ready");
                if (backend.initResult() == TextToSpeech.SUCCESS) {
                    throw new AssertionError("removed engine reported SUCCESS");
                }
            }
            return "ready=" + ready + " engine=" + backend.enginePackage() + " init=" + backend.initResult();
        } finally {
            backend.close();
        }
    }

    private String audioCheck(JSONObject report, boolean engineExpected) throws Exception {
        if (!engineExpected) throw new Skip("no engine installed");
        Backend backend = openBackend(1L << 42, 30000);
        try {
            if (!backend.isReady()) throw new AssertionError("engine not ready for synthesizeToFile");
            File output = new File(getTargetContext().getFilesDir(), AUDIO_PATH);
            File parent = output.getParentFile();
            if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
                throw new AssertionError("audio directory could not be created");
            }
            if (output.exists() && !output.delete()) throw new AssertionError("stale audio file kept");
            String voice = backend.localVoiceId();
            byte[] text = "Reader audio acceptance sample.".getBytes(StandardCharsets.UTF_8);
            int outcome = backend.synthesizeToFile(text, voice, 1.0, output.getAbsolutePath(), 60000);
            if (outcome != 0) throw new AssertionError("synthesizeToFile returned " + outcome);
            if (!output.isFile()) throw new AssertionError("no audio file was written");
            long bytes = output.length();
            if (bytes <= 44) throw new AssertionError("audio file is " + bytes + " bytes");
            String header = header(output);
            JSONObject audio = new JSONObject();
            audio.put("path", AUDIO_PATH)
                 .put("bytes", bytes)
                 .put("sha256", sha256(output))
                 .put("header", header)
                 .put("engine", backend.enginePackage() == null ? "" : backend.enginePackage())
                 .put("voice", voice == null ? "" : voice)
                 .put("default_voice", backend.defaultVoiceId() == null ? "" : backend.defaultVoiceId());
            report.put("audio", audio);
            return "bytes=" + bytes + " header=" + header;
        } finally {
            backend.close();
        }
    }

    /** Opens one direct engine binding so a check can read the engine's own voice objects. */
    private TextToSpeech openEngine() throws Exception {
        final CountDownLatch settled = new CountDownLatch(1);
        final int[] status = new int[1];
        TextToSpeech engine = new TextToSpeech(getTargetContext(), value -> {
            status[0] = value;
            settled.countDown();
        });
        if (!settled.await(30, TimeUnit.SECONDS)) {
            engine.shutdown();
            throw new AssertionError("a direct engine binding did not settle");
        }
        if (status[0] != TextToSpeech.SUCCESS) {
            engine.shutdown();
            throw new AssertionError("a direct engine binding failed with " + status[0]);
        }
        return engine;
    }

    private static Map<String, Voice> voiceMap(TextToSpeech engine) {
        Map<String, Voice> map = new HashMap<>();
        Set<Voice> voices = engine.getVoices();
        if (voices != null) {
            for (Voice voice : voices) map.put(voice.getName(), voice);
        }
        return map;
    }

    private File audioFile(String name) {
        File output = new File(getTargetContext().getFilesDir(), "audio/" + name);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new AssertionError("audio directory could not be created");
        }
        if (output.exists() && !output.delete()) throw new AssertionError("stale audio file kept: " + name);
        return output;
    }

    /**
     * The C ABI voice list must carry the engine's own id, display name and
     * language tag for every installed voice: a picker cannot show an id.
     */
    private String voiceNamesCheck(boolean engineExpected) throws Exception {
        if (!engineExpected) throw new Skip("no engine installed");
        String lines = NativeTts.voiceLines();
        if (lines == null || lines.isEmpty()) {
            throw new AssertionError("the installed C ABI listed no voices");
        }
        TextToSpeech engine = openEngine();
        try {
            Map<String, Voice> voices = voiceMap(engine);
            if (voices.isEmpty()) throw new Skip("the engine lists no voice objects");
            int compared = 0;
            for (String line : lines.split("\n")) {
                if (line.isEmpty()) continue;
                String[] fields = line.split("\t", -1);
                if (fields.length != 3) throw new AssertionError("malformed C voice line: " + line);
                Voice voice = voices.get(fields[0]);
                if (voice == null) {
                    throw new AssertionError("the C list reports a voice the engine does not have: " + fields[0]);
                }
                String name = voice.getLocalizedName();
                if (name != null && !name.isEmpty() && !name.equals(fields[1])) {
                    throw new AssertionError("voice " + fields[0] + " reports name '" + fields[1]
                        + "' but the engine localized name is '" + name + "'");
                }
                String tag = voice.getLocale() == null ? "und" : voice.getLocale().toLanguageTag();
                if (!tag.equals(fields[2])) {
                    throw new AssertionError("voice " + fields[0] + " reports language '" + fields[2]
                        + "' but the engine tag is '" + tag + "'");
                }
                compared++;
            }
            if (compared == 0) throw new AssertionError("the C voice list was empty");
            return "voices=" + compared;
        } finally {
            engine.shutdown();
        }
    }

    /**
     * An explicit voice must stick for its own request, and a request with an
     * empty voice id must return to the engine default instead of inheriting it.
     */
    private String voiceSelectionCheck(boolean engineExpected) throws Exception {
        if (!engineExpected) throw new Skip("no engine installed");
        Voice fallback = null;
        Voice chosen = null;
        String defaultName = null;
        TextToSpeech engine = openEngine();
        try {
            fallback = engine.getDefaultVoice();
            if (fallback == null) throw new Skip("the engine exposes no default voice");
            defaultName = fallback.getName();
            List<Voice> sorted = new ArrayList<>();
            Set<Voice> all = engine.getVoices();
            if (all != null) sorted.addAll(all);
            sorted.sort((left, right) -> left.getName().compareTo(right.getName()));
            String language = fallback.getLocale() == null ? "und" : fallback.getLocale().getLanguage();
            for (Voice voice : sorted) {
                if (voice.getName().equals(defaultName)) continue;
                if (voice.isNetworkConnectionRequired()) continue;
                if (voice.getLocale() == null || !language.equals(voice.getLocale().getLanguage())) continue;
                chosen = voice;
                break;
            }
        } finally {
            engine.shutdown();
        }
        if (chosen == null) throw new Skip("the engine offers no second installed voice in the default language");
        Backend backend = openBackend(1L << 43, 30000);
        try {
            if (!backend.isReady()) throw new AssertionError("engine not ready for the voice-selection case");
            String active = backend.activeVoiceId();
            if (active != null) throw new AssertionError("a fresh handle already selected '" + active + "'");
            File explicit = audioFile("voice-explicit.wav");
            File restored = audioFile("voice-default.wav");
            byte[] text = "Voice selection sample.".getBytes(StandardCharsets.UTF_8);
            int outcome = backend.synthesizeToFile(text, chosen.getName(), 1.0,
                explicit.getAbsolutePath(), 60000);
            if (outcome != 0) throw new Skip("the engine refused the explicit voice (result " + outcome + ")");
            if (!chosen.getName().equals(backend.activeVoiceId())) {
                throw new AssertionError("the explicit voice did not stick: " + backend.activeVoiceId());
            }
            outcome = backend.synthesizeToFile(text, null, 1.0, restored.getAbsolutePath(), 60000);
            if (outcome != 0) throw new AssertionError("rendering with the default voice returned " + outcome);
            active = backend.activeVoiceId();
            if (!defaultName.equals(active)) {
                throw new AssertionError("an empty voice id kept '" + active + "' instead of the default '"
                    + defaultName + "'");
            }
            if (explicit.length() <= 44 || restored.length() <= 44) {
                throw new AssertionError("a voice-selection render is empty");
            }
            return "default=" + defaultName + " explicit=" + chosen.getName()
                + " sizes=" + explicit.length() + "/" + restored.length();
        } finally {
            backend.close();
        }
    }

    private static String header(File file) throws Exception {
        byte[] head = new byte[12];
        try (InputStream input = new FileInputStream(file)) {
            int read = 0;
            while (read < head.length) {
                int step = input.read(head, read, head.length - read);
                if (step < 0) break;
                read += step;
            }
            if (read < head.length) throw new AssertionError("audio header is truncated");
        }
        return new String(head, 0, 4, StandardCharsets.ISO_8859_1) + ":"
             + new String(head, 8, 4, StandardCharsets.ISO_8859_1);
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[65536];
            int read;
            while ((read = input.read(buffer)) > 0) digest.update(buffer, 0, read);
        }
        StringBuilder text = new StringBuilder();
        for (byte value : digest.digest()) text.append(String.format("%02x", value));
        return text.toString();
    }
}
