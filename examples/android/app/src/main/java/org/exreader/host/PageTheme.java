// SPDX-License-Identifier: MIT
package org.exreader.host;

/** UI-sampled immutable render inputs. No OS/configuration access on the SDK owner. */
final class PageTheme {
    static final PageTheme ORIGINAL=new PageTheme(false,0x000000ff,0xffffffff,0);
    final boolean enabled;
    final int foreground,background,system;
    private PageTheme(boolean enabled,int foreground,int background,int system){this.enabled=enabled;this.foreground=foreground;this.background=background;this.system=system;}
    static PageTheme sample(ReadingPreferences value,int system,boolean original){
        if(!BuildConfig.READER_PAGE_THEME||original||value==null)return ORIGINAL;
        byte[] colors=value.colors();int at=(value.theme==2||value.theme==3&&system==2)?8:0;
        return new PageTheme(true,rgba(colors,at),rgba(colors,at+4),system);
    }
    private static int rgba(byte[] bytes,int at){return (bytes[at]&255)<<24|(bytes[at+1]&255)<<16|(bytes[at+2]&255)<<8|(bytes[at+3]&255);}
}
