param([Parameter(Mandatory=$true)][int]$Port)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSEdition -eq 'Core'){
    & 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -File $PSCommandPath -Port $Port
    exit $LASTEXITCODE
}
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$evidence=Join-Path $root 'reports/completion_20261101'
$run=Join-Path $evidence ('top10_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $run|Out-Null
Add-Type -Path 'C:/Program Files (x86)/Microsoft SQL Server Management Studio 20/Common7/IDE/Microsoft.AnalysisServices.AdomdClient.dll'
$connection=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$results=@()
try{
 $connection.Open()
 $source=Get-Content (Join-Path $evidence 'top10_cases.json') -Raw|ConvertFrom-Json
 foreach($case in $source.cases){
  $command=$connection.CreateCommand();$command.CommandText=$case.dax;$command.CommandTimeout=120
  $adapter=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter($command)
  $table=New-Object System.Data.DataTable;[void]$adapter.Fill($table)
  $actual=@();foreach($row in $table.Rows){$actual+=[pscustomobject]@{label=[string]$row[0];volume=[long]$row[1]}}
  $ok=$actual.Count -eq 10 -and $actual.Count -eq $case.expected.Count
  for($i=0;$i -lt [Math]::Min($actual.Count,$case.expected.Count);$i++){if($actual[$i].label -ne $case.expected[$i].label -or $actual[$i].volume -ne $case.expected[$i].volume){$ok=$false}}
  $results+=[pscustomobject]@{Name=$case.name;Status=$(if($ok){'PASS'}else{'FAIL'});Actual=$actual;Expected=$case.expected;DAX=$case.dax}
 }
}finally{if($connection.State -eq 'Open'){$connection.Close()}}
$summary=[pscustomobject]@{Passed=@($results|Where-Object Status -eq 'PASS').Count;Failed=@($results|Where-Object Status -eq 'FAIL').Count;Cases=$results}
$summary|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $run 'results.json') -Encoding UTF8
Join-Path $run 'results.json'
if($summary.Failed){throw 'Top-10 gate reconciliation failed.'}
