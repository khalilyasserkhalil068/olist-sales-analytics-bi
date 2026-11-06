param([int]$BaselinePort=0,[Parameter(Mandatory=$true)][int]$FinalPort,[string]$BaselineEvidence)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$run=Join-Path $root ('reports/completion_20261101/model_regression_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $run|Out-Null
$lib='C:/Program Files (x86)/Microsoft SQL Server Management Studio 20/Common7/IDE/'
Add-Type -Path ($lib+'Microsoft.AnalysisServices.Core.dll')
Add-Type -Path ($lib+'Microsoft.AnalysisServices.Tabular.dll')
Add-Type -Path ($lib+'Microsoft.AnalysisServices.AdomdClient.dll')
$baseline=Get-Content (Join-Path $root 'power_bi/reports/final_reopened_model_20261031.json') -Raw|ConvertFrom-Json
$measures=@($baseline.model.tables|ForEach-Object{$_.measures}|Where-Object{$null -ne $_ -and $_.name})
if($measures.Count -ne 33){throw 'Expected exactly 33 retained measure definitions.'}
$parts=@();$i=0
foreach($measure in $measures){$parts+=('"m'+$i+'", ['+$measure.name+']');$i++}
$q='EVALUATE ROW('+($parts -join ',')+', "orders", COUNTROWS(FactOrders), "items", COUNTROWS(FactOrderItems), "reviews", COUNTROWS(FactReviews), "payments", COUNTROWS(FactPayments))'
$entries=@()
if($BaselinePort){$entries+=@{Name='baseline_current';Port=$BaselinePort}}
else{
 if(!$BaselineEvidence){throw 'Provide the verified baseline evidence directory when its Desktop instance is closed.'}
 foreach($name in @('baseline_current_model.json','baseline_current_values.json')){Copy-Item -LiteralPath (Join-Path $BaselineEvidence $name) -Destination (Join-Path $run $name)}
}
$entries+=@{Name='final_current';Port=$FinalPort}
foreach($entry in $entries){
 $server=New-Object Microsoft.AnalysisServices.Tabular.Server
 $connection=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$($entry.Port)")
 try{
  $server.Connect("localhost:$($entry.Port)")
  [Microsoft.AnalysisServices.Tabular.JsonSerializer]::SerializeDatabase($server.Databases[0])|Set-Content -LiteralPath (Join-Path $run ($entry.Name+'_model.json')) -Encoding UTF8
  $connection.Open();$command=$connection.CreateCommand();$command.CommandText=$q
  $adapter=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter($command);$table=New-Object System.Data.DataTable;[void]$adapter.Fill($table)
  $rows=@();foreach($r in $table.Rows){$row=[ordered]@{};foreach($c in $table.Columns){$v=$r[$c.ColumnName];if($v -is [DBNull]){$v=$null};$row[$c.ColumnName.Trim('[',']')]=$v};$rows+=[pscustomobject]$row}
  ConvertTo-Json -InputObject $rows -Depth 8|Set-Content -LiteralPath (Join-Path $run ($entry.Name+'_values.json')) -Encoding UTF8
 }finally{if($connection.State -eq 'Open'){$connection.Close()};if($server.Connected){$server.Disconnect()}}
}
ConvertTo-Json -InputObject @($measures|Select-Object name) -Depth 5|Set-Content -LiteralPath (Join-Path $run 'measure_order.json') -Encoding UTF8
Write-Output $run
