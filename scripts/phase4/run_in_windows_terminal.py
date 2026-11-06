"""Continue the EXISTING project ETL under the user's normal Windows token.

Run with the project's .venv Python. No package installation or system changes.
--execute authorizes the existing guarded OlistSalesDW snapshot loader.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--output',type=Path)
    args=p.parse_args();project=args.project.resolve();package=Path(__file__).resolve().parent
    output=(args.output or project/'reports/phase_4_terminal_run').resolve();output.mkdir(parents=True,exist_ok=True)
    evidence={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'NOT COMPLETE',
              'external_sqlcmd':'Successful according to user; separate from this Python execution.',
              'python':sys.executable,'steps':[],'database_execution_started':False}
    report=output/'phase_4_execution_report.md'
    def save():
        evidence['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output/'run_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        lines=['# Phase 4 actual execution report',f"Status: **{evidence['status']}**",f"Windows token: `{evidence.get('identity','unknown')}`",
               f"Python: `{sys.executable}`",'SQL Server target: `lpc:localhost\\SQLEXPRESS`; Windows Authentication; Encrypt=yes; TrustServerCertificate=yes.',
               'External sqlcmd success and Python connectivity are tracked independently.',
               'Database execution started: '+str(evidence['database_execution_started'])+'. A later validation failure does not undo an earlier committed load.']
        for step in evidence['steps']:lines.append(f"- {step['name']}: {step['status']}; {step.get('details','')}")
        if 'error' in evidence:lines+=['', 'Execution stopped: '+evidence['error']]
        lines+=['','Database ownership, transactional ETL, rerun hashes, rollback, and primary KPI evidence are written by the existing ETL to the project reports directory.',
                'No skipped live tests are accepted as integration-test success. Local checks do not establish SQL Server execution.']
        report.write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    def step(name,command,env=None):
        log=output/(f"{len(evidence['steps'])+1:02d}_"+name.replace(' ','_')+'.log')
        print(name,flush=True)
        item={'name':name,'status':'RUNNING','details':'log='+log.name}
        evidence['steps'].append(item);save()
        try:
            with log.open('w',encoding='utf-8') as stream:
                process=subprocess.run(command,cwd=project,env=env,stdout=stream,stderr=subprocess.STDOUT)
        except BaseException:
            item.update(status='INTERRUPTED',details='Execution outcome uncertain; inspect '+log.name)
            save();raise
        item.update(status='PASS' if process.returncode==0 else 'FAIL',details=f'exit={process.returncode}; log={log.name}')
        save()
        if process.returncode:
            print('\n'.join(log.read_text(encoding='utf-8',errors='replace').splitlines()[-12:]),file=sys.stderr)
        if process.returncode:raise RuntimeError(name+' failed; inspect '+str(log))
    try:
        expected_python=project/'.venv/Scripts/python.exe'
        if Path(sys.executable).resolve()!=expected_python.resolve():raise RuntimeError('Run this helper with the existing project .venv/Scripts/python.exe.')
        evidence['identity']=subprocess.run(['whoami'],capture_output=True,text=True,check=True).stdout.strip()
        if evidence['identity'].lower().endswith('\\codexsandboxoffline'):
            raise RuntimeError('This is still the Codex sandbox token. Open normal Windows Terminal under your usual account.')
        env=os.environ.copy();env.update(OLIST_SQL_SERVER='lpc:localhost\\SQLEXPRESS',OLIST_SQL_DRIVER='ODBC Driver 18 for SQL Server',OLIST_SQL_AUTH='windows',OLIST_SQL_TRUST_CERTIFICATE='yes',PYTHONDONTWRITEBYTECODE='1')
        step('Python connection probe',[sys.executable,str(package/'probe_python.py'),'--output',str(output/'python_connection.json')],env)
        probe=json.loads((output/'python_connection.json').read_text(encoding='utf-8'))
        required=[r for r in probe['attempts'] if 'ODBC Driver 18' in r['configuration'] and 'SERVER=lpc:localhost\\SQLEXPRESS;' in r['configuration']]
        if not required or not required[0]['connected']:raise RuntimeError('Required ODBC 18 Python configuration did not connect. External sqlcmd success does not satisfy this check.')
        evidence['verified_server']=required[0]
        baseline=json.loads((package/'fingerprints.json').read_text(encoding='utf-8'))
        def source_hashes():
            paths=sorted((project/'data/raw').glob('*.csv'))+sorted((project/'data/processed').glob('*.csv'))
            return {f.relative_to(project).as_posix():sha(f) for f in paths}
        actual_paths=sorted((project/'data/raw').glob('*.csv'))+sorted((project/'data/processed').glob('*.csv'))
        before={f.relative_to(project).as_posix():sha(f) for f in actual_paths}
        if len(before)!=19 or before!=baseline:raise RuntimeError('The 19 source files do not match the validated Phase 3 baseline.')
        evidence['steps'].append({'name':'19 source fingerprints before execution','status':'PASS','details':'All match Phase 3.'});save()
        step('Source preflight',[sys.executable,'-m','src.data_processing.sql_server_etl','--preflight-only'],env)
        if not args.execute:
            evidence['status']='PYTHON CONNECTION AND PREFLIGHT PASSED; DATABASE NOT EXECUTED';save();return 0
        evidence['database_execution_started']=True;save()
        step('Existing ETL with rerun and rollback verification',[sys.executable,'-m','src.data_processing.sql_server_etl','--verify-rerun','--verify-rollback'],env)
        env['OLIST_SQL_TESTS']='1'
        junit=output/'sql_integration_tests.xml'
        step('SQL Server integration tests',[sys.executable,'-m','pytest','tests/test_sql_warehouse.py','tests/test_phase4_safety.py','-q','-p','no:cacheprovider','--junitxml='+str(junit)],env)
        suites=ET.parse(junit).getroot()
        counts={k:sum(int(s.get(k,'0')) for s in suites.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
        evidence['pytest_counts']=counts
        if counts['tests']<19 or any(counts[k] for k in ('failures','errors','skipped')):raise RuntimeError('The complete integration suite did not execute without skips/failures.')
        step('Additional Phase 3 acceptance checks',[sys.executable,str(package/'verify_additional_kpis.py'),'--project',str(project),'--output',str(output/'additional_kpis.json')],env)
        # Never label the run complete merely because the ETL process returned zero.
        import csv
        for name in ('phase_4_etl_validation.csv','phase_4_kpi_reconciliation.csv'):
            with (project/'reports'/name).open(encoding='utf-8-sig',newline='') as stream:checks=list(csv.DictReader(stream))
            if not checks or any(not (r['status']=='PASS' or (name=='phase_4_etl_validation.csv' and r['status']=='WARN' and r.get('category')=='source_quality')) for r in checks):
                raise RuntimeError('Unexecuted/failed validation in '+name)
        execution=json.loads((project/'reports/phase_4_execution_evidence.json').read_text(encoding='utf-8'))
        if len(execution['successful_load_ids'])!=2:raise RuntimeError('Two successful ETL loads are required.')
        after=source_hashes()
        if after!=before:raise RuntimeError('Source fingerprints changed during execution.')
        evidence.update(source_hashes=after,table_counts=execution['table_counts'],successful_load_ids=execution['successful_load_ids'])
        evidence['steps'].append({'name':'19 source fingerprints after execution','status':'PASS','details':'Exact match to before execution and Phase 3.'})
        evidence['status']='COMPLETE — SQL SERVER EXECUTION AND ALL VALIDATION SUCCEEDED'
        save();print('Phase 4 complete. Evidence: '+str(report));return 0
    except BaseException as exc:
        evidence['error']=str(exc) or type(exc).__name__;evidence['status']='NOT COMPLETE — EXECUTION STOPPED';save()
        print(str(exc),file=sys.stderr);print('Report: '+str(report),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
