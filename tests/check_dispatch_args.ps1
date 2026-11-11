param(
  [Parameter(Mandatory)][string]$DispatchPath,
  [Parameter(Mandatory)][string]$EchoExe,
  [Parameter(Mandatory)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $DispatchPath),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$function=$ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'ConvertTo-ArgLine'},$true)
if ($function.Count -ne 1) { throw 'Expected one actual ConvertTo-ArgLine definition' }
Invoke-Expression $function[0].Extent.Text
$values=[Collections.Generic.List[string]]::new()
foreach ($s in @('', 'plain', 'two words', 'a"b', 'C:\space dir\', 'C:\plain\', '中文参数', "line1`nline2", "line1`r`nline2", "`t", '\"', '\\"', 'end\\', '"', '--leading')) { $values.Add($s) }
# Exhaust all strings of length 1..3 over delimiter/escape/Unicode characters.
$alphabet=@('a',' ','\','"',"`t","`n",'中')
$level=@('')
foreach ($depth in 1..3) {
  $next=@(foreach ($prefix in $level) { foreach ($c in $alphabet) { $prefix+$c } })
  foreach ($s in $next) { $values.Add($s) }
  $level=$next
}
$argLine=($values | ForEach-Object { ConvertTo-ArgLine $_ }) -join ' '
$temporary=Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString()+'.json')
try {
  $proc=Start-Process -FilePath $EchoExe -ArgumentList $argLine -RedirectStandardOutput $temporary -WindowStyle Hidden -PassThru
  $proc.WaitForExit()
  if ($proc.ExitCode -ne 0) { throw "echo exited $($proc.ExitCode)" }
  $actual=@(Get-Content -Raw $temporary | ConvertFrom-Json)
  if ($actual.Count -ne $values.Count) { throw "argc: expected=$($values.Count) actual=$($actual.Count)" }
  $mismatches=@(for ($i=0;$i -lt $values.Count;$i++) {
    if (-not [string]::Equals($values[$i],$actual[$i],[StringComparison]::Ordinal)) { [ordered]@{index=$i;expected=$values[$i];actual=$actual[$i]} }
  })
  [ordered]@{passed=($mismatches.Count -eq 0);count=$values.Count;dispatch_sha256=(Get-FileHash $DispatchPath -Algorithm SHA256).Hash;examples=@($values.GetRange(0,15));actual_examples=@($actual[0..14]);mismatches=$mismatches;command_line=$argLine} |
    ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $OutputPath
  if ($mismatches.Count) { throw "$($mismatches.Count) argument mismatches; see $OutputPath" }
  "PASS: CRT argc=$($actual.Count); all argument boundaries and UTF-16 code units match"
} finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
