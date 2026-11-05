// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Known spellings only. This admits subsequent original/selector checks; it
 * never changes a stored tag or labels the current SDK as a different version. */
final class ReadingParserPolicy {
    private ReadingParserPolicy() {}
    static boolean accepts(String recorded, String actual) {
        if (recorded == null || actual == null || actual.isEmpty()) return false;
        if (recorded.equals("exreader-sdk-" + actual)) return true;
        if (actual.equals("3.42.0") && recorded.equals("exreader-sdk-3.41.0")) return true;
        return actual.equals("3.41.0") &&
            (recorded.equals("3.41.0") || recorded.equals("3.40.0") ||
             recorded.equals("exreader-sdk-3.40.0"));
    }
}
