// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.InputType;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

/** Low-frequency native settings; a draft never changes the accepted reader. */
final class PreferencesPanel {
    interface Host {
        ReadingPreferences preferences();
        void preferencesApply(ReadingPreferences value,Runnable done,java.util.function.Consumer<Throwable> failed);
        void preferencesCancel();
    }
    private final Activity activity;private final Host host;private AlertDialog dialog;private boolean busy;
    PreferencesPanel(Activity activity,Host host){this.activity=activity;this.host=host;}
    boolean visible(){return dialog!=null&&dialog.isShowing();}
    void close(){if(busy)host.preferencesCancel();if(dialog!=null){hideKeyboard();dialog.dismiss();}dialog=null;busy=false;}
    private void hideKeyboard(){if(dialog==null||dialog.getWindow()==null)return;android.view.inputmethod.InputMethodManager input=(android.view.inputmethod.InputMethodManager)activity.getSystemService(Activity.INPUT_METHOD_SERVICE);if(input!=null)input.hideSoftInputFromWindow(dialog.getWindow().getDecorView().getWindowToken(),0);}
    private EditText number(LinearLayout box,String label,float value){
        TextView title=new TextView(activity);title.setText(label);box.addView(title);
        EditText input=new EditText(activity);input.setSingleLine(true);input.setContentDescription(label);
        input.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL|InputType.TYPE_NUMBER_FLAG_SIGNED);
        input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(14)});
        input.setText(Float.toString(value));box.addView(input);return input;
    }
    private Spinner choice(LinearLayout box,String label,String[] rows,int selected){
        TextView title=new TextView(activity);title.setText(label);box.addView(title);
        Spinner input=new Spinner(activity);input.setContentDescription(label);ArrayAdapter<String> adapter=new ArrayAdapter<>(activity,android.R.layout.simple_spinner_item,rows);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);input.setAdapter(adapter);input.setSelection(selected-1);box.addView(input);return input;
    }
    void show(){
        close();ReadingPreferences original=host.preferences();if(original==null)return;
        LinearLayout box=new LinearLayout(activity);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(24,12,24,12);
        EditText font=number(box,"字号 pt",original.font),line=number(box,"行距倍数",original.line),paragraph=number(box,"段距 pt",original.paragraph),margin=number(box,"页边距 pt",original.margin),zoom=number(box,"固定页缩放 %",original.zoom);
        Spinner theme=choice(box,"主题",new String[]{"浅色","深色（暂不可用）","跟随系统"},original.theme);
        TextView colors=new TextView(activity);colors.setText("阅读页颜色由文档决定。深色阅读页暂不可用；系统为深色时保持原页并提示。");box.addView(colors);
        Spinner direction=choice(box,"翻页方向",new String[]{"从左向右","从右向左","上下翻页"},original.direction);
        Spinner input=choice(box,"翻页操作",new String[]{"点击","滑动","点击和滑动","方向键"},original.input);
        TextView status=new TextView(activity);status.setContentDescription("阅读设置状态");status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);box.addView(status);
        ScrollView scroll=new ScrollView(activity);scroll.addView(box);
        dialog=new AlertDialog.Builder(activity).setTitle("阅读设置").setView(scroll).setPositiveButton("应用",null).setNegativeButton("取消",null).create();
        dialog.setOnCancelListener(ignored->{if(busy)host.preferencesCancel();busy=false;});
        dialog.setOnDismissListener(ignored->{hideKeyboard();android.view.View reader=activity.findViewById(R.id.reader_view);if(reader!=null)reader.post(reader::requestFocus);});
        if(dialog.getWindow()!=null)dialog.getWindow().setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
        dialog.show();AlertDialog owner=dialog;
        owner.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener(view->close());
        owner.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            if(busy)return;
            try{
                float scale=Float.parseFloat(zoom.getText().toString());if(!Float.isFinite(scale)||scale!=(int)scale)throw new IllegalArgumentException("缩放需为整数百分比");
                ReadingPreferences candidate=original.with(Float.parseFloat(font.getText().toString()),Float.parseFloat(line.getText().toString()),Float.parseFloat(paragraph.getText().toString()),Float.parseFloat(margin.getText().toString()),theme.getSelectedItemPosition()+1,direction.getSelectedItemPosition()+1,input.getSelectedItemPosition()+1,(int)scale);
                busy=true;owner.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);status.setText("正在准备页面…");
                host.preferencesApply(candidate,()->{if(dialog==owner){busy=false;close();}},error->{if(dialog==owner){busy=false;owner.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);status.setText(error.getMessage()==null?"未能应用设置":error.getMessage());scroll.post(()->scroll.smoothScrollTo(0,box.getBottom()));}});
            }catch(IllegalArgumentException error){status.setText(error.getMessage()==null?"请输入有效数值":error.getMessage());scroll.post(()->scroll.smoothScrollTo(0,box.getBottom()));}
        });
    }
}
