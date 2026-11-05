# SPDX-License-Identifier: MIT
# UI Automation client for the drive, run in Windows PowerShell, which ships
# the managed client. Lists the elements of a process's main window as
# "type<TAB>automation id<TAB>name" lines into -Out, or with -Invoke invokes
# the first element whose name matches the wildcard pattern.
param(
  [Parameter(Mandatory)] [int] $ProcessId,
  [string] $Invoke,
  [string] $Out
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$Element = [System.Windows.Automation.AutomationElement]
$condition = New-Object System.Windows.Automation.PropertyCondition($Element::ProcessIdProperty, $ProcessId)
$window = $Element::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if (-not $window) { 'no window'; exit 2 }
$all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
if ($Invoke) {
  foreach ($e in $all) {
    if ($e.Current.Name -like $Invoke) {
      $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
      "invoked $($e.Current.Name)"
      exit 0
    }
  }
  "no element named $Invoke"
  exit 3
}
$lines = foreach ($e in $all) { '{0}{3}{1}{3}{2}' -f $e.Current.ControlType.ProgrammaticName, $e.Current.AutomationId, $e.Current.Name, "`t" }
[System.IO.File]::WriteAllLines($Out, [string[]]@($lines), (New-Object System.Text.UTF8Encoding $false))
