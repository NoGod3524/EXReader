# SPDX-License-Identifier: MIT
# Drives EXReader Studio through its own window: open EPUB, PDF and CBZ from the
# shelf, zoom the PDF and pan it by wheel and drag, switch the EPUB through night
# and day themes, change its font size and spacing, jump through its table of
# contents, turn pages, go back to the shelf, reopen, resize the window,
# favorite and remove a book through the context menu, use it by keyboard and
# through UI Automation, import through the open-file dialog, and close.
# Real mouse and keyboard input first; if the desktop does not deliver it, the
# same messages are posted to the window and the result says so.
# Every check reads the --trace state the app writes after it paints.
param(
  [Parameter(Mandatory)] [string] $Exe,
  [Parameter(Mandatory)] [string] $Data,
  [Parameter(Mandatory)] [string] $Out,
  [Parameter(Mandatory)] [string[]] $Books
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Win {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint x, uint y, int data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int ht, uint flags);
}
'@

New-Item -ItemType Directory -Force $Out | Out-Null
$trace = Join-Path $Out 'trace.txt'
$result = Join-Path $Out 'drive.txt'
Remove-Item -Force -ErrorAction SilentlyContinue $trace, $result
# Logs to the result file and the job log without adding to any function output.
function Note([string] $line) { Add-Content -LiteralPath $result -Value $line; Write-Host $line }

# Last complete block of the trace: a state line, hot lines, then 'end'.
function Read-State {
  if (-not (Test-Path $trace)) { return $null }
  $lines = @(Get-Content -LiteralPath $trace -Encoding UTF8)
  $end = [Array]::LastIndexOf($lines, 'end')
  if ($end -lt 0) { return $null }
  $start = $end - 1
  while ($start -ge 0 -and -not $lines[$start].StartsWith('state ')) { $start-- }
  if ($start -lt 0) { return $null }
  $state = @{ hots = @(); raw = $lines[$start] }
  foreach ($pair in $lines[$start].Substring(6).Split(' ')) {
    $kv = $pair.Split('=', 2)
    if ($kv.Count -eq 2) { $state[$kv[0]] = $kv[1] }
  }
  foreach ($line in $lines[($start + 1)..($end - 1)]) {
    if ($start + 1 -gt $end - 1) { break }
    $f = $line.Split(' ')
    $state.hots += [pscustomobject]@{ id = [int]$f[1]; arg = [long]$f[2]; x = [int]$f[3]; y = [int]$f[4]
      w = $(if ($f.Count -gt 5) { [int]$f[5] } else { 0 }) }
  }
  $state
}

function Wait-State([scriptblock] $test, [string] $what, [int] $seconds = 20) {
  $deadline = (Get-Date).AddSeconds($seconds)
  do {
    $s = Read-State
    if ($s -and (& $test $s)) { return $s }
    Start-Sleep -Milliseconds 200
  } while ((Get-Date) -lt $deadline)
  $last = if ($s) { $s.raw } else { 'none' }
  throw "timeout waiting for $what; last state: $last"
}

function Near([string] $hex, [int] $rgb, [int] $tolerance = 8) {
  if ($hex -notmatch '^[0-9A-F]{6}$') { return $false }
  $v = [Convert]::ToInt32($hex, 16)
  foreach ($shift in 16, 8, 0) {
    if ([Math]::Abs((($v -shr $shift) -band 255) - (($rgb -shr $shift) -band 255)) -gt $tolerance) { return $false }
  }
  $true
}

$HotBook = 6; $HotBack = 8; $HotStyle = 9; $HotFontUp = 11; $HotSpacing = 12; $HotTheme = 13; $HotZoomUp = 15
$HotToc = 21; $HotTocItem = 22
$HotNavAll = 1; $HotNavRecent = 2; $HotNavFavorites = 3; $HotAppearance = 5; $HotTrack = 16; $HotSearch = 20
$HotConfirm = 24; $HotConfirmCancel = 25; $HotMenuItem = 28
$script:input = 'sendinput'
$script:shot = 0

function Focus {
  if ([Win]::GetForegroundWindow() -ne $hwnd) {
    [Win]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [Win]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    [Win]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 150
  }
}

function Click-At([int] $x, [int] $y) {
  if ($script:input -eq 'sendinput') {
    Focus
    $p = New-Object Win+POINT; $p.X = $x; $p.Y = $y
    [Win]::ClientToScreen($hwnd, [ref]$p) | Out-Null
    [Win]::SetCursorPos($p.X, $p.Y) | Out-Null
    Start-Sleep -Milliseconds 80
    [Win]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 40
    [Win]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
  } else {
    $l = [IntPtr](($y -shl 16) -bor ($x -band 0xffff))
    [Win]::PostMessage($hwnd, 0x200, [IntPtr]0, $l) | Out-Null
    [Win]::PostMessage($hwnd, 0x201, [IntPtr]1, $l) | Out-Null
    [Win]::PostMessage($hwnd, 0x202, [IntPtr]0, $l) | Out-Null
  }
}

function Wheel-At([int] $x, [int] $y, [int] $delta) {
  $p = New-Object Win+POINT; $p.X = $x; $p.Y = $y
  [Win]::ClientToScreen($hwnd, [ref]$p) | Out-Null
  if ($script:input -eq 'sendinput') {
    Focus
    [Win]::SetCursorPos($p.X, $p.Y) | Out-Null
    Start-Sleep -Milliseconds 80
    [Win]::mouse_event(0x0800, 0, 0, $delta, [UIntPtr]::Zero)
  } else {
    [Win]::PostMessage($hwnd, 0x20A, [IntPtr]([long]($delta -band 0xffff) -shl 16), [IntPtr](($p.Y -shl 16) -bor ($p.X -band 0xffff))) | Out-Null
  }
}

# Press at one client point, move in steps, release at another.
function Drag([int] $x1, [int] $y1, [int] $x2, [int] $y2) {
  if ($script:input -eq 'sendinput') {
    Focus
    $p = New-Object Win+POINT; $p.X = $x1; $p.Y = $y1
    [Win]::ClientToScreen($hwnd, [ref]$p) | Out-Null
    $dx = $p.X - $x1; $dy = $p.Y - $y1
    [Win]::SetCursorPos($p.X, $p.Y) | Out-Null
    Start-Sleep -Milliseconds 80
    [Win]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)
    foreach ($k in 1..8) {
      Start-Sleep -Milliseconds 30
      [Win]::SetCursorPos($x1 + ($x2 - $x1) * $k / 8 + $dx, $y1 + ($y2 - $y1) * $k / 8 + $dy) | Out-Null
    }
    Start-Sleep -Milliseconds 60
    [Win]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
  } else {
    [Win]::PostMessage($hwnd, 0x201, [IntPtr]1, [IntPtr](($y1 -shl 16) -bor ($x1 -band 0xffff))) | Out-Null
    foreach ($k in 1..8) {
      $x = [int]($x1 + ($x2 - $x1) * $k / 8); $y = [int]($y1 + ($y2 - $y1) * $k / 8)
      [Win]::PostMessage($hwnd, 0x200, [IntPtr]1, [IntPtr](($y -shl 16) -bor ($x -band 0xffff))) | Out-Null
    }
    [Win]::PostMessage($hwnd, 0x202, [IntPtr]0, [IntPtr](($y2 -shl 16) -bor ($x2 -band 0xffff))) | Out-Null
  }
}

# Color of a client pixel in the window as it is on screen, as RRGGBB.
function Window-Pixel([int] $x, [int] $y) {
  $r = New-Object Win+RECT; [Win]::GetWindowRect($hwnd, [ref]$r) | Out-Null
  $o = New-Object Win+POINT; [Win]::ClientToScreen($hwnd, [ref]$o) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R - $r.L)), ([Math]::Max(1, $r.B - $r.T))
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $dc = $g.GetHdc(); [Win]::PrintWindow($hwnd, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $g.Dispose()
  $c = $bmp.GetPixel($o.X - $r.L + $x, $o.Y - $r.T + $y); $bmp.Dispose()
  '{0:X2}{1:X2}{2:X2}' -f $c.R, $c.G, $c.B
}

# A real right click on a shelf card, which opens the in-window book menu.
function Right-Click([int] $x, [int] $y) {
  Focus
  $p = New-Object Win+POINT; $p.X = $x; $p.Y = $y
  [Win]::ClientToScreen($hwnd, [ref]$p) | Out-Null
  [Win]::SetCursorPos($p.X, $p.Y) | Out-Null
  Start-Sleep -Milliseconds 80
  [Win]::mouse_event(8, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 40
  [Win]::mouse_event(0x10, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 500
}

# A key to whatever has focus: the main window, or with -Modal the menu or
# dialog the app has open, which must keep the foreground.
function Press([byte] $vk, [switch] $Modal) {
  if ($script:input -eq 'sendinput' -or $Modal) {
    if (-not $Modal) { Focus }
    [Win]::keybd_event($vk, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 40
    [Win]::keybd_event($vk, 0, 2, [UIntPtr]::Zero)
  } else {
    [Win]::PostMessage($hwnd, 0x100, [IntPtr]$vk, [IntPtr]1) | Out-Null
    [Win]::PostMessage($hwnd, 0x101, [IntPtr]$vk, [IntPtr]0xC0000001L) | Out-Null
  }
}

# The screen over the window, so menus and dialogs the app opens are included.
function Screen-Shot([string] $name) {
  $script:shot++
  try {
    $r = New-Object Win+RECT; [Win]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R - $r.L)), ([Math]::Max(1, $r.B - $r.T))
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size); $g.Dispose()
    $bmp.Save((Join-Path $Out ('{0:D2}-{1}.png' -f $script:shot, $name))); $bmp.Dispose()
  } catch { Note "screenshot $name failed: $($_.Exception.Message)" }
}

function Shot([string] $name) {
  $script:shot++
  Start-Sleep -Milliseconds 400 # let the page fade finish
  try {
    $r = New-Object Win+RECT; [Win]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R - $r.L)), ([Math]::Max(1, $r.B - $r.T))
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc(); [Win]::PrintWindow($hwnd, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $g.Dispose()
    $path = Join-Path $Out ('{0:D2}-{1}.png' -f $script:shot, $name)
    $bmp.Save($path); $bmp.Dispose()
    (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
  } catch { Note "screenshot $name failed: $($_.Exception.Message)" }
}

# One action whose effect the trace must show. The first action that real
# input fails to deliver switches the whole run to posted messages, once.
function Act([scriptblock] $action, [scriptblock] $test, [string] $what) {
  & $action
  try { return Wait-State $test $what 15 }
  catch {
    if ($script:input -ne 'sendinput') { throw }
    $script:input = 'post'
    Note "input=post (real input not delivered for: $what)"
    & $action
    return Wait-State $test $what 15
  }
}

function Hot-Center($state, [int] $id, [long] $arg = -1) {
  $h = $state.hots | Where-Object { $_.id -eq $id -and ($arg -lt 0 -or $_.arg -eq $arg) } | Select-Object -First 1
  if (-not $h) { throw "control $id/$arg not on screen; state: $($state.raw)" }
  $h
}

# The shelf card for a book, scrolled fully into view with the wheel if needed.
function Find-Card([long] $id) {
  foreach ($delta in 0, -120, -120, -120, -120, 120, 120, 120, 120, 120, 120, 120, 120) {
    if ($delta) {
      $r = New-Object Win+RECT; [Win]::GetClientRect($hwnd, [ref]$r) | Out-Null
      $p = New-Object Win+POINT; $p.X = [int]($r.R / 2); $p.Y = [int]($r.B / 2)
      [Win]::ClientToScreen($hwnd, [ref]$p) | Out-Null
      [Win]::PostMessage($hwnd, 0x20A, [IntPtr]([long]($delta -band 0xffff) -shl 16), [IntPtr](($p.Y -shl 16) -bor ($p.X -band 0xffff))) | Out-Null
      Start-Sleep -Milliseconds 900
    }
    $r = New-Object Win+RECT; [Win]::GetClientRect($hwnd, [ref]$r) | Out-Null
    $card = (Read-State).hots | Where-Object { $_.id -eq $HotBook -and $_.arg -eq $id -and $_.y -gt 120 -and $_.y -lt $r.B - 40 } |
      Select-Object -First 1
    if ($card) { return $card }
  }
  throw "shelf card for book $id never came into view; state: $((Read-State).raw)"
}

$app = Start-Process -FilePath $Exe -PassThru -ArgumentList (@('--data', "`"$Data`"", '--trace', "`"$trace`"") + ($Books | ForEach-Object { "`"$_`"" }))
$failed = $false
try {
  $deadline = (Get-Date).AddSeconds(30)
  while ($app.MainWindowHandle -eq 0 -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200; $app.Refresh() }
  $hwnd = $app.MainWindowHandle
  if ($hwnd -eq 0) { throw 'no main window' }
  [Win]::ShowWindow($hwnd, 3) | Out-Null
  $n = $Books.Count
  $shelf = Wait-State { param($s) $s.view -eq 'shelf' -and [int]$s.books -eq $n } "$n books on the shelf" 60
  Shot 'shelf' | Out-Null

  $db = Join-Path $Data 'library.sqlite'
  # The probe EPUB is the one titled 'Studio Probe'; formats are exr_format values.
  $rows = python -I -c "import sqlite3,sys; [print(r[0],r[1],{'Studio Probe':'probe','Cover import':'cover'}.get(r[2],'-'),r[3] or '-') for r in sqlite3.connect(sys.argv[1]).execute('select id,format,title,author from books')]" $db
  # The author chain, from the file itself: OPF dc:creator, then library, then UI.
  $probe = $Books | Where-Object { $_ -like '*probe.epub' } | Select-Object -First 1
  $creator = python -I -c "import re,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print(';'.join(c for n in z.namelist() if n.endswith('.opf') for c in re.findall(r'<dc:creator[^>]*>([^<]*)', z.read(n).decode())) or '-')" $probe
  Note "epub_creator_in_file=$creator"
  $ids = @{}
  foreach ($row in $rows) {
    $f = $row.Split(' ', 4)
    $name = @{ '8' = 'PDF'; '9' = 'CBZ' }[$f[1]]
    if ($f[1] -eq '4' -and $f[2] -eq 'probe') { $name = 'EPUB'; Note "epub_author_in_library=$($f[3])" }
    if ($f[1] -eq '4' -and $f[2] -eq 'cover') { $name = 'COVER' }
    if ($name -and -not $ids[$name]) { $ids[$name] = [long]$f[0] }
  }

  $paper = @{ 0 = 0xFFFFFF; 1 = 0xF7EFDD; 2 = 0xE4EDDA; 3 = 0x1E1F22 }

  # pictures=center:corner,... from the trace; the probe EPUB's first page holds
  # the opaque red picture, then the green one inside a transparent frame.
  function Pictures-Right($s, [int] $theme) {
    if (-not $s.pictures -or $s.pictures -eq 'none') { return $false }
    $p = @($s.pictures.Split(',') | ForEach-Object { , $_.Split(':') })
    $p.Count -ge 2 -and (Near $p[0][0] 0xFF0000) -and (Near $p[0][1] 0xFF0000) -and
      (Near $p[1][0] 0x00A000) -and (Near $p[1][1] $paper[$theme])
  }

  function Open-Book([long] $id, [string] $format, [scriptblock] $extra) {
    $card = Find-Card $id
    $s = Act { Click-At $card.x $card.y } { param($s) $s.view -eq 'reader' -and [long]$s.book -eq $id -and
      $s.opening -eq '0' -and [int]$s.ink -gt 0 -and $s.frame -ne '00000000' -and (& $extra $s) } "$format opened"
    if ($s.format -ne $format) { throw "opened $($s.format), expected $format" }
    $s
  }

  # Every reading panel shows the theme row; PDF and CBZ show zoom instead of font size.
  function Open-Panel {
    Act { $b = Hot-Center (Read-State) $HotStyle; Click-At $b.x $b.y } {
      param($s) $s.panel -eq '1' -and ($s.hots | Where-Object { $_.id -eq $HotTheme }) } 'style panel'
  }

  # Clicks a panel control and waits until the setting and the shown page both changed.
  function Restyle([int] $id, [long] $arg, [string] $key, [string] $value, [string] $what) {
    $before = Read-State
    $shotBefore = Shot "$what-before"
    $b = Hot-Center $before $id $arg
    $s = Act { Click-At $b.x $b.y } { param($s) $s.$key -eq $value -and $s.opening -eq '0' -and
      $s.frame -ne $before.frame -and $s.frame -ne '00000000' } $what
    $shotAfter = Shot $what
    if ($shotBefore -and $shotBefore -eq $shotAfter) { throw "$what changed the page bitmap but not the window" }
    Note "$what=$value frame=$($before.frame)->$($s.frame) size=$($before.size)->$($s.size) count=$($s.count) window_differs=$($shotBefore -ne $shotAfter)"
    $s
  }

  function Turn-Two([string] $format) {
    $from = [int](Read-State).page
    foreach ($page in ($from + 1), ($from + 2)) {
      Act { Press 0x27 } { param($s) $s.page -eq "$page" -and $s.opening -eq '0' -and [int]$s.ink -gt 0 } "$format page $page" | Out-Null
    }
    Note "turn_$format=$from,$($from + 1),$($from + 2)"
    Read-State
  }

  function Back([string] $format) {
    $b = Hot-Center (Read-State) $HotBack
    Act { Click-At $b.x $b.y } { param($s) $s.view -eq 'shelf' -and ($s.hots | Where-Object { $_.id -eq $HotBook }) } "$format back to shelf" | Out-Null
    Note "back_$format=ok"
  }

  # Reopening must show the same page with the same settings, pixel for pixel.
  function Reopen([long] $id, [string] $format, $left) {
    $s = Open-Book $id $format { param($s) $true }
    foreach ($key in 'page', 'font', 'spacing', 'zoom', 'theme', 'size', 'frame') {
      if ($s.$key -ne $left.$key) { throw "$format reopened with $key=$($s.$key), left with $($left.$key)" }
    }
    Note "reopen_$format=ok page=$($s.page) font=$($s.font) spacing=$($s.spacing) zoom=$($s.zoom) frame=$($s.frame)"
    Shot "$format-reopen" | Out-Null
  }

  # Shelf: dark mode both ways, search, the Recent filter and its empty state.
  $client = New-Object Win+RECT; [Win]::GetClientRect($hwnd, [ref]$client) | Out-Null
  foreach ($mode in @(@{ dark = '1'; window = 0x16171A }, @{ dark = '0'; window = 0xF7F5F1 })) {
    $b = Hot-Center (Read-State) $HotAppearance
    Act { Click-At $b.x $b.y } { param($s) $s.dark -eq $mode.dark } "dark mode $($mode.dark)" | Out-Null
    Start-Sleep -Milliseconds 500
    $pixel = Window-Pixel ($client.R - 12) ($client.B - 12)
    if (-not (Near $pixel $mode.window)) { throw "shelf background in dark=$($mode.dark) is $pixel" }
    Note "shelf_dark_$($mode.dark)=ok background=$pixel"
    Shot "shelf-dark$($mode.dark)" | Out-Null
    if ($mode.dark -eq '1') {
      # The book menu and removal confirmation in dark mode, for review.
      $card = Find-Card $ids.EPUB
      Right-Click $card.x $card.y
      Wait-State { param($s) $s.menu -eq "$($ids.EPUB)" } 'dark book menu' | Out-Null
      Shot 'shelf-dark-menu' | Out-Null
      $item = Hot-Center (Read-State) $HotMenuItem 2
      Click-At $item.x $item.y
      Wait-State { param($s) $s.confirm -eq "$($ids.EPUB)" } 'dark removal confirmation' | Out-Null
      Shot 'shelf-dark-confirm' | Out-Null
      Act { Press 0x1B } { param($s) $s.confirm -eq '0' -and [int]$s.books -eq $n } 'dark confirmation cancelled' | Out-Null
    }
  }
  $search = Hot-Center (Read-State) $HotSearch
  Click-At $search.x $search.y
  Start-Sleep -Milliseconds 200
  foreach ($vk in [byte][char]'P', [byte][char]'R', [byte][char]'O', [byte][char]'B', [byte][char]'E') { Press $vk }
  $found = Wait-State { param($s) $s.match -eq '2' -and @($s.hots | Where-Object { $_.id -eq $HotBook }).Count -eq 2 } 'search "probe" shows 2 books'
  Note "search_probe=$($found.match)"
  Shot 'shelf-search' | Out-Null
  foreach ($k in 1..5) { Press 0x08 }
  Wait-State { param($s) $s.match -eq "$n" } 'search cleared' | Out-Null
  $b = Hot-Center (Read-State) $HotNavRecent
  Act { Click-At $b.x $b.y } { param($s) $s.filter -eq '1' -and $s.match -eq '0' } 'Recent filter, nothing read yet' | Out-Null
  Shot 'shelf-recent-empty' | Out-Null
  $b = Hot-Center (Read-State) $HotNavAll
  Act { Click-At $b.x $b.y } { param($s) $s.filter -eq '0' -and $s.match -eq "$n" } 'All filter' | Out-Null
  Note 'shelf_filters=ok'
  $card = Find-Card $ids.COVER
  Right-Click $card.x $card.y
  Wait-State { param($s) $s.menu -eq "$($ids.COVER)" -and $s.row -eq '-1' } 'book menu open' | Out-Null
  Act { Press 0x1B } { param($s) $s.menu -eq '0' } 'Esc closes the book menu' | Out-Null
  Right-Click $card.x $card.y
  Wait-State { param($s) $s.menu -eq "$($ids.COVER)" -and $s.hover -ne "$HotBook" } 'book menu open, card hover cleared' | Out-Null
  Shot 'shelf-menu' | Out-Null
  Press 0x28; Press 0x28
  Wait-State { param($s) $s.row -eq '1' } 'menu row on favorite' | Out-Null
  Press 0x0D # Enter on the favorite item
  $b = Hot-Center (Read-State) $HotNavFavorites
  Act { Click-At $b.x $b.y } { param($s) $s.filter -eq '2' -and $s.match -eq '1' -and
    ($s.hots | Where-Object { $_.id -eq $HotBook -and $_.arg -eq $ids.COVER }) } 'favorite shows in Favorites' | Out-Null
  Shot 'shelf-favorites' | Out-Null
  $b = Hot-Center (Read-State) $HotNavAll
  Act { Click-At $b.x $b.y } { param($s) $s.filter -eq '0' -and $s.match -eq "$n" } 'All filter' | Out-Null
  # Remove through the in-window confirmation: Esc cancels, the Cancel button
  # cancels, then Tab moves focus from Cancel to Remove and Enter removes.
  function Ask-Remove {
    $card = Find-Card $ids.COVER
    Right-Click $card.x $card.y
    Wait-State { param($s) $s.menu -eq "$($ids.COVER)" } 'book menu open' | Out-Null
    $item = Hot-Center (Read-State) $HotMenuItem 2
    Click-At $item.x $item.y # the remove item, by mouse
    Wait-State { param($s) $s.confirm -eq "$($ids.COVER)" -and $s.focus -eq '0' -and $s.search -eq '0' } 'removal confirmation, search box hidden'
  }
  Ask-Remove | Out-Null
  Shot 'shelf-remove-confirm' | Out-Null
  Act { Press 0x1B } { param($s) $s.confirm -eq '0' -and [int]$s.books -eq $n -and $s.search -eq '1' } 'Esc cancels removal' | Out-Null
  $ask = Ask-Remove
  $b = Hot-Center $ask $HotConfirmCancel
  Act { Click-At $b.x $b.y } { param($s) $s.confirm -eq '0' -and [int]$s.books -eq $n } 'Cancel button keeps the book' | Out-Null
  Ask-Remove | Out-Null
  Act { Press 0x09 } { param($s) $s.focus -eq '1' } 'Tab to Remove' | Out-Null
  Shot 'shelf-remove-focus' | Out-Null
  $n = $n - 1
  Act { Press 0x0D } { param($s) $s.confirm -eq '0' -and [int]$s.books -eq $n -and $s.match -eq "$n" } 'Enter removes' | Out-Null
  Note "context_menu=favorite,remove(esc,cancel,enter) books=$n"

  # PDF: zoom in twice, turn, back, reopen.
  $s = Open-Book $ids.PDF 'PDF' { param($s) $s.page -eq '0' }
  Note "open_PDF=ok input=$($script:input) ink=$($s.ink) count=$($s.count) zoom=$($s.zoom) size=$($s.size)"
  Open-Panel | Out-Null
  $zoom = [int]$s.zoom
  $s = Restyle $HotZoomUp 0 'zoom' "$($zoom + 10)" 'PDF-zoom1'
  $s = Restyle $HotZoomUp 0 'zoom' "$($zoom + 20)" 'PDF-zoom2'
  Act { Press 0x1B } { param($s) $s.panel -eq '0' } 'panel closed' | Out-Null
  $s = Read-State
  $over = [int]$s.over.Split(',')[1]
  if ($over -le 0) { throw "PDF at zoom $($s.zoom) does not overflow the view: $($s.raw)" }
  $client = New-Object Win+RECT; [Win]::GetClientRect($hwnd, [ref]$client) | Out-Null
  $cx = [int]($client.R / 2); $cy = [int]($client.B / 2)
  $below = Window-Pixel $cx ($client.B - 6)
  if (-not (Near $below 0xECE9E3)) { throw "page shows under the bottom bar: $below" }
  Note "PDF_overflow=$($s.over) bottom_bar=$below"
  $s = Act { Wheel-At $cx $cy -120 } { param($s) $s.page -eq '0' -and [int]$s.pan.Split(',')[1] -gt 0 } 'PDF wheel pan'
  $wheelPan = [int]$s.pan.Split(',')[1]
  Shot 'PDF-wheel' | Out-Null
  $s = Act { Drag $cx $cy $cx ($cy + 40) } { param($s) $s.page -eq '0' -and [int]$s.pan.Split(',')[1] -lt $wheelPan } 'PDF drag pan'
  Note "PDF_pan wheel=0,$wheelPan drag=$($s.pan) page=$($s.page)"
  $s = Act { Wheel-At $cx $cy -120 } { param($s) $s.page -eq '0' -and $s.pan -eq "0,$over" } 'PDF pan to bottom'
  $s = Act { Wheel-At $cx $cy -120 } { param($s) $s.page -eq '1' -and $s.pan -eq '0,0' } 'PDF wheel turns at bottom'
  $s = Act { Wheel-At $cx $cy 120 } { param($s) $s.page -eq '0' -and $s.pan -eq "0,$over" } 'PDF wheel back enters at bottom'
  Note "PDF_edge_turn=0->1->0 enters_at=$($s.pan)"
  $left = Turn-Two 'PDF'
  Shot 'PDF-turned' | Out-Null
  Back 'PDF'
  Reopen $ids.PDF 'PDF' $left
  $track = Hot-Center (Read-State) $HotTrack
  $tx = [int]($track.x - $track.w / 2 + $track.w * 0.1)
  Act { Click-At $tx $track.y } { param($s) $s.page -eq '0' -and $s.opening -eq '0' } 'PDF progress bar jump' | Out-Null
  Note 'PDF_track_jump=page 0'
  Back 'PDF'

  # CBZ: open, turn, back.
  $s = Open-Book $ids.CBZ 'CBZ' { param($s) $s.page -eq '0' }
  Note "open_CBZ=ok input=$($script:input) ink=$($s.ink) count=$($s.count)"
  Turn-Two 'CBZ' | Out-Null
  Shot 'CBZ-turned' | Out-Null
  Back 'CBZ'

  # EPUB: pictures through day and night themes, font size and spacing, turn, back, reopen.
  $s = Open-Book $ids.EPUB 'EPUB' { param($s) $s.page -eq '0' }
  Note "open_EPUB=ok input=$($script:input) ink=$($s.ink) theme=$($s.theme) pictures=$($s.pictures)"
  Note "epub_author_in_ui=$($s.author)"
  if (-not (Pictures-Right $s ([int]$s.theme))) { throw "pictures wrong in theme $($s.theme): $($s.pictures) paper=$($s.paper)" }
  Shot 'EPUB-open' | Out-Null
  Open-Panel | Out-Null
  foreach ($theme in 3, 1, 0) {
    $b = Hot-Center (Read-State) $HotTheme $theme
    $t = Act { Click-At $b.x $b.y } { param($s) $s.theme -eq "$theme" -and (Near $s.paper $paper[$theme]) -and
      (Pictures-Right $s $theme) } "theme $theme pictures"
    Note "theme_$theme paper=$($t.paper) pictures=$($t.pictures)"
    Shot "EPUB-theme$theme" | Out-Null
    if ($theme -eq 3) {
      # The contents drawer in the night theme, for review; then back to the panel.
      $b = Hot-Center (Read-State) $HotToc
      Act { Click-At $b.x $b.y } { param($s) $s.tocopen -eq '1' -and $s.panel -eq '0' } 'night contents' | Out-Null
      Shot 'EPUB-night-contents' | Out-Null
      Act { Press 0x1B } { param($s) $s.tocopen -eq '0' } 'night contents closed' | Out-Null
      Open-Panel | Out-Null
    }
  }
  $font = [int](Read-State).font
  Restyle $HotFontUp 0 'font' "$($font + 1)" 'EPUB-font1' | Out-Null
  Restyle $HotFontUp 0 'font' "$($font + 2)" 'EPUB-font2' | Out-Null
  $spacing = if ((Read-State).spacing -eq '2') { 0 } else { 2 }
  Restyle $HotSpacing $spacing 'spacing' "$spacing" 'EPUB-spacing' | Out-Null
  Act { Press 0x1B } { param($s) $s.panel -eq '0' } 'panel closed' | Out-Null
  $s = Read-State
  if ($s.toc -ne '4' -or $s.current -ne '0') { throw "contents: expected 4 entries at entry 0, got $($s.raw)" }
  $pages = @{}
  foreach ($entry in 2, 3, 1) {
    Act { $b = Hot-Center (Read-State) $HotToc; Click-At $b.x $b.y } {
      param($s) $s.tocopen -eq '1' -and ($s.hots | Where-Object { $_.id -eq $HotTocItem }) } 'contents open' | Out-Null
    Shot "EPUB-contents$entry" | Out-Null
    $item = Hot-Center (Read-State) $HotTocItem $entry
    $s = Act { Click-At $item.x $item.y } { param($s) $s.tocopen -eq '0' -and $s.current -eq "$entry" -and
      $s.opening -eq '0' -and [int]$s.ink -gt 0 } "contents entry $entry"
    $pages[$entry] = [int]$s.page
    Note "toc_entry_$entry=page $($s.page)"
  }
  if (-not ($pages[1] -lt $pages[2] -and $pages[2] -lt $pages[3] -and $pages[1] -gt 0)) {
    throw "contents pages out of order: 1=$($pages[1]) 2=$($pages[2]) 3=$($pages[3])"
  }
  Act { $b = Hot-Center (Read-State) $HotToc; Click-At $b.x $b.y } { param($s) $s.tocopen -eq '1' } 'contents open' | Out-Null
  Act { Press 0x1B } { param($s) $s.tocopen -eq '0' } 'contents closed by Esc' | Out-Null
  $left = Turn-Two 'EPUB'
  Shot 'EPUB-turned' | Out-Null
  Back 'EPUB'
  Reopen $ids.EPUB 'EPUB' $left
  $before = Read-State
  [Win]::ShowWindow($hwnd, 9) | Out-Null
  [Win]::SetWindowPos($hwnd, [IntPtr]::Zero, 40, 40, 960, 680, 0x0014) | Out-Null
  $small = Wait-State { param($s) $s.size -ne $before.size -and $s.opening -eq '0' -and [int]$s.ink -gt 0 -and
    $s.frame -ne $before.frame } 'relayout after resize'
  if ($small.current -ne $before.current) { throw "resize moved contents entry $($before.current) -> $($small.current)" }
  Note "resize=ok size=$($before.size)->$($small.size) current=$($small.current) page=$($before.page)->$($small.page)"
  Shot 'EPUB-resized' | Out-Null
  [Win]::ShowWindow($hwnd, 3) | Out-Null
  Wait-State { param($s) $s.size -eq $before.size -and $s.opening -eq '0' } 'relayout after maximize' | Out-Null
  Back 'EPUB'
  # Keyboard only: Tab to the probe EPUB on the shelf, Enter opens it; Tab to
  # Back, Enter returns. The focused control carries a ring.
  Act { Press 0x09 } { param($s) $s.kfocus -eq '1:0' } 'Tab focuses the first sidebar item' | Out-Null
  foreach ($k in 1..14) {
    if ((Read-State).kfocus -eq "6:$($ids.EPUB)") { break }
    Press 0x09
    Start-Sleep -Milliseconds 250
  }
  Wait-State { param($s) $s.kfocus -eq "6:$($ids.EPUB)" } 'Tab reaches the EPUB card' | Out-Null
  Shot 'shelf-keyboard-focus' | Out-Null
  Act { Press 0x0D } { param($s) $s.view -eq 'reader' -and [long]$s.book -eq $ids.EPUB -and $s.opening -eq '0' } 'Enter opens the focused book' | Out-Null
  Act { Press 0x09 } { param($s) $s.kfocus -eq '8:0' } 'Tab focuses Back in the reader' | Out-Null
  Shot 'reader-keyboard-focus' | Out-Null
  Act { Press 0x0D } { param($s) $s.view -eq 'shelf' } 'Enter on Back returns to the shelf' | Out-Null
  Note 'keyboard=tab to book, enter opens, tab to back, enter returns'

  # Screen readers: the same window through UI Automation, as Narrator sees it.
  $uia = Join-Path $PSScriptRoot 'uia.ps1'
  function Uia-Names([string] $what, [string[]] $need) {
    $file = Join-Path $Out "uia-$what.txt"
    $deadline = (Get-Date).AddSeconds(15)
    do {
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File $uia -ProcessId $app.Id -Out $file | Out-Null
      $names = if (Test-Path $file) { @(Get-Content -LiteralPath $file -Encoding UTF8 | ForEach-Object { $_.Split("`t")[-1] }) } else { @() }
      $missing = @($need | Where-Object { $want = $_; -not ($names | Where-Object { $_ -like $want }) })
      if (-not $missing.Count) { Note "uia_$what=ok elements=$($names.Count)"; return }
      Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "UI Automation $what lacks: $($missing -join ' | ')"
  }
  function Uia-Invoke([string] $pattern) {
    $said = powershell.exe -NoProfile -ExecutionPolicy Bypass -File $uia -ProcessId $app.Id -Invoke $pattern
    if ($LASTEXITCODE) { throw "UI Automation could not invoke $($pattern): $said" }
  }
  Uia-Names 'shelf' @('全部书籍', '导入书籍', '深色模式，已关闭', '搜索书名或作者', 'Studio Probe，*', 'probe，*', 'SDK Comic，*')
  $shelfTree = @(Get-Content -LiteralPath (Join-Path $Out 'uia-shelf.txt') -Encoding UTF8)
  $searchLine = $shelfTree | Where-Object { $_ -like '*搜索书名或作者' } | Select-Object -First 1
  $firstNav = [Array]::FindIndex([string[]]$shelfTree, [Predicate[string]] { param($l) $l -like '*全部书籍' })
  $firstBook = [Array]::FindIndex([string[]]$shelfTree, [Predicate[string]] { param($l) $l -like '*ListItem*' })
  if ($firstNav -lt 0 -or $firstBook -lt 0 -or $firstNav -gt $firstBook) { throw "shelf reading order: navigation at $firstNav, first book at $firstBook" }
  Note "uia_search=$($searchLine.Split("`t")[0]) shelf_order=navigation($firstNav) before books($firstBook)"
  Uia-Invoke 'Studio Probe，*'
  $s = Wait-State { param($s) $s.view -eq 'reader' -and [long]$s.book -eq $ids.EPUB -and $s.opening -eq '0' } 'UI Automation opened the EPUB'
  Uia-Names 'reader' @('返回书架', '阅读设置', '目录', '下一页', '*the quiet reader*', '阅读进度 *')
  $page = [int]$s.page
  Uia-Invoke '下一页'
  Wait-State { param($s) $s.page -eq "$($page + 1)" -and $s.opening -eq '0' } 'UI Automation next page' | Out-Null
  Uia-Invoke '目录'
  Wait-State { param($s) $s.tocopen -eq '1' } 'UI Automation contents' | Out-Null
  Uia-Names 'contents' @('Studio Probe', 'Chapter Two*', 'Part B*', 'Chapter Three*')
  Uia-Invoke 'Chapter Three*'
  Wait-State { param($s) $s.current -eq '3' -and $s.tocopen -eq '0' } 'UI Automation contents jump' | Out-Null
  Uia-Invoke '返回书架'
  Wait-State { param($s) $s.view -eq 'shelf' } 'UI Automation back to shelf' | Out-Null
  Note 'uia_actions=open,next page,contents,jump,back'

  # Import through the open-file dialog: Ctrl+O, paste a full path, Enter.
  $extra = (Resolve-Path (Join-Path $PSScriptRoot '../../../../tests/fixtures/complex-text.epub')).Path
  Press 0x1B # leave the search box if it has focus
  Set-Clipboard -Value $extra
  [Win]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); Press ([byte][char]'O'); [Win]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
  Start-Sleep -Seconds 2
  Screen-Shot 'import-dialog'
  [Win]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); Press ([byte][char]'V') -Modal; [Win]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 300
  Press 0x0D -Modal
  $n = $n + 1
  Wait-State { param($s) [int]$s.books -eq $n } 'book imported through the dialog' 30 | Out-Null
  Note "dialog_import=ok books=$n"
  Shot 'shelf-end' | Out-Null
} catch {
  $failed = $true
  Note "FAILED: $($_.Exception.Message)"
  if ($hwnd) { try { Shot 'failure' | Out-Null } catch {} }
}

taskkill /PID $app.Id | Out-Null
if (-not $app.WaitForExit(15000)) {
  Stop-Process -Id $app.Id -Force
  Note 'graceful_close=False'
  exit 1
}
$exited = (Get-Content -LiteralPath $trace -Tail 1) -eq 'exit'
Note "graceful_close=True exit_code=$($app.ExitCode) trace_exit=$exited"
$count = python -I -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from books').fetchone()[0])" (Join-Path $Data 'library.sqlite')
Note "library_books=$count expected=$($Books.Count) (one removed, one imported by dialog)"
if ($failed -or $app.ExitCode -ne 0 -or -not $exited -or [int]$count -ne $Books.Count) { exit 1 }
Note 'drive=passed'
