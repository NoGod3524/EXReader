package org.exreader.importentry;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.Test;

public class DisplayFilenameTest {
    @Test public void defaultTitleStillRemovesExtension() {
        assertEquals("NewReview", ImportEntry.titleFrom("NewReview.txt"));
        assertEquals(".hidden", ImportEntry.titleFrom(".hidden"));
    }

    @Test public void retainedFilenamePreservesActualSpellingWithoutInventingExtensions() {
        assertEquals("NewReview.txt", ImportEntry.filenameFrom("NewReview.txt"));
        assertEquals("Title.EPUB", ImportEntry.filenameFrom("Title.EPUB"));
        assertEquals("no-extension", ImportEntry.filenameFrom("no-extension"));
        assertEquals("", ImportEntry.filenameFrom(null));
    }

    @Test public void retainedFilenameKeepsExistingSafetyAndUtf8Limit() {
        assertEquals("..evilname.txt", ImportEntry.filenameFrom("../evil\\name\n.txt"));
        String value = ImportEntry.filenameFrom("书".repeat(100) + ".txt");
        assertTrue(value.getBytes(StandardCharsets.UTF_8).length <= 256);
        assertEquals("书".repeat(85), value);
    }
}
