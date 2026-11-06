param([Parameter(Mandatory=$true)][int]$Port)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSEdition -eq 'Core'){
    & 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -File $PSCommandPath -Port $Port
    exit $LASTEXITCODE
}
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$run=Join-Path $root ('reports/completion_20261101/dashboard_batches_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $run|Out-Null
Add-Type -Path 'C:/Program Files (x86)/Microsoft SQL Server Management Studio 20/Common7/IDE/Microsoft.AnalysisServices.AdomdClient.dll'
$connection=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$results=@()
try{
 $connection.Open()
 foreach($page in @('01_executive_overview','02_sales_product_performance','03_customer_geographic_analytics','04_delivery_logistics','05_reviews_satisfaction')){
  $source=Get-Content (Join-Path $root ('power_bi/dashboards/'+$page+'/validation.dax')) -Raw
  $number=0
  foreach($batch in [regex]::Split($source,'(?m)(?=^EVALUATE\b)')){
   if($batch -notmatch '^EVALUATE'){continue};$number++
   $timer=[System.Diagnostics.Stopwatch]::StartNew()
   try{
    $command=$connection.CreateCommand();$command.CommandText=$batch;$command.CommandTimeout=120
    $adapter=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter($command)
    $table=New-Object System.Data.DataTable;[void]$adapter.Fill($table)
    $rows=@();$differences=@()
    foreach($record in $table.Rows){
     $row=[ordered]@{}
     foreach($column in $table.Columns){$key=$column.ColumnName;$value=$record[$key];if($value -is [DBNull]){$value=$null};$row[$key]=$value
      if($key -match 'Difference' -and $null -ne $value){$differences+=[pscustomobject]@{Column=$key;Value=$value;Status=$(if([Math]::Abs([double]$value) -le 0.005){'PASS'}else{'FAIL'})}}
     }
     $rows+=[pscustomobject]$row
    }
    $timer.Stop();$status=if(@($differences|Where-Object Status -eq 'FAIL').Count){'FAIL'}else{'PASS'}
    $results+=[pscustomobject]@{Page=$page;Batch=$number;Status=$status;Milliseconds=$timer.ElapsedMilliseconds;RowCount=$table.Rows.Count;DifferenceChecks=$differences;Rows=$rows}
   }catch{$timer.Stop();$results+=[pscustomobject]@{Page=$page;Batch=$number;Status='FAIL';Error=$_.Exception.Message}}
  }
 }
}finally{if($connection.State -eq 'Open'){$connection.Close()}}
$summary=[pscustomobject]@{Scope='Executed page validation query batches and numeric Difference checks; UI rendering not tested';Passed=@($results|Where-Object Status -eq 'PASS').Count;Failed=@($results|Where-Object Status -eq 'FAIL').Count;Batches=$results}
$summary|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $run 'results.json') -Encoding UTF8
Join-Path $run 'results.json'
if($summary.Failed){throw 'Dashboard query batch failures; inspect evidence.'}
