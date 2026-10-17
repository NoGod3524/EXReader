// SPDX-License-Identifier: GPL-3.0-only
package org.exreader;
public final class EXReaderException extends RuntimeException {
    public final int code;
    public EXReaderException(int code, String message) { super(message); this.code = code; }
}
