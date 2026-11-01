// SPDX-License-Identifier: MIT
package org.exreader.f09tts;

import android.media.AudioFormat;
import android.speech.tts.SynthesisCallback;
import android.speech.tts.SynthesisRequest;
import android.speech.tts.TextToSpeech;
import android.speech.tts.TextToSpeechService;
import android.util.Log;

/** Logs each utterance under tag F09TTS and returns a short silence, so the screen
 *  reader proceeds as with a real voice while its exact words reach logcat. */
public final class CaptureService extends TextToSpeechService {
    private String[] language = {"eng", "USA", ""};

    @Override protected int onIsLanguageAvailable(String lang, String country, String variant) {
        return TextToSpeech.LANG_COUNTRY_AVAILABLE;
    }

    @Override protected String[] onGetLanguage() {
        return language;
    }

    @Override protected int onLoadLanguage(String lang, String country, String variant) {
        language = new String[]{lang == null ? "" : lang, country == null ? "" : country, variant == null ? "" : variant};
        return TextToSpeech.LANG_COUNTRY_AVAILABLE;
    }

    @Override protected void onStop() {
    }

    @Override protected void onSynthesizeText(SynthesisRequest request, SynthesisCallback callback) {
        CharSequence text = request.getCharSequenceText();
        Log.i("F09TTS", "SPEAK " + (text == null ? request.getText() : text.toString()));
        callback.start(16000, AudioFormat.ENCODING_PCM_16BIT, 1);
        byte[] silence = new byte[3200];
        callback.audioAvailable(silence, 0, silence.length);
        callback.done();
    }
}
