    private void seed()throws Exception{
        books=new JSONObject();owner(store->{
            JSONArray originals=input.getJSONArray("books");for(int i=0;i<originals.length();i++){
                JSONObject row=originals.getJSONObject(i);File file=new File(context.getFilesDir(),"preferences-fixtures/"+row.getString("file"));
                NativeLibrary.ImportResult imported=store.nativeLibrary().importFile(file.getPath(),format(row.getString("format")),row.getString("title"));
                BookStore.VerifiedSource source=store.verifySource(imported.id,row.getString("sha256"),row.getLong("bytes"),task());store.finalizeImport(source);
                books.put(row.getString("role"),new JSONObject().put("id",imported.id).put("title",source.book.title).put("sha256",source.sha256).put("format",source.format));
                need(context.getSharedPreferences("host",0).edit().putString("path_"+imported.id,file.getPath()).putLong("size_"+imported.id,file.length()).commit(),"actual host private original mapping");
            }return true;
        });Files.write(new File(context.getFilesDir(),"preferences-books.json").toPath(),books.toString().getBytes(StandardCharsets.UTF_8));click("Refresh");
    }
    private String snapshot()throws Exception{return owner(store->{
        JSONObject result=new JSONObject();JSONArray rows=new JSONArray();NativeLibrary library=store.nativeLibrary();NativeLibrary.Book[] items=library.books();Arrays.sort(items,(a,b)->Long.compare(a.id,b.id));
        for(NativeLibrary.Book value:items){JSONObject row=new JSONObject().put("id",value.id).put("position",value.position).put("source",hash(library,value.id));JSONArray notes=new JSONArray();
            if(value.fixed()){for(NativeLibrary.FixedNote note:library.fixedNotes(value.id))notes.put(new JSONArray().put(note.id).put(note.page).put(note.start).put(note.end).put(note.comment).put(note.selected));}
            else{for(NativeLibrary.Note note:library.notes(value.id))notes.put(new JSONArray().put(note.id).put(note.start).put(note.end).put(note.comment).put(note.selected));if(value.format==NativeLibrary.FORMAT_EPUB&&library.bounded(value.id))row.put("progress",BoundedEpub.progressIdentity(library,value.id));else{long[] progress=library.progress(value.id);row.put("progress",progress==null?JSONObject.NULL:new JSONArray(progress));}}
            row.put("notes",notes);rows.put(row);
        }
        java.util.ArrayList<String> outbox=new java.util.ArrayList<>();for(byte[] wire:RecordWireProbe.outbox(store.productOwner()))outbox.add(digest(wire));java.util.Collections.sort(outbox);
        result.put("sdk",rows).put("outbox_wires",new JSONArray(outbox));return result.toString();
    });}
    private static String digest(byte[] bytes)throws Exception{StringBuilder hash=new StringBuilder();for(byte value:MessageDigest.getInstance("SHA-256").digest(bytes))hash.append(String.format(Locale.ROOT,"%02x",value&255));return hash.toString();}
    private static void durable(File path,byte[] bytes)throws Exception{File directory=path.getParentFile();need(directory.isDirectory()||directory.mkdirs(),"bundle directory");File temporary=new File(directory,path.getName()+".pending");try(FileOutputStream stream=new FileOutputStream(temporary)){stream.write(bytes);stream.getFD().sync();}Files.move(temporary.toPath(),path.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE,java.nio.file.StandardCopyOption.REPLACE_EXISTING);}
