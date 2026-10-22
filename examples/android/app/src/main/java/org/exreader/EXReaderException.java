// SPDX-License-Identifier: MIT
package org.exreader;
public final class EXReaderException extends RuntimeException {
    public final int code;
    public EXReaderException(int code, String message) { super(message); this.code = code; }
}
