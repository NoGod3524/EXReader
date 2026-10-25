    private final JSONArray themeFrames=new JSONArray();
    private void themeOriginal(boolean value){visible("原始配色");until(node->description(node,"原始配色")&&node.isVisibleToUser(),node->{if(node.isChecked()!=value)tap(node);},"explicit Original control",30000);}
    private JSONObject actualThemeFrame(String name,boolean dark)throws Exception{
        JSONObject page=settledFrame();need(page.getJSONObject("page_theme").getBoolean("enabled"),"actual accepted theme mode");
        need(page.getJSONObject("page_theme").getString("sdk").equals("3.41.0"),"runtime renderer SDK3.41");
        AtomicReference<byte[]> observed=new AtomicReference<>(),png=new AtomicReference<>();AtomicReference<int[]> geometry=new AtomicReference<>();
        runOnMainSync(()->{try{
            PageSnapshot actual=(PageSnapshot)ReadingReview.field(activity(),"current");
            need(actual!=null&&actual.bookId==page.getLong("book")&&actual.start==page.getLong("start"),"observed pixels belong to the actual accepted live frame");
            int w=actual.bitmap.getWidth(),h=actual.bitmap.getHeight();int[] colors=new int[w*h];actual.bitmap.getPixels(colors,0,w,0,0,w,h);byte[] rgba=new byte[w*h*4];
            for(int i=0;i<colors.length;i++){int c=colors[i];rgba[i*4]=(byte)(c>>16);rgba[i*4+1]=(byte)(c>>8);rgba[i*4+2]=(byte)c;rgba[i*4+3]=(byte)(c>>24);}
            java.io.ByteArrayOutputStream encoded=new java.io.ByteArrayOutputStream();need(actual.bitmap.compress(Bitmap.CompressFormat.PNG,100,encoded),"lossless original bitmap encoding");observed.set(rgba);png.set(encoded.toByteArray());geometry.set(new int[]{w,h});
        }catch(Exception error){throw new RuntimeException(error);}});
        byte[] rgba=observed.get();int[] size=geometry.get();String background=dark?"101010ff":"ffffffff",foreground=dark?"e6e6e6ff":"1a1a1aff";
        need(String.format(Locale.ROOT,"%02x%02x%02x%02x",rgba[0]&255,rgba[1]&255,rgba[2]&255,rgba[3]&255).equals(background),"actual native whole-page corner palette");
        int wanted=dark?0xe6:0x1a,ink=0;for(int at=0;at<rgba.length;at+=4)if((rgba[at]&255)==wanted&&(rgba[at+1]&255)==wanted&&(rgba[at+2]&255)==wanted&&(rgba[at+3]&255)==255)ink++;
        need(ink>10,"actual fully covered ink pixels have selected foreground");
        File directory=new File(context.getFilesDir(),"page-theme-captures");need(directory.isDirectory()||directory.mkdirs(),"raw theme evidence directory");Files.write(new File(directory,name+".rgba").toPath(),rgba);Files.write(new File(directory,name+".png").toPath(),png.get());
        JSONObject observation=new JSONObject().put("name",name).put("width",size[0]).put("height",size[1]).put("foreground_rgba",foreground).put("background_rgba",background).put("solid_ink_pixels",ink).put("frame",page).put("rgba_sha256",digestBytes(rgba)).put("png_sha256",digestBytes(png.get())).put("accepted",true);
        themeFrames.put(observation);return observation;
    }
    private static String digestBytes(byte[] bytes)throws Exception{StringBuilder text=new StringBuilder();for(byte value:MessageDigest.getInstance("SHA-256").digest(bytes))text.append(String.format(Locale.ROOT,"%02x",value&255));return text.toString();}
