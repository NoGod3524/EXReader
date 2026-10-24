// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.Arrays;
import java.util.UUID;
import org.exreader.credentials.CredentialStore;

/** One library binding; only the platform credential store persists a secret. */
final class AccountStore {
    private final SharedPreferences preferences;
    private final CredentialStore credentials;
    private byte[] currentSecret;
    AccountStore(Context context){
        preferences=context.getSharedPreferences("reader-sync",Context.MODE_PRIVATE);
        credentials=CredentialStore.open(context,"org.exreader.reader.webdav");
    }
    String id(){
        String value=preferences.getString("account",null);
        if(value==null){value=UUID.randomUUID().toString();if(!preferences.edit().putString("account",value).commit())throw new IllegalStateException("账号标识保存失败");}
        return value;
    }
    String root(){return preferences.getString("root","");}
    int configure(String root,byte[] authorization,boolean remember){
        if(root==null||!NativeSync.validRoot(root)||authorization==null||authorization.length==0||authorization.length>CredentialStore.SECRET_MAX)return CredentialStore.ARGUMENT;
        String previous=root();if(!previous.isEmpty()&&!previous.equals(root))throw new IllegalStateException("此书库已绑定另一个云盘地址");
        String account=id();int status=remember?credentials.put(account,authorization):CredentialStore.OK;
        if(status!=CredentialStore.OK)return status;
        if(!preferences.edit().putString("root",root).commit())return CredentialStore.IO;
        clearMemory();currentSecret=authorization.clone();return CredentialStore.OK;
    }
    byte[] authorization(){
        if(currentSecret!=null)return currentSecret.clone();
        byte[] bytes=new byte[CredentialStore.SECRET_MAX];int[] size={0};int status=credentials.get(id(),bytes,size);
        if(status!=CredentialStore.OK){Arrays.fill(bytes,(byte)0);throw new IllegalStateException(status==CredentialStore.NOT_FOUND?"请输入云盘凭据":status==CredentialStore.UNAVAILABLE?"安全凭据暂不可用，请解锁设备或仅本次输入":"安全凭据读取失败，请重新输入");}
        byte[] result=Arrays.copyOf(bytes,size[0]);Arrays.fill(bytes,(byte)0);return result;
    }
    void forgetSecret(){int status=credentials.delete(id());if(status!=CredentialStore.OK&&status!=CredentialStore.NOT_FOUND)throw new IllegalStateException("安全凭据移除失败");clearMemory();}
    void clearMemory(){if(currentSecret!=null){Arrays.fill(currentSecret,(byte)0);currentSecret=null;}}
}
