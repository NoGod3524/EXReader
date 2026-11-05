package org.exreader.host;

/** Executes the actual capture state class without an Android runtime or rendering a fake frame. */
public final class CatalogFrameLatchControl {
    private static int checks;
    private static void need(boolean ok){checks++;if(!ok)throw new AssertionError("control "+checks);}
    private static void status(String expected,String actual){need(expected.equals(actual));}
    public static void main(String[] args){
        Object window=new Object(),other=new Object();
        CatalogFrameLatch x=new CatalogFrameLatch(window);
        status("wrong_window",x.arm(other,1,3,true));status("armed",x.arm(window,1,3,true));
        status("duplicate_apply",x.arm(window,1,4,true));status("wrong_window",x.frame(other,100));
        status("latched",x.frame(window,100));status("duplicate_latch",x.frame(window,101));
        status("candidate",x.ready(window,1,3));status("candidate",x.draw(window,1,3));
        status("duplicate_ready",x.ready(window,1,3));status("duplicate_tree_draw_begin",x.draw(window,1,3));
        x.clear();need(!x.active);need(x.frameTimeNs==100);
        x=new CatalogFrameLatch(window);status("armed",x.arm(window,1,3,true));status("latched",x.frame(window,100));x.clear();
        status("outside_frame",x.ready(window,1,3));status("missing_ready",x.draw(window,1,3));
        x=new CatalogFrameLatch(window);status("armed",x.arm(window,1,3,true));status("latched",x.frame(window,100));
        status("wrong_revision",x.ready(window,1,4));status("missing_ready",x.draw(window,1,3));
        x=new CatalogFrameLatch(window);status("armed",x.arm(window,1,3,true));status("latched",x.frame(window,100));
        status("candidate",x.ready(window,1,3));status("wrong_window",x.draw(other,1,3));
        x=new CatalogFrameLatch(window);status("no_pending_draw",x.arm(window,1,3,false));status("unarmed",x.frame(window,100));status("unarmed",x.ready(window,1,3));
        x=new CatalogFrameLatch(window);status("armed",x.arm(window,1,3,true));x.close();status("closed",x.frame(window,100));status("closed",x.ready(window,1,3));
        System.out.println("{\"state_controls\":"+checks+",\"f08_accepted\":false}");
    }
}
