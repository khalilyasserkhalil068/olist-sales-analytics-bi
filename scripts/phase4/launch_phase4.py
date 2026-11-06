"""Interactive launcher only. Existing runner and ETL implementations are unchanged."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys

TARGET = 'DESKTOP-GEUMHVT\\SQLEXPRESS'
CONFIRMATION = 'RUN PHASE4'

def prerequisites(project, package):
    errors=[]
    required=[
        project/'.venv/Scripts/python.exe',
        project/'src/data_processing/sql_server_etl.py',
        project/'src/data_processing/warehouse_contract.json',
        project/'tests/test_sql_warehouse.py',
        project/'tests/test_phase4_safety.py',
        project/'reports/phase_4_protected_files.json',
        project/'reports/phase_4_source_to_target_mapping.csv',
        project/'docs/kpi_definitions.md',
    ]
    required += [project/'sql'/name for name in (
        '01_create_database.sql','02_create_staging_tables.sql','03_create_dimensions.sql',
        '04_create_fact_tables.sql','05_create_indexes.sql','06_kpi_validation.sql',
        '07_data_quality_checks.sql','08_load_warehouse.sql')]
    required += [package/name for name in ('run_in_windows_terminal.py','probe_python.py','verify_additional_kpis.py','fingerprints.json')]
    for path in required:
        if not path.is_file():errors.append('Missing required file: '+str(path))
    if Path(sys.executable).resolve()!=(project/'.venv/Scripts/python.exe').resolve():
        errors.append('The launcher must use the project .venv Python: '+str(project/'.venv/Scripts/python.exe'))
    if platform.node().upper()!='DESKTOP-GEUMHVT':
        errors.append('This package targets '+TARGET+' via local shared memory. Current machine: '+platform.node())
    for name in ('pyodbc','pytest','pandas','numpy'):
        if importlib.util.find_spec(name) is None:errors.append('Missing project .venv dependency: '+name)
    if importlib.util.find_spec('pyodbc') is not None:
        import pyodbc
        if 'ODBC Driver 18 for SQL Server' not in pyodbc.drivers():
            errors.append('ODBC Driver 18 for SQL Server is not installed.')
    if (package/'fingerprints.json').is_file():
        try:
            baseline=json.loads((package/'fingerprints.json').read_text(encoding='utf-8'))
            if len(baseline)!=19:errors.append('Expected 19 protected CSV fingerprints.')
            for name in baseline:
                if not (project/name).is_file():errors.append('Missing protected source CSV: '+name)
        except (OSError,ValueError) as exc:errors.append('Cannot read source fingerprint baseline: '+str(exc))
    return errors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--check-files',action='store_true',help='File/dependency checks only; no prompt, report write, connection, or ETL.')
    args=parser.parse_args();project=args.project.resolve();package=Path(__file__).resolve().parent
    report=project/'reports/phase_4_terminal_run/phase_4_execution_report.md'
    print('\nOlist Phase 4 - Windows launcher',flush=True)
    print('Project: '+str(project))
    print('Target instance: '+TARGET)
    print('Transport: lpc:localhost\\SQLEXPRESS (local alias for the target above)')
    print('Authentication: Windows; encryption enabled; local certificate trust enabled.')
    print('Python: '+sys.executable)
    print('Execution report: '+str(report)+'\n',flush=True)
    try:
        errors=prerequisites(project,package)
    except Exception as exc:
        errors=['Prerequisite inspection failed: '+str(exc)]
    if args.check_files:
        for error in errors:print('ERROR: '+error,file=sys.stderr)
        print('File/dependency checks: '+('FAIL' if errors else 'PASS')+'. No SQL connection or ETL attempted.')
        return 1 if errors else 0
    report.parent.mkdir(parents=True,exist_ok=True)
    # Preserve any previous actual evidence before writing this attempt's status.
    if report.exists():
        archive=report.with_name('phase_4_execution_report_previous_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.md')
        archive.write_bytes(report.read_bytes())
    def status(message):
        report.write_text('# Phase 4 execution report\n\nStatus: **NOT EXECUTED / NOT COMPLETE**\n\n'+message+'\n\n'+
            'Target: `'+TARGET+'`; Windows Authentication; encryption enabled.\n\n'+
            'No SQL Server connection or ETL was attempted by this launcher before confirmation.\n',encoding='utf-8')
    def interrupted(message):
        prior=report.read_text(encoding='utf-8') if report.exists() else ''
        report.write_text('# Launcher status: NOT COMPLETE\n\n'+message+
            '\n\nDatabase execution may have started. Existing runner evidence follows.\n\n'+prior,encoding='utf-8')
    status('Launcher opened. Checking prerequisites; awaiting explicit confirmation.')
    runner_started=False
    try:
        token=subprocess.run(['whoami'],capture_output=True,text=True,check=True).stdout.strip()
        print('Actual Windows identity: '+token)
        if token.lower().endswith(('\\codexsandboxoffline','\\codexsandboxonline')):
            errors.append('Codex sandbox identity detected. Double-click RUN_PHASE4.bat under your normal Windows account.')
        if errors:
            for error in errors:print('ERROR: '+error,file=sys.stderr)
            status('Prerequisite check failed:\n\n'+'\n'.join('- '+e for e in errors));return 1
        print('\nPrerequisites passed. No SQL connection has been attempted.')
        print('Continuing will inspect/create OlistSalesDW, load its snapshot twice,')
        print('and run the existing rollback, integrity, and KPI reconciliation checks.')
        print('Raw/processed CSV files will only be read.')
        print('To confirm database changes, type exactly: '+CONFIRMATION)
        answer=input('Confirmation (Enter cancels): ')
        if answer.strip()!=CONFIRMATION:
            print('Cancelled. Database execution was not started.')
            status('User did not confirm. Database execution was not started.');return 2
        status('User explicitly confirmed '+CONFIRMATION+'. Starting the existing runner; its report will replace this status.')
        runner_started=True
        result=subprocess.run([sys.executable,str(package/'run_in_windows_terminal.py'),'--project',str(project),'--output',str(report.parent),'--execute'],cwd=project)
        if result.returncode:
            print('\nERROR: Phase 4 did not complete. Read '+str(report),file=sys.stderr)
        else:
            print('\nExecution returned successfully. Actual evidence: '+str(report))
        return result.returncode
    except (KeyboardInterrupt,EOFError):
        if runner_started:
            interrupted('Execution was interrupted after confirmation.')
            print('\nExecution interrupted after confirmation. Inspect the actual report and logs; database work may have started.',file=sys.stderr)
        else:
            status('Cancelled before starting the execution runner.');print('\nCancelled.')
        return 2
    except Exception as exc:
        if runner_started:
            interrupted('Launcher error after starting the runner: '+str(exc))
        else:
            status('Launcher error: '+str(exc))
        print('ERROR: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
