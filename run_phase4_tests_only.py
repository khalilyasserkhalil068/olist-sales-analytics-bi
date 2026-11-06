"""Run existing-warehouse tests only. Never invoke ETL or database setup."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path(r'E:\Projects CV\Sales Analytics & Business Intelligence'))
    root=parser.parse_args().project.resolve()
    python=root/'.venv/Scripts/python.exe'
    required=[python,root/'tests/test_sql_warehouse.py',root/'tests/test_phase4_safety.py',root/'reports/phase_4_protected_files.json']
    for path in required:
        if not path.is_file(): raise RuntimeError('Missing prerequisite: '+str(path))
    test=(root/'tests/test_sql_warehouse.py').read_text(encoding='utf-8')
    if 'out.reset_index()["review_id"].nunique() == 814' not in test or '.dayofweek' in test:
        raise RuntimeError('Install the corrected tests/test_sql_warehouse.py first.')
    output=root/'reports/phase_4_test_only'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True)
    evidence={'etl_executed':False,'database_setup_executed':False,'steps':[],'status':'NOT EXECUTED'}
    baseline=json.loads((root/'reports/phase_4_protected_files.json').read_text(encoding='utf-8'))
    def verify():
        changed=[name for name,digest in baseline.items() if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest]
        if changed: raise RuntimeError('Protected file mismatch: '+str(changed))
    env=os.environ.copy()
    env.update(OLIST_SQL_SERVER=r'lpc:localhost\SQLEXPRESS',OLIST_SQL_DRIVER='ODBC Driver 18 for SQL Server',OLIST_SQL_AUTH='windows',OLIST_SQL_TRUST_CERTIFICATE='yes',OLIST_SQL_TESTS='1',PHASE2_AUDIT_WRITE='0',PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    env.pop('PYTEST_ADDOPTS',None)
    env.pop('PYTEST_PLUGINS',None)
    target='tests/test_sql_warehouse.py::test_review_record_grain_scores_and_text_availability'
    try:
        verify()
        for name,tests in [('targeted',[target]),('complete',['tests/test_sql_warehouse.py','tests/test_phase4_safety.py'])]:
            junit=output/(name+'.xml')
            command=[str(python),'-B','-m','pytest',*tests,'-q','-p','no:cacheprovider','--junitxml='+str(junit),'--basetemp='+str(output/(name+'_tmp'))]
            print('\nRunning '+name+' tests only. No ETL or database creation.',flush=True)
            step={'name':name,'command':command}
            evidence['steps'].append(step)
            with (output/(name+'.log')).open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
                for line in process.stdout:
                    print(line,end='',flush=True);log.write(line);log.flush()
                step['exit_code']=process.wait()
            if junit.exists():
                suites=ET.parse(junit).getroot()
                step['counts']={k:sum(int(s.get(k,'0')) for s in suites.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
            counts=step.get('counts',{})
            if step['exit_code'] or not counts.get('tests') or any(counts.get(k,0) for k in ('failures','errors','skipped')):
                raise RuntimeError(name+' tests did not pass completely. See '+str(output))
        evidence['status']='PASS'
    except BaseException as exc:
        evidence['status']='FAIL';evidence['error']=str(exc)
        raise
    finally:
        try:
            verify();evidence['protected_files_unchanged']=len(baseline)
        except Exception as exc:
            evidence['status']='FAIL';evidence['integrity_error']=str(exc)
        (output/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print('\nEvidence: '+str(output),flush=True)
    return 0 if evidence['status']=='PASS' else 1

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
