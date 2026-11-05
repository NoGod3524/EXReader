package org.exreader.host;

public final class Policy342Check {
    private static void check(String recorded, String actual, boolean expected) {
        if (ReadingParserPolicy.accepts(recorded, actual) != expected)
            throw new AssertionError(String.valueOf(recorded) + " / " + actual);
    }
    public static void main(String[] args) {
        check("exreader-sdk-3.41.0", "3.42.0", true);
        check("exreader-sdk-3.42.0", "3.42.0", true);
        check("3.41.0", "3.42.0", false);
        check("3.40.0", "3.42.0", false);
        check("exreader-sdk-3.40.0", "3.42.0", false);
        check("3.42.0", "3.42.0", false);
        check("exreader-sdk-3.43.0", "3.42.0", false);
        check("exreader-sdk-3.41.1", "3.42.0", false);
        check("exreader-sdk-exreader-sdk-3.41.0", "3.42.0", false);
        check("exreader-sdk-3.41.0 ", "3.42.0", false);
        check(null, "3.42.0", false);
        check("exreader-sdk-3.41.0", null, false);
    }
}
