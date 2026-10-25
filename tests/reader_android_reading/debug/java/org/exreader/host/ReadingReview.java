// SPDX-License-Identifier: MIT
package org.exreader.host;
import android.app.Activity;
import java.lang.reflect.Field;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
/** Tests observe and borrow the real worker, store and accepted page. */
final class ReadingReview {
    interface Call<T>{T run(BookStore store)throws Exception;}
    static Object field(Activity activity,String name)throws Exception{Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);return field.get(activity);}
    static <T>T call(Activity activity,Call<T> call)throws Exception{
        ExecutorService worker=(ExecutorService)field(activity,"worker");BookStore store=(BookStore)field(activity,"store");FutureTask<T> result=new FutureTask<>(()->call.run(store));worker.execute(result);return result.get(120,TimeUnit.SECONDS);
    }
}
