"""Read-only Python ODBC probe; run using the existing project .venv."""
import argparse
import datetime
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('python_connection_evidence.json'))
    args=parser.parse_args()
    evidence={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'python':sys.executable,'python_version':sys.version,
              'actual_token_identity':subprocess.run(['whoami'],capture_output=True,text=True).stdout.strip(),
              'environment_username':getpass.getuser(),
              'note':'getpass may read environment variables; whoami reports the process token identity.',
              'external_terminal_result':'User reports success with Windows Authentication on DESKTOP-GEUMHVT\\SQLEXPRESS; external login name not provided.',
              'attempts':[]}
    try:
        import pyodbc
    except ImportError as exc:
        evidence['import_error']=str(exc)
    else:
        evidence.update(pyodbc_version=pyodbc.version,drivers=pyodbc.drivers())
        for driver in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server'):
            for server in ('lpc:localhost\\SQLEXPRESS','lpc:DESKTOP-GEUMHVT\\SQLEXPRESS'):
                config=f'DRIVER={{{driver}}};SERVER={server};DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;APP=OlistPhase4Probe;'
                attempt={'configuration':config}
                try:
                    with pyodbc.connect(config,timeout=5,autocommit=True) as cn:
                        row=cn.cursor().execute("SELECT @@SERVERNAME, ORIGINAL_LOGIN(), CONVERT(nvarchar(128),SERVERPROPERTY('ProductVersion'))").fetchone()
                        attempt.update(connected=True,server=row[0],login=row[1],version=row[2])
                except pyodbc.Error as exc:
                    attempt.update(connected=False,error_args=list(exc.args))
                evidence['attempts'].append(attempt)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,indent=2))
    return 0 if any(a.get('connected') for a in evidence['attempts']) else 2

if __name__=='__main__':
    raise SystemExit(main())
