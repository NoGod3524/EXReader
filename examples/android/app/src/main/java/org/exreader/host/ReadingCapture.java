// SPDX-License-Identifier: MIT
package org.exreader.host;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Copied selector values only; NULL and empty bytes are distinct. */
final class ReadingCapture {
    static final int REFLOW=1,EPUB=2,FIXED=3;
    final int mode;final long unit,start,end;
    final String bookKey,parser,partPath,pageId,chapter;
    private final byte[][] selectors;
    ReadingCapture(long[] numbers,String[] route,byte[][] bytes){
        if(numbers==null||numbers.length!=4||route==null||route.length!=5||bytes==null||bytes.length!=3)throw new IllegalArgumentException("Incomplete reading selector");
        mode=(int)numbers[0];unit=numbers[1];start=numbers[2];end=numbers[3];bookKey=route[0];parser=route[1];partPath=route[2];pageId=route[3];chapter=route[4];
        selectors=new byte[][]{copy(bytes[0]),copy(bytes[1]),copy(bytes[2])};
    }
    private static byte[] copy(byte[] value){return value==null?null:value.clone();}
    long[] numbers(){return new long[]{mode,unit,start,end};}
    String[] route(){return new String[]{bookKey,parser,partPath,pageId,chapter};}
    byte[][] bytes(){return new byte[][]{copy(selectors[0]),copy(selectors[1]),copy(selectors[2])};}
    String text(int index){return decode(selectors[index]);}
    static String decode(byte[] bytes){if(bytes==null)return null;try{return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();}catch(java.nio.charset.CharacterCodingException error){throw new IllegalArgumentException("Invalid reading UTF-8",error);}}
    static byte[] encode(String value,int maximum){if(value==null)throw new IllegalArgumentException("Missing reading text");try{ByteBuffer encoded=StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value));if(encoded.remaining()>maximum)throw new IllegalArgumentException("Reading text exceeds its byte limit");byte[] bytes=new byte[encoded.remaining()];encoded.get(bytes);return bytes;}catch(java.nio.charset.CharacterCodingException error){throw new IllegalArgumentException("Invalid reading Unicode",error);}}
    String[] chapterLocation(long resolvedUnit){if(mode!=EPUB||resolvedUnit<0||partPath==null)throw new IllegalArgumentException("Missing explicit reading chapter");return new String[]{Long.toString(resolvedUnit),partPath,Long.toString(start),Long.toString(end),text(0),text(1),text(2),chapter};}
}
