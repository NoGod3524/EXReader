package org.exreader.hostimportsource;

import java.io.IOException;
import java.io.OutputStream;

/** Deterministic byte generators: byte at stream position p is PATTERN[p % 64], so any chunking is comparable. */
final class Streams {
    private static final byte[] PATTERN =
            "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ \n".getBytes();

    private Streams() { }

    static void text(OutputStream out, long length, int maxChunk, boolean tiny) throws IOException {
        text(out, length, maxChunk, tiny, 0);
    }

    /** {@code startPosition} continues an earlier call so the whole stream stays one deterministic sequence. */
    static void text(OutputStream out, long length, int maxChunk, boolean tiny, long startPosition) throws IOException {
        byte[] block = new byte[Math.max(1, Math.min(maxChunk, 65536))];
        long pos = startPosition, end = startPosition + length;
        int writes = 0;
        while (pos < end) {
            int want = tiny ? 1 + (writes % 37) : block.length;
            int n = (int) Math.min(Math.min(want, block.length), end - pos);
            for (int i = 0; i < n; i++) block[i] = PATTERN[(int) ((pos + i) % 64)];
            out.write(block, 0, n);
            pos += n;
            if (tiny && ++writes % 64 == 0) {
                out.flush();
                try { Thread.sleep(1); } catch (InterruptedException e) { throw new IOException(e); }
            }
        }
        out.flush();
    }

    /** Minimal ZIP local header naming an EPUB mimetype member, then zeros to the requested total length. */
    static void epubLike(OutputStream out, long total) throws IOException {
        byte[] head = new byte[58];
        head[0] = 'P'; head[1] = 'K'; head[2] = 3; head[3] = 4;
        head[26] = 8;
        byte[] name = "mimetypeapplication/epub+zip".getBytes();
        System.arraycopy(name, 0, head, 30, name.length);
        out.write(head);
        byte[] zeros = new byte[65536];
        long left = total - head.length;
        while (left > 0) {
            int n = (int) Math.min(zeros.length, left);
            out.write(zeros, 0, n);
            left -= n;
        }
    }

    static void raw(OutputStream out, byte[] prefix, int total) throws IOException {
        out.write(prefix);
        out.write(new byte[total - prefix.length]);
    }
}
