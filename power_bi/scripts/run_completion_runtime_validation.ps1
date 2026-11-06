param([Parameter(Mandatory=$true)][ValidateRange(1,65535)][int]$Port)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSEdition -eq 'Core'){
    # Installed SSMS ADOMD/TOM assemblies target .NET Framework.
    & 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -File $PSCommandPath -Port $Port
    exit $LASTEXITCODE
}
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$evidence=Join-Path $root 'reports/completion_20261101'
$run=Join-Path $evidence ('runtime_'+(Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $run | Out-Null
$lib='C:/Program Files (x86)/Microsoft SQL Server Management Studio 20/Common7/IDE/'
Add-Type -Path ($lib+'Microsoft.AnalysisServices.Core.dll')
Add-Type -Path ($lib+'Microsoft.AnalysisServices.Tabular.dll')
Add-Type -Path ($lib+'Microsoft.AnalysisServices.AdomdClient.dll')
$server=New-Object Microsoft.AnalysisServices.Tabular.Server
$connection=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$results=@();$modelChecks=@();$errorText=$null
try {
    $server.Connect("localhost:$Port")
    if($server.Databases.Count -ne 1){throw 'Expected one Desktop model; select the intended local port.'}
    $db=$server.Databases[0];$model=$db.Model
    $baseline=Get-Content (Join-Path $root 'power_bi/reports/final_reopened_model_20261031.json') -Raw | ConvertFrom-Json
    $originals=@($baseline.model.tables | ForEach-Object {$tableName=$_.name;foreach($measure in $_.measures){[pscustomobject]@{Table=$tableName;Name=$measure.name;Expression=$measure.expression;Format=$measure.formatString}}})
    if($model.Tables.Count -ne 31 -or $model.Relationships.Count -ne 37){throw 'Wrong model structure: expected 31 tables and 37 relationships.'}
    if(@($model.Tables | ForEach-Object {$_.Measures}).Count -ne 58){throw 'Expected 58 measures after loading the authored TMDL. Close and reopen the correct generated PBIP first.'}
    foreach($entry in $originals){
        $live=$model.Tables[$entry.Table].Measures[$entry.Name]
        $expectedExpression=$entry.Expression
        if($entry.Name -eq 'Show Top 5 Trend Categories' -and $model.Tables['DimDate'].Columns.Contains('MonthStartDate')){
            $expectedExpression=$entry.Expression.Replace('ALLSELECTED(DimDate[YearMonth])','ALLSELECTED(DimDate[YearMonth], DimDate[MonthStartDate])')
        }
        if(!$live -or $live.Expression -ne $expectedExpression -or [string]$live.FormatString -ne [string]$entry.Format){throw ('Original measure mismatch: '+$entry.Name)}
    }
    $modelChecks+=[pscustomobject]@{Name='31 tables, 37 relationships, 58 measures; 32 unchanged prior measures and one exact monthly-axis gate extension';Status='PASS'}
    foreach($table in $model.Tables){
        foreach($measure in $table.Measures){if($measure.ErrorMessage){throw ('DAX model error: '+$table.Name+'['+$measure.Name+']: '+$measure.ErrorMessage)}}
        foreach($column in $table.Columns){if($column.ErrorMessage){throw ('Column error: '+$table.Name+'['+$column.Name+']: '+$column.ErrorMessage)}}
    }
    [Microsoft.AnalysisServices.Tabular.JsonSerializer]::SerializeDatabase($db) | Set-Content -LiteralPath (Join-Path $run 'live_model.json') -Encoding UTF8
    $connection.Open()
    $definitions=Get-Content (Join-Path $evidence 'runtime_cases.json') -Raw | ConvertFrom-Json
    $countMeasures=@('[Order Count]','[Unique Sales Customers]','[Repeat Sales Customers]','[Delivered Orders]','[Timeliness Eligible Orders]','[On Time Deliveries]','[Late Deliveries]','[Duration Eligible Orders]','[Total Valid Reviews]','[Category Valid Reviews]','[Category Eligible Deliveries]','[Sales Order Count]')
    foreach($case in $definitions.cases){
        $timer=[System.Diagnostics.Stopwatch]::StartNew();$checks=@();$actual=[ordered]@{}
        try {
            $command=$connection.CreateCommand();$command.CommandText=$case.dax;$command.CommandTimeout=120
            $adapter=New-Object Microsoft.AnalysisServices.AdomdClient.AdomdDataAdapter($command)
            $table=New-Object System.Data.DataTable;[void]$adapter.Fill($table)
            if($table.Rows.Count -ne 1){throw 'Expected exactly one result row.'}
            foreach($column in $table.Columns){$key=$column.ColumnName.Trim('[',']');$value=$table.Rows[0][$column.ColumnName];if($value -is [DBNull]){$value=$null};$actual[$key]=$value}
            foreach($entry in $case.expected.PSObject.Properties){
                $key=$entry.Name;$value=$actual[$key];$expected=$entry.Value
                $expression=$case.expressions.$key
                $blankAsZero=($null -eq $value -and $expected -eq 0 -and $countMeasures -contains $expression)
                if($blankAsZero){$value=0}
                $ok=$null -ne $value -and [Math]::Abs([double]$value-[double]$expected) -le [double]$case.tolerance
                $checks+=[pscustomobject]@{Expression=$expression;Expected=$expected;Actual=$actual[$key];BlankCountTreatedAsZero=$blankAsZero;Status=$(if($ok){'PASS'}else{'FAIL'})}
            }
            $status=if(@($checks|Where-Object Status -eq 'FAIL').Count){'FAIL'}else{'PASS'}
            $timer.Stop();$results+=[pscustomobject]@{Name=$case.name;Status=$status;Milliseconds=$timer.ElapsedMilliseconds;Checks=$checks;DAX=$case.dax}
        }catch{$timer.Stop();$results+=[pscustomobject]@{Name=$case.name;Status='FAIL';Milliseconds=$timer.ElapsedMilliseconds;Error=$_.Exception.Message;DAX=$case.dax}}
    }
}catch{$errorText=$_.Exception.Message}
finally {
    if($connection.State -eq 'Open'){$connection.Close()}
    if($server.Connected){$server.Disconnect()}
}
$passed=@($results|Where-Object Status -eq 'PASS').Count
$failed=@($results|Where-Object Status -eq 'FAIL').Count
$summary=[pscustomobject]@{Scope='READ-ONLY local Desktop model/DAX execution; UI rendering/interactions still require separate checks';ModelChecks=$modelChecks;CasesPassed=$passed;CasesFailed=$failed;Error=$errorText;Cases=$results}
$summary | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $run 'results.json') -Encoding UTF8
Write-Output (Join-Path $run 'results.json')
if($errorText -or $failed -or !$passed){throw 'Runtime acceptance did not pass. Inspect the results file; do not mark UI checks complete.'}
