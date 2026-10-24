// SPDX-License-Identifier: MIT
package org.exreader.tts;

import java.util.ArrayList;
import java.util.List;

/**
 * Bounded UTF-16 chunking for the reader TTS C ABI.
 *
 * <p>{@code reader_tts_speak} refuses text above the engine ceiling with
 * {@code READER_TTS_LIMIT} instead of truncating it, so hosts chunk first and
 * give every chunk a new, strictly increasing request id. Chunks never split a
 * surrogate pair, never drop a character (their concatenation equals the
 * input) and prefer a whitespace boundary at or before the limit. The byte
 * ceiling of {@code reader_tts_config.max_utf8_bytes} still applies per chunk:
 * callers that lowered it must keep the UTF-8 size of each chunk under it.
 */
public final class Chunker {
    private Chunker() {}

    public static List<String> chunk(String text, int maxChars) {
        if (text == null) throw new IllegalArgumentException("text is required");
        if (maxChars < 1) throw new IllegalArgumentException("maxChars must be positive");
        List<String> chunks = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int end = Math.min(start + maxChars, text.length());
            if (end < text.length() && Character.isLowSurrogate(text.charAt(end))) end -= 1;
            if (end <= start) {
                end = start + (Character.isHighSurrogate(text.charAt(start)) && start + 1 < text.length() ? 2 : 1);
            } else if (end < text.length()) {
                int boundary = lastBreak(text, start, end);
                if (boundary > start) end = boundary;
            }
            chunks.add(text.substring(start, end));
            start = end;
        }
        return chunks;
    }

    private static int lastBreak(String text, int start, int end) {
        for (int index = end; index > start; index--) {
            char current = text.charAt(index - 1);
            if (current == '\n' || current == ' ' || current == '\t' || current == '\u3000') return index;
        }
        return start;
    }
}
