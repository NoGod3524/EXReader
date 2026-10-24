// SPDX-License-Identifier: MIT
package org.exreader.host;

/** Device-local F3 value; its installed C ABI owns validation and persistence. */
final class ReadingPreferences {
    final float font,line,paragraph,margin;
    final int theme,direction,input,zoom;
    private final byte[] palette;
    ReadingPreferences(float[] numbers,int[] choices,byte[] colors) {
        if(numbers==null||numbers.length!=4||choices==null||choices.length!=4||colors==null||colors.length!=16)throw new IllegalArgumentException("Incomplete preferences");
        font=numbers[0];line=numbers[1];paragraph=numbers[2];margin=numbers[3];
        theme=choices[0];direction=choices[1];input=choices[2];zoom=choices[3];palette=colors.clone();
    }
    float[] numbers(){return new float[]{font,line,paragraph,margin};}
    int[] choices(){return new int[]{theme,direction,input,zoom};}
    byte[] colors(){return palette.clone();}
    ReadingPreferences with(float size,float height,float spacing,float inset,int appearance,int turn,int operation,int scale){
        return new ReadingPreferences(new float[]{size,height,spacing,inset},new int[]{appearance,turn,operation,scale},palette);
    }
}
