// SPDX-License-Identifier: MIT
package org.exreader.host;

/** One rendered page plus its measured worker time. */
final class PageLoad {
    final PageSnapshot snapshot;
    final long millis;

    PageLoad(PageSnapshot snapshot, long millis) {
        this.snapshot = snapshot;
        this.millis = millis;
    }
}
