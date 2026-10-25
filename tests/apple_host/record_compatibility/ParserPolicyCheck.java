// SPDX-License-Identifier: MIT
package org.exreader.host;

public final class ParserPolicyCheck {
    static void check(String name, String recorded, String actual, boolean expected) {
        if (ReadingParserPolicy.accepts(recorded, actual) != expected)
            throw new AssertionError(name);
        System.out.println("CASE " + name);
    }
    public static void main(String[] args) {
        check("android-current-own-spelling", "exreader-sdk-3.41.0", "3.41.0", true);
        check("desktop-current-spelling", "3.41.0", "3.41.0", true);
        check("android-old-upgrade", "exreader-sdk-3.40.0", "3.41.0", true);
        check("desktop-old-upgrade", "3.40.0", "3.41.0", true);
        check("old-runtime-original-own-behavior", "exreader-sdk-3.40.0", "3.40.0", true);
        check("old-runtime-no-new-bare-admission", "3.40.0", "3.40.0", false);
        check("old-runtime-no-downgrade", "exreader-sdk-3.41.0", "3.40.0", false);
        check("null-record", null, "3.41.0", false);
        check("null-runtime", "3.41.0", null, false);
        check("empty-runtime", "exreader-sdk-", "", false);
        check("empty-record", "", "3.41.0", false);
        check("future-prefixed", "exreader-sdk-3.42.0", "3.41.0", false);
        check("future-bare", "3.42.0", "3.41.0", false);
        check("unknown-old-patch", "3.40.1", "3.41.0", false);
        check("unknown-old-prefixed-patch", "exreader-sdk-3.40.1", "3.41.0", false);
        check("duplicate-prefix", "exreader-sdk-exreader-sdk-3.41.0", "3.41.0", false);
        check("trailing-space", "exreader-sdk-3.41.0 ", "3.41.0", false);
        check("embedded-nul", "3.41.0\u0000", "3.41.0", false);
        check("short-version", "3.41", "3.41.0", false);
        check("nearby-prefix", "exreader-3.41.0", "3.41.0", false);
    }
}
