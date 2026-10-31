// SPDX-License-Identifier: MIT
using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
using System.Runtime.InteropServices;
using System.Windows.Automation;
using System.Windows.Automation.Text;
using System.Collections.Generic;
using System.Web.Script.Serialization;
class EscapeProbe {
  static string stagePath;
  static void Stage(string name) {
    if(stagePath==null)return;
    string line=DateTime.UtcNow.ToString("o")+" "+name+"\n";
    byte[] bytes=System.Text.Encoding.UTF8.GetBytes(line);
    using(FileStream file=new FileStream(stagePath,FileMode.Append,FileAccess.Write,FileShare.ReadWrite)){
      file.Write(bytes,0,bytes.Length);file.Flush(true);
    }
    Console.WriteLine("F09-STAGE "+name);
  }
  static string ReadDocument(TextPattern pattern,string label) {
    Stage(label+" document-range-before");
    TextPatternRange range=pattern.DocumentRange;
    Stage(label+" document-range-after null="+(range==null));
    Stage(label+" get-text-before");
    string text=range.GetText(-1);
    Stage(label+" get-text-after length="+text.Length);
    return text;
  }

  [DllImport("user32.dll")] static extern IntPtr GetDlgItem(IntPtr h,int id);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] static extern uint SendInput(uint n,INPUT[] p,int size);
  [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk,scan; public uint flags,time; public UIntPtr extra; }
  [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int x,y; public uint data,flags,time; public UIntPtr extra; }
  [StructLayout(LayoutKind.Explicit)] struct UNION { [FieldOffset(0)] public KEYBDINPUT key; [FieldOffset(0)] public MOUSEINPUT mouse; }
  [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public UNION value; }
  static void Key(ushort vk,bool up) {
    INPUT i=new INPUT(); i.type=1;i.value.key.vk=vk;i.value.key.flags=up?2u:0u;
    if(SendInput(1,new INPUT[]{i},Marshal.SizeOf(typeof(INPUT)))!=1)throw new Exception("SendInput failed");
  }
  static void SelectAll() { Key(0x11,false);try{Key(0x41,false);Key(0x41,true);}finally{Key(0x11,true);} }
  static void Escape() { Key(0x1b,false);Key(0x1b,true); }
  static void Require(bool ok,string label) { if(!ok)throw new Exception(label); }
  static void Wait(Func<bool> predicate,int milliseconds,string label) {
    Stopwatch s=Stopwatch.StartNew();
    while(s.ElapsedMilliseconds<milliseconds){if(predicate())return;Thread.Sleep(25);}
    throw new Exception("timeout: "+label);
  }
  static string Quote(string s){return "\""+s+"\"";}
  static bool EmptyAtStart(TextPattern p) {
    Stage("escape get-selection-before");
    TextPatternRange[] r=p.GetSelection();
    Stage("escape get-selection-after count="+r.Length);
    return r.Length==1 && r[0].CompareEndpoints(TextPatternRangeEndpoint.Start,r[0],TextPatternRangeEndpoint.End)==0
      && r[0].CompareEndpoints(TextPatternRangeEndpoint.Start,p.DocumentRange,TextPatternRangeEndpoint.Start)==0;
  }
  [MTAThread] static int Main(string[] args) {
    Dictionary<string,object> report=new Dictionary<string,object>();
    Process process=null;AutomationElement page=null;AutomationEventHandler handler=null;
    try {
      string exe=Path.GetFullPath(args[0]),output=Path.GetFullPath(args[1]);Directory.CreateDirectory(output);
      stagePath=Path.Combine(output,"stages.log");
      Stage("start bitness="+(IntPtr.Size*8)+" apartment="+Thread.CurrentThread.GetApartmentState()+" probe-pid="+Process.GetCurrentProcess().Id);
      report["event_observation_ms"]=5000;report["executable"]=exe;report["expected_selection_event"]=args[2]=="present";
      ProcessStartInfo si=new ProcessStartInfo(exe,"--data "+Quote(Path.Combine(output,"profile"))+" "+Quote(Path.Combine(Path.GetDirectoryName(exe),"Sample.epub")));
      si.EnvironmentVariables["F09_PROVIDER_LOG"]=Path.Combine(output,"provider.log");
      si.WorkingDirectory=Path.GetDirectoryName(exe);si.UseShellExecute=false;Stage("host-start-before");process=Process.Start(si);
      File.WriteAllText(Path.Combine(output,"host.pid"),process.Id.ToString());
      Stage("host-start-after pid="+process.Id);
      IntPtr hwnd=IntPtr.Zero,pageHwnd=IntPtr.Zero;
      Wait(delegate{if(process.HasExited)throw new Exception("host exited");process.Refresh();hwnd=process.MainWindowHandle;pageHwnd=GetDlgItem(hwnd,123);return pageHwnd!=IntPtr.Zero;},120000,"native page");
      Stage("page-found hwnd="+pageHwnd+" host-exited="+process.HasExited);
      SetForegroundWindow(hwnd);page=AutomationElement.FromHandle(pageHwnd);
      Stage("automation-element-created");
      TextPattern pattern=null;
      Wait(delegate{try{object p;Stage("ready get-pattern-before");if(!page.TryGetCurrentPattern(TextPattern.Pattern,out p)){Stage("ready pattern-unavailable");return false;}Stage("ready get-pattern-after");pattern=(TextPattern)p;return ReadDocument(pattern,"ready").Length>10 && page.Current.IsEnabled;}catch(ElementNotAvailableException){Stage("ready transient-element-unavailable");return false;}},120000,"native text ready");
      page.SetFocus();Wait(delegate{return page.Current.HasKeyboardFocus;},10000,"page keyboard focus");
      string before=ReadDocument(pattern,"before-selection");
      { // Kept alive until process exit: an in-flight UIA callback must not touch a disposed event.
        AutoResetEvent selected=new AutoResetEvent(false);
        handler=delegate(object sender,AutomationEventArgs e){selected.Set();};
        Automation.AddAutomationEventHandler(TextPattern.TextSelectionChangedEvent,page,TreeScope.Element,handler);
        Stage("ctrl-a-before");SelectAll();Stage("ctrl-a-sent");Require(selected.WaitOne(5000),"Ctrl+A event positive control missing");
        Wait(delegate{Stage("ctrl-a get-selection-before");var r=pattern.GetSelection();Stage("ctrl-a get-selection-after count="+r.Length);return r.Length==1 && r[0].GetText(-1).Length>0;},5000,"nonempty selection");
        report["ctrl_a_event"]=true;report["nonempty_selection"]=true;
        Automation.RemoveAutomationEventHandler(TextPattern.TextSelectionChangedEvent,page,handler);handler=null;
      }
      bool got;
      {
        AutoResetEvent cleared=new AutoResetEvent(false);
        handler=delegate(object sender,AutomationEventArgs e){cleared.Set();};
        Automation.AddAutomationEventHandler(TextPattern.TextSelectionChangedEvent,page,TreeScope.Element,handler);
        Stage("escape-before");Escape();Stage("escape-sent");Wait(delegate{return EmptyAtStart(pattern);},5000,"Escape actual selection clear");
        got=cleared.WaitOne(5000);report["escape_cleared_to_document_start"]=true;report["escape_selection_event"]=got;
        Automation.RemoveAutomationEventHandler(TextPattern.TextSelectionChangedEvent,page,handler);handler=null;
      }
      Require(ReadDocument(pattern,"after-escape")==before,"Escape changed page text");
      Require(page.Current.HasKeyboardFocus,"Escape lost page focus");
      report["same_page_text"]=true;report["page_focus_preserved"]=true;
      Require(got==(args[2]=="present"),"Escape event differs from required baseline/candidate outcome");
      Stage("all-assertions-passed");report["passed"]=true;return 0;
    } catch(Exception e){Stage("managed-exception "+e.GetType().FullName);report["passed"]=false;report["error"]=e.ToString();return 1;}
    finally {
      if(handler!=null && page!=null){try{Automation.RemoveAutomationEventHandler(TextPattern.TextSelectionChangedEvent,page,handler);}catch{}}
      if(process!=null && !process.HasExited){process.CloseMainWindow();if(!process.WaitForExit(15000)){process.Kill();process.WaitForExit();report["forced_cleanup"]=true;}}
      if(args.Length>1){Directory.CreateDirectory(args[1]);File.WriteAllText(Path.Combine(args[1],"report.json"),new JavaScriptSerializer().Serialize(report));}
      Console.WriteLine(new JavaScriptSerializer().Serialize(report));
    }
  }
}
