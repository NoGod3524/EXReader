// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.os.OperationCanceledException;
import android.text.Editable;
import android.text.InputFilter;
import android.text.TextWatcher;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Executor;
import java.util.function.Consumer;

/** UI-owned three-page window over the product catalog; all SQLite work uses the host owner. */
final class CatalogShelf extends BaseAdapter implements AutoCloseable, AbsListView.OnScrollListener {
    interface Loader {
        List<CatalogStore.ShelfBook> load(String query, CatalogStore.ShelfKey anchor,
                                         boolean before, boolean inclusive, CancellationSignal cancellation);
    }
    static final int PAGE_SIZE = 50, MAX_ROWS = PAGE_SIZE * 3;
    private final Context context;
    private final ListView list;
    private final EditText search;
    private final TextView status;
    private final SharedPreferences prefs;
    private final Executor executor;
    private final Loader loader;
    private final Consumer<Throwable> failure;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final List<CatalogStore.ShelfBook> rows = new ArrayList<>();
    private CancellationSignal cancellation;
    private Runnable pendingSearch;
    private String query;
    private long generation, appliedGeneration, discardedResults;
    private int maxRowsObserved;
    private int createdViews, recycledViews;
    private long activityStartedNs, firstInteractiveNs;
    private android.view.ViewTreeObserver.OnPreDrawListener firstDraw;
    private boolean loading, before, after, applying, started;
    private volatile boolean closed;

    CatalogShelf(Context context, ListView list, EditText search, TextView status, SharedPreferences prefs,
                 Executor executor, Loader loader, Consumer<Throwable> failure) {
        this.context=context; this.list=list; this.search=search; this.status=status; this.prefs=prefs;
        this.executor=executor; this.loader=loader; this.failure=failure;
        query=prefs.getString("catalog_query", "");
        search.setFilters(new InputFilter[]{new InputFilter.LengthFilter(256)});
        search.setText(query);
        list.setAdapter(this);
        list.setOnScrollListener(this);
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                query=Normalizer.normalize(s.toString().trim(), Normalizer.Form.NFC);
                invalidateRequest(); // Invalidate now, before the debounce; an old result cannot flash back.
                rows.clear(); CatalogShelf.this.before=CatalogShelf.this.after=false; notifyDataSetChanged();
                status.setText("Loading books…");
                if (pendingSearch != null) ui.removeCallbacks(pendingSearch);
                pendingSearch=()-> { if (started && !closed) reset(null, 0); };
                ui.postDelayed(pendingSearch, 180);
            }
            @Override public void afterTextChanged(Editable value) { }
        });
    }

    void start() {
        if (started || closed) return;
        started=true;
        String key=prefs.getString("catalog_top_key", null), sort=prefs.getString("catalog_top_sort", null);
        reset(!query.equals(prefs.getString("catalog_query", "")) || key==null || sort==null
                ? null : new CatalogStore.ShelfKey(sort,key), prefs.getInt("catalog_top_y",0));
    }

    void load() { if (!started) start(); else refresh(); }

    void observeFirstInteractive(long startedNs) {
        activityStartedNs=startedNs;
        firstDraw=()->{
            if (firstInteractiveNs==0 && started && !loading && appliedGeneration==generation
                    && (rows.isEmpty() || list.getChildCount()>0) && list.isShown() && list.isEnabled()) {
                firstInteractiveNs=android.os.SystemClock.elapsedRealtimeNanos();
                list.getViewTreeObserver().removeOnPreDrawListener(firstDraw); firstDraw=null;
            }
            return true;
        };
        list.getViewTreeObserver().addOnPreDrawListener(firstDraw);
    }

    CatalogStore.ShelfBook cachedBook(long id) {
        for (CatalogStore.ShelfBook row:rows) if (row.sdkBookId==id) return row;
        return null;
    }

    void refresh() {
        if (!started || closed) return;
        Viewport viewport=viewport();
        reset(viewport==null ? null : viewport.key, viewport==null ? 0 : viewport.top);
    }

    private void invalidateRequest() {
        ++generation;
        if (cancellation != null) cancellation.cancel();
        cancellation=null; loading=false;
    }

    private void reset(CatalogStore.ShelfKey anchor, int top) {
        invalidateRequest();
        rows.clear(); before=after=false;
        notifyDataSetChanged();
        request(anchor,false,true,true,top);
    }

    private void request(CatalogStore.ShelfKey anchor, boolean previous, boolean inclusive, boolean reset, int restoreTop) {
        if (loading || closed) return;
        loading=true;
        status.setText("Loading books…");
        final long token=generation;
        final String requestedQuery=query;
        final CancellationSignal signal=new CancellationSignal();
        cancellation=signal;
        executor.execute(()->{
            try {
                signal.throwIfCanceled();
                List<CatalogStore.ShelfBook> page=loader.load(requestedQuery,anchor,previous,inclusive,signal);
                ui.post(()->{
                    if (closed || token!=generation || signal.isCanceled()) { discardedResults++; return; }
                    loading=false; cancellation=null;
                    if (reset && page.isEmpty() && anchor!=null && !previous) {
                        request(anchor,true,false,true,restoreTop); return;
                    }
                    apply(page,previous,reset,anchor,restoreTop);
                    appliedGeneration=token;
                });
            } catch (Throwable error) {
                ui.post(()->{
                    if (closed || token!=generation || signal.isCanceled() || error instanceof OperationCanceledException) {
                        discardedResults++; return;
                    }
                    loading=false; cancellation=null;
                    status.setText("Could not load books. Refresh to retry.");
                    failure.accept(error);
                });
            }
        });
    }

    private void apply(List<CatalogStore.ShelfBook> page, boolean previous, boolean reset,
                       CatalogStore.ShelfKey anchor, int restoreTop) {
        if (page.size()>PAGE_SIZE) throw new IllegalStateException("Catalog page exceeded its bound");
        Viewport visible=reset ? null : viewport();
        int first=list.getFirstVisiblePosition(), last=first+list.getChildCount();
        // A fast reversal may make a pending page's eviction unsafe. Retry only on a later edge scroll.
        if (!reset && rows.size()+page.size()>MAX_ROWS
                && ((!previous && first<PAGE_SIZE) || (previous && last>rows.size()-PAGE_SIZE))) {
            status.setText("On this device"); return;
        }
        applying=true;
        if (reset) {
            rows.clear(); rows.addAll(page);
            before=anchor!=null;
            after=!previous && page.size()==PAGE_SIZE;
            if (previous) before=page.size()==PAGE_SIZE;
        } else if (previous) {
            rows.addAll(0,page); before=page.size()==PAGE_SIZE;
            while (rows.size()>MAX_ROWS) { rows.remove(rows.size()-1); after=true; }
        } else {
            rows.addAll(page); after=page.size()==PAGE_SIZE;
            while (rows.size()>MAX_ROWS) { rows.remove(0); before=true; }
        }
        maxRowsObserved=Math.max(maxRowsObserved,rows.size());
        notifyDataSetChanged();
        if (visible!=null) restore(visible.key,visible.top);
        else if (reset) restore(anchor,restoreTop);
        status.setText(rows.isEmpty() ? query.isEmpty() ? "No books on this device" : "No matching books" : "On this device");
        applying=false;
        list.post(()->onScroll(list,list.getFirstVisiblePosition(),list.getChildCount(),getCount()));
    }

    private void restore(CatalogStore.ShelfKey key, int top) {
        int index=0;
        if (key!=null) for (int at=0;at<rows.size();at++) if (rows.get(at).key.bookKey.equals(key.bookKey)) { index=at; break; }
        list.setSelectionFromTop(index,top);
    }

    private static final class Viewport {
        final CatalogStore.ShelfKey key; final int top;
        Viewport(CatalogStore.ShelfKey key,int top) { this.key=key; this.top=top; }
    }

    private Viewport viewport() {
        int first=list.getFirstVisiblePosition();
        View child=list.getChildAt(0);
        return first<0 || first>=rows.size() || child==null ? null : new Viewport(rows.get(first).key,child.getTop());
    }

    void save() {
        SharedPreferences.Editor edit=prefs.edit().putString("catalog_query",query);
        Viewport visible=viewport();
        if (visible!=null) edit.putString("catalog_top_sort",visible.key.sortTitle).putString("catalog_top_key",visible.key.bookKey)
                .putInt("catalog_top_y",visible.top);
        else if (rows.isEmpty()) edit.remove("catalog_top_sort").remove("catalog_top_key").remove("catalog_top_y");
        edit.apply();
    }

    @Override public void onScrollStateChanged(AbsListView view,int scrollState) {
        if (scrollState==SCROLL_STATE_IDLE) save();
    }

    @Override public void onScroll(AbsListView view,int first,int visible,int total) {
        if (closed || loading || applying || rows.isEmpty()) return;
        if (after && first+visible>=total-8) request(rows.get(rows.size()-1).key,false,false,false,0);
        else if (before && first<8) request(rows.get(0).key,true,false,false,0);
    }

    @Override public int getCount() { return rows.size(); }
    @Override public CatalogStore.ShelfBook getItem(int position) { return rows.get(position); }
    @Override public long getItemId(int position) { return getItem(position).sdkBookId; }
    @Override public boolean hasStableIds() { return true; }

    @Override public View getView(int position,View recycled,ViewGroup parent) {
        if (recycled==null) createdViews++; else recycledViews++;
        View row=recycled==null ? LayoutInflater.from(context).inflate(android.R.layout.simple_list_item_1,parent,false) : recycled;
        CatalogStore.ShelfBook book=getItem(position);
        TextView title=row.findViewById(android.R.id.text1);
        title.setMaxLines(3); title.setEllipsize(TextUtils.TruncateAt.END);
        String bytes=book.sourceBytes<1024 ? book.sourceBytes+" B" : book.sourceBytes<1024*1024
                ? String.format(Locale.ROOT,"%.1f KiB",book.sourceBytes/1024.0)
                : String.format(Locale.ROOT,"%.1f MiB",book.sourceBytes/(1024.0*1024.0));
        title.setText(book.title+"\n"+(book.author.isEmpty() ? "" : book.author+" · ")+book.format.toUpperCase(Locale.ROOT)+" · "+bytes);
        return row;
    }

    String observation() {
        try {
            JSONArray keys=new JSONArray(), visibleKeys=new JSONArray();
            for (CatalogStore.ShelfBook book:rows) keys.put(book.key.bookKey);
            int first=list.getFirstVisiblePosition();
            for(int at=Math.max(0,first);at<Math.min(rows.size(),first+list.getChildCount());at++)visibleKeys.put(rows.get(at).key.bookKey);
            Viewport visible=viewport();
            return new JSONObject().put("query",query).put("generation",generation).put("applied_generation",appliedGeneration)
                    .put("loading",loading).put("cached_rows",rows.size()).put("max_cached_rows",maxRowsObserved)
                    .put("page_limit",PAGE_SIZE).put("cache_limit",MAX_ROWS).put("has_before",before).put("has_after",after)
                    .put("discarded_results",discardedResults).put("visible_children",list.getChildCount())
                    .put("created_views",createdViews).put("recycled_views",recycledViews)
                    .put("activity_started_elapsed_ns",activityStartedNs).put("first_interactive_elapsed_ns",firstInteractiveNs)
                    .put("first_interactive_ms",firstInteractiveNs==0 ? JSONObject.NULL : (firstInteractiveNs-activityStartedNs)/1e6)
                    .put("top_key",visible==null ? JSONObject.NULL : visible.key.bookKey)
                    .put("top_y",visible==null ? 0 : visible.top).put("keys",keys).put("visible_keys",visibleKeys).toString();
        } catch (Exception error) { throw new IllegalStateException(error); }
    }

    @Override public void close() {
        save(); closed=true; invalidateRequest();
        if (pendingSearch!=null) ui.removeCallbacks(pendingSearch);
        if (firstDraw!=null && list.getViewTreeObserver().isAlive())list.getViewTreeObserver().removeOnPreDrawListener(firstDraw);
    }
}
