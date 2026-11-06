"""Offline execution-safety regressions. Every ODBC connection is forbidden here."""
from decimal import Decimal,localcontext,ROUND_HALF_UP
from copy import deepcopy
import importlib.util
import csv
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pyodbc
from src.data_processing import sql_server_etl as etl
from src.config import PROJECT_ROOT


@pytest.fixture(autouse=True)
def forbid_real_sql(monkeypatch):
    def forbidden(*a,**k):
        raise AssertionError('This is an offline test; a real SQL connection is forbidden.')
    monkeypatch.setattr(pyodbc,'connect',forbidden)


def patch_root():
    return Path(os.environ.get('PHASE4_SAFETY_PATCH',str(PROJECT_ROOT)))


def import_helper(name):
    path=patch_root()/'scripts/phase4'/name
    spec=importlib.util.spec_from_file_location('_review_'+path.stem,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Cursor:
    def __init__(self,cn):self.cn=cn;self.description=None;self.query='';self._fetched=False
    def execute(self,query,*args):
        self.query=query;self._fetched=False
        self.description=[('value',)] if query.strip().startswith(('SELECT','DECLARE')) else None
        self.cn.events.append(query)
        if "SET Status='PASS'" in query:self.cn.outcome='PASS'
        if "SET Status='FAIL'" in query:self.cn.outcome='FAIL'
        return self
    def fetchval(self):return 1
    def fetchall(self):return []
    def fetchone(self):return ('order','1')
    def fetchmany(self,size):
        if self._fetched:return []
        self._fetched=True
        return [(self.fetchval(),)] if self.query.startswith('DECLARE') else self.fetchall()
    def nextset(self):return False
    def close(self):self.cn.events.append('CURSOR CLOSE')


class Connection:
    def __init__(self,autocommit=False):
        self.autocommit=autocommit;self.events=[];self.outcome=None;self.pending=False;self.closed=False
    def cursor(self):return Cursor(self)
    def commit(self):self.events.append('COMMIT '+str(self.outcome));self.pending=False
    def rollback(self):self.events.append('ROLLBACK');self.pending=False
    def close(self):self.events.append('CLOSE');self.closed=True


def setup_load(monkeypatch,checks=None,stage_error=None):
    cn=Connection()
    monkeypatch.setattr(etl,'connect',lambda *a,**k:cn)
    monkeypatch.setattr(etl,'assert_owned_database',lambda c,**k:None)
    def stage(c,*a,**k):
        c.events.append('DELETE staging');c.pending=True
        if stage_error:raise stage_error
    monkeypatch.setattr(etl,'load_staging',stage)
    monkeypatch.setattr(etl,'execute_script',lambda c,n,**k:cn.events.append('RELOAD '+n))
    monkeypatch.setattr(etl,'validation_checks',lambda c:checks or [])
    def roundtrip(c):c.events.append('VERIFY roundtrip');return []
    monkeypatch.setattr(etl,'verify_staging_round_trip',roundtrip)
    monkeypatch.setattr(etl,'kpi_reconciliation',lambda *a:[])
    monkeypatch.setattr(etl,'protected_integrity',lambda:83)
    monkeypatch.setattr(etl,'record_checks',lambda *a:cn.events.append('RECORD checks'))
    return cn


def test_success_commits_only_after_roundtrip_and_validation(monkeypatch):
    cn=setup_load(monkeypatch)
    etl.run_load({})
    assert cn.events.index('COMMIT None')<cn.events.index('DELETE staging')
    assert cn.events.index('DELETE staging')<cn.events.index('VERIFY roundtrip')<cn.events.index('COMMIT PASS')
    assert cn.closed


@pytest.mark.parametrize('failure',[RuntimeError('stage failed'),KeyboardInterrupt()])
def test_mid_staging_failure_or_interrupt_rolls_back_before_audit_commit(monkeypatch,failure):
    cn=setup_load(monkeypatch,stage_error=failure)
    with pytest.raises(type(failure)):etl.run_load({})
    assert cn.events.index('ROLLBACK')<cn.events.index('COMMIT FAIL')
    assert 'COMMIT PASS' not in cn.events and not cn.pending and cn.closed


@pytest.mark.parametrize('status,category',[('FAIL','execution'),('NOT EXECUTED','execution'),('WARN','execution'),('WARN','source_quality')])
def test_unexpected_validation_never_commits(monkeypatch,status,category):
    cn=setup_load(monkeypatch,[dict(check='Unexpected condition',status=status,category=category)])
    with pytest.raises(ValueError,match='Validation failed'):etl.run_load({})
    assert 'ROLLBACK' in cn.events and 'COMMIT PASS' not in cn.events


def test_known_source_quality_warning_is_nonfatal(monkeypatch):
    warning=etl.result('Orders without items',775,0,warning=True)
    cn=setup_load(monkeypatch,[warning]);etl.run_load({})
    assert warning['status']=='WARN' and 'COMMIT PASS' in cn.events


def test_roundtrip_failure_rolls_back_before_success(monkeypatch):
    cn=setup_load(monkeypatch)
    monkeypatch.setattr(etl,'verify_staging_round_trip',lambda c:[etl.result('Roundtrip',1,0)])
    with pytest.raises(ValueError):etl.run_load({})
    assert 'COMMIT PASS' not in cn.events and 'ROLLBACK' in cn.events


@pytest.mark.parametrize('method',['load_staging','verify_unknown_fallback'])
def test_autocommit_refused_before_any_delete_or_synthetic_update(method):
    cn=Connection(autocommit=True)
    with pytest.raises(RuntimeError,match='autocommit=False'):
        getattr(etl,method)(cn,'load') if method=='load_staging' else getattr(etl,method)(cn)
    assert cn.events==[]


@pytest.mark.parametrize('error',[None,RuntimeError('loader failed'),KeyboardInterrupt()])
def test_unknown_fixture_rolls_back_on_success_error_and_interrupt(monkeypatch,error):
    cn=Connection();cur=Cursor(cn)
    def one():
        if any('SELECT ProductKey' in e for e in cn.events):return SimpleNamespace(ProductKey=0,SourceProductID='~MISSING_TEST')
        return ('order','1')
    cur.fetchone=one;cn.cursor=lambda:cur
    cur.fetchall=lambda:[one()]
    monkeypatch.setattr(etl,'assert_owned_database',lambda c:None)
    def reload(c,n,**kwargs):
        cn.pending=True
        if error:raise error
    monkeypatch.setattr(etl,'execute_script',reload)
    if error:
        with pytest.raises(type(error)):etl.verify_unknown_fallback(cn)
    else:assert etl.verify_unknown_fallback(cn)['status']=='PASS'
    assert cn.events[-1]=='ROLLBACK' and not cn.pending
    assert not any(e.startswith('COMMIT') for e in cn.events)


def allowed_objects():
    return [('stg',n,'U') for n in etl.CONTRACT]+[('dw',n,'U') for n in [*etl.DIM_KEYS,*etl.FACTS]]+[
        ('audit',n,'U') for n in ['WarehouseMetadata','LoadRun','LoadFile','ValidationResult']]


def guard_connection(database='OlistSalesDW',marker=True,objects=None):
    class GuardCursor(Cursor):
        def execute(self,q,*a):self.query=q;return super().execute(q,*a)
        def fetchval(self):return database if self.query=='SELECT DB_NAME()' else int(marker) if marker else None
        def fetchall(self):
            if self.query=='SELECT DB_NAME()' or 'SELECT OBJECT_ID(' in self.query:return [(self.fetchval(),)]
            return [('OlistSalesDW',1)] if self.query.startswith('SELECT ProjectName') else (allowed_objects() if objects is None else objects)
    cn=Connection();cn.cursor=lambda:GuardCursor(cn);return cn


@pytest.mark.parametrize('db',['master','SomeUserDatabase'])
def test_wrong_database_refused_before_writes(db):
    cn=guard_connection(database=db)
    with pytest.raises(RuntimeError,match='outside'):etl.assert_owned_database(cn)
    assert [e for e in cn.events if e!='CURSOR CLOSE']==['SELECT DB_NAME()']


def test_unmarked_existing_database_is_refused():
    with pytest.raises(RuntimeError,match='ownership marker'):etl.assert_owned_database(guard_connection(marker=False))


@pytest.mark.parametrize('extra',[('dbo','UserTable','U'),('dw','FactOrdersTrigger','TR'),('stg','payments','SN')])
def test_unrelated_table_trigger_or_synonym_refused(extra):
    with pytest.raises(RuntimeError,match='Unexpected'):etl.assert_owned_database(guard_connection(objects=allowed_objects()+[extra]))


def test_only_expected_dedicated_objects_are_accepted():
    etl.assert_owned_database(guard_connection())


def test_loader_sql_has_transaction_guard_and_only_intended_destructive_operations():
    sql=(patch_root()/'sql/08_load_warehouse.sql').read_text(encoding='utf-8')
    code=re.sub(r'--[^\n]*|/\*.*?\*/','',sql,flags=re.S)
    assert 'XACT_STATE()<>1 OR @@TRANCOUNT=0' in code and 'DB_NAME()' in code
    assert not re.search(r'\b(COMMIT|ROLLBACK|TRUNCATE|BACKUP|RESTORE|USE)\b',code,re.I)
    assert all(n.startswith('#') for n in re.findall(r'\bDROP\s+TABLE\s+(\S+?);',code,re.I))
    assert re.findall(r'\bDELETE\s+(?:FROM\s+)?([\w.]+)',code,re.I)==['dw.FactReviews','dw.FactPayments','dw.FactOrderItems','d']
    assert 'DELETE d FROM dw.FactOrders d WHERE NOT EXISTS' in code
    assert not re.search(r'\b(?:FROM|JOIN|INTO)\s+\w+\.\w+\.\w+',code,re.I)


def test_standalone_initialization_checks_marker_before_creation():
    sql=(patch_root()/'sql/01_create_database.sql').read_text(encoding='utf-8')
    assert sql.index('Existing OlistSalesDW is not owned')<sql.index('CREATE DATABASE')


def test_rollback_verifier_uses_supplied_latest_committed_snapshot(monkeypatch):
    cn=Connection();latest={'dw.FactOrders':{'sha256':'latest'}}
    monkeypatch.setattr(etl,'connect',lambda *a,**k:cn)
    def fail(*a,**k):raise RuntimeError('Intentional rollback verification after replacing the first staging table')
    monkeypatch.setattr(etl,'run_load',fail)
    monkeypatch.setattr(etl,'snapshot_hashes',lambda c:latest)
    monkeypatch.setattr(etl,'verify_unknown_fallback',lambda c:etl.result('Unknown product fallback preserves source record',1,1))
    assert all(r['status']=='PASS' for r in etl.rollback_verification({},latest))
    assert cn.closed


def test_main_compares_fault_tests_to_latest_even_when_idempotency_fails(monkeypatch,tmp_path):
    cn=Connection();first={'state':'first'};latest={'state':'second'}
    monkeypatch.setattr(etl,'ROOT',tmp_path);(tmp_path/'reports').mkdir()
    monkeypatch.setattr(etl,'preflight',lambda:{'protected_files':83})
    monkeypatch.setattr(etl,'inspect_server',lambda:{'instance':'fake'})
    monkeypatch.setattr(etl,'initialize_database',lambda:'mocked')
    monkeypatch.setattr(etl,'expected_kpis',lambda p:{})
    monkeypatch.setattr(etl,'run_load',Mock(side_effect=[{'load_id':'first','validation':[],'kpis':[]},{'load_id':'second','validation':[],'kpis':[]}]))
    monkeypatch.setattr(etl,'connect',lambda *a,**k:cn)
    monkeypatch.setattr(etl,'snapshot_hashes',Mock(side_effect=[first,latest]))
    rollback=Mock(return_value=[]);monkeypatch.setattr(etl,'rollback_verification',rollback)
    monkeypatch.setattr(etl,'export_schema_dictionary',lambda c:1)
    monkeypatch.setattr(etl,'capture_plans',lambda c:['one','two','three'])
    monkeypatch.setattr(etl,'record_checks',lambda *a:None)
    monkeypatch.setattr(etl,'protected_integrity',lambda:83)
    monkeypatch.setattr(etl,'write_csv',lambda *a:None)
    assert etl.main(['--verify-rerun','--verify-rollback'])==1
    rollback.assert_called_once_with({},latest)
    saved=json.loads((tmp_path/'reports/phase_4_execution_evidence.json').read_text())
    assert saved['snapshot_hashes']==latest and saved['first_snapshot_hashes']==first


def test_concurrent_execution_is_refused_before_database_initialization(monkeypatch):
    cn=Connection();cur=Cursor(cn);cur.fetchval=lambda:-1;cn.cursor=lambda:cur
    monkeypatch.setattr(etl,'preflight',lambda:{})
    monkeypatch.setattr(etl,'inspect_server',lambda:{})
    monkeypatch.setattr(etl,'connect',lambda *a,**k:cn)
    initialize=Mock();monkeypatch.setattr(etl,'initialize_database',initialize)
    with pytest.raises(RuntimeError,match='Another Phase 4 execution'):etl.main([])
    initialize.assert_not_called()
    assert cn.closed


@pytest.mark.parametrize('answer',['','yes'])
def test_launcher_cancellation_never_starts_runner(monkeypatch,tmp_path,answer):
    launcher=import_helper('launch_phase4.py')
    monkeypatch.setattr(launcher,'prerequisites',lambda *a:[])
    monkeypatch.setattr(launcher.sys,'argv',['launcher','--project',str(tmp_path)])
    run=Mock(return_value=SimpleNamespace(stdout='host\\normal_user',returncode=0))
    monkeypatch.setattr(launcher.subprocess,'run',run);monkeypatch.setattr('builtins.input',lambda _:answer)
    assert launcher.main()==2 and run.call_count==1


@pytest.mark.parametrize('failure',[OSError('runner launch error'),KeyboardInterrupt()])
def test_launcher_preserves_runner_evidence_after_confirmation(monkeypatch,tmp_path,failure):
    launcher=import_helper('launch_phase4.py')
    monkeypatch.setattr(launcher,'prerequisites',lambda *a:[])
    monkeypatch.setattr(launcher.sys,'argv',['launcher','--project',str(tmp_path)])
    monkeypatch.setattr('builtins.input',lambda _:'RUN PHASE4')
    report=tmp_path/'reports/phase_4_terminal_run/phase_4_execution_report.md'
    def run(command,**kwargs):
        if command==['whoami']:return SimpleNamespace(stdout='host\\normal_user',returncode=0)
        report.write_text('Actual runner evidence: first load committed',encoding='utf-8')
        raise failure
    monkeypatch.setattr(launcher.subprocess,'run',run)
    assert launcher.main()!=0
    text=report.read_text(encoding='utf-8')
    assert 'NOT COMPLETE' in text and 'Actual runner evidence' in text
    assert 'may have started' in text and 'NOT EXECUTED' not in text


@pytest.mark.parametrize('failure',[7,KeyboardInterrupt()])
def test_runner_failed_or_interrupted_probe_saves_actual_step_failure(monkeypatch,tmp_path,failure):
    runner=import_helper('run_in_windows_terminal.py')
    monkeypatch.setattr(runner.sys,'executable',str(tmp_path/'.venv/Scripts/python.exe'))
    monkeypatch.setattr(runner.sys,'argv',['runner','--project',str(tmp_path),'--execute'])
    def run(command,**kwargs):
        if command==['whoami']:return SimpleNamespace(stdout='host\\normal_user',returncode=0)
        if isinstance(failure,BaseException):raise failure
        kwargs['stdout'].write('Synthetic offline probe failure\n');return SimpleNamespace(returncode=failure)
    monkeypatch.setattr(runner.subprocess,'run',run)
    assert runner.main()==1
    evidence=json.loads((tmp_path/'reports/phase_4_terminal_run/run_evidence.json').read_text(encoding='utf-8'))
    assert evidence['status'].startswith('NOT COMPLETE')
    assert evidence['steps'][0]['status'] in ('FAIL','INTERRUPTED')
    assert evidence['database_execution_started'] is False


class SingleActiveCursor:
    """Model SQL Server's no-MARS response ownership, including trailing DONEs."""
    def __init__(self,cn):self.cn=cn;self.groups=[];self.index=0;self.closed=False
    @property
    def description(self):
        return self.groups[self.index][0] if self.index<len(self.groups) else None
    def execute(self,query,*params):
        if self.cn.active is not None:
            raise pyodbc.Error('HY000','Connection is busy with results for another command')
        self.cn.queries.append(query)
        groups=self.cn.responses.get(query)
        if groups is None:
            if query.startswith('DECLARE'):groups=[(('value',),[(1,)]),(None,[])]
            elif query.startswith('SELECT'):groups=[(('value',),[(0,)]),(None,[])]
            else:groups=[(None,[]),(None,[])]
        self.groups=deepcopy(groups);self.index=0;self.cn.active=self
        if "SET Status='PASS'" in query:self.cn.outcome='PASS'
        if "SET Status='FAIL'" in query:self.cn.outcome='FAIL'
        return self
    def executemany(self,query,params):return self.execute(query)
    def setinputsizes(self,sizes):pass
    def fetchmany(self,size):
        assert self.description is not None,'Attempted to fetch a row-count/DONE response'
        rows=self.groups[self.index][1];batch=rows[:size];del rows[:size];return batch
    def fetchone(self):
        rows=self.fetchmany(1);return rows[0] if rows else None
    def nextset(self):
        assert not self.groups[self.index][1],'Rows were skipped before SQLMoreResults'
        self.index+=1;self.cn.advances+=1
        if self.index==len(self.groups):self.cn.active=None;return False
        if isinstance(self.groups[self.index],BaseException):raise self.groups[self.index]
        return True
    def close(self):
        self.closed=True
        if self.cn.active is self:self.cn.cancelled+=1;self.cn.active=None


class SingleActiveConnection:
    def __init__(self,responses=None):
        self.responses=responses or {};self.active=None;self.cursors=[];self.queries=[]
        self.autocommit=False;self.advances=0;self.cancelled=0;self.commits=0;self.rollbacks=0
        self.closed=False;self.outcome=None
    def cursor(self):
        cur=SingleActiveCursor(self);self.cursors.append(cur);return cur
    def commit(self):
        assert self.active is None,'Commit attempted with an unfinished response'
        self.commits+=1
    def rollback(self):self.rollbacks+=1;self.active=None
    def close(self):self.closed=True


def warehouse_responses():
    return [(None,[]),(('diagnostic',),[(42,)]),(None,[])]


def test_reproduces_original_unconsumed_batch_hy000():
    cn=SingleActiveConnection({'warehouse':warehouse_responses()})
    loader=cn.cursor();loader.execute('warehouse')  # old execute_script returned here
    with pytest.raises(pyodbc.Error,match='Connection is busy'):
        cn.cursor().execute('SELECT COUNT_BIG(*) FROM stg.[orders]')
    loader.close()


def validation_fixture(monkeypatch):
    cn=SingleActiveConnection({'warehouse':warehouse_responses(),
        'SELECT COUNT_BIG(*) FROM stg.[orders]':[(('count',),[(1,)]),(None,[])],
        'quality':[(None,[]),(('check','count'),[('Orders without items',775)]),(None,[])]})
    monkeypatch.setattr(etl,'CONTRACT',{'orders':{'rows':1,'sha256':'test'}})
    monkeypatch.setattr(etl,'FACTS',{});monkeypatch.setattr(etl,'DIM_KEYS',{})
    monkeypatch.setattr(etl,'SOURCE_DIMENSIONS',{})
    monkeypatch.setattr(etl,'sql_batches',lambda path:['warehouse' if path.name.startswith('08_') else 'quality'])
    return cn


def test_load_batch_is_fully_drained_before_real_validation_checks(monkeypatch):
    cn=validation_fixture(monkeypatch)
    etl.execute_file(cn,'08_load_warehouse.sql')
    checks=etl.validation_checks(cn)
    assert not etl.validation_failures(checks)
    assert cn.active is None and all(c.closed for c in cn.cursors)
    assert cn.cancelled==0 and cn.commits==cn.rollbacks==0


@pytest.mark.parametrize('capture',[False,True])
def test_every_go_batch_and_mixed_response_is_consumed(monkeypatch,capture):
    cn=SingleActiveConnection({'first':warehouse_responses(),'second':warehouse_responses()})
    monkeypatch.setattr(etl,'sql_batches',lambda p:['first','second'])
    rows=etl.execute_file(cn,'any.sql',collect_results=capture)
    assert rows==([(42,),(42,)] if capture else [])
    assert cn.queries==['first','second'] and cn.advances==6
    assert cn.cancelled==0 and all(c.closed for c in cn.cursors)


@pytest.mark.parametrize('capture',[False,True])
def test_deferred_sql_error_is_not_hidden_by_drain_or_cursor_close(monkeypatch,capture):
    cn=SingleActiveConnection({'late':[(('value',),[(1,)]),pyodbc.Error('42000','Deferred SQL error')]})
    monkeypatch.setattr(etl,'sql_batches',lambda p:['late','must not run'])
    with pytest.raises(pyodbc.Error,match='Deferred SQL error'):
        etl.execute_file(cn,'any.sql',collect_results=capture)
    assert cn.queries==['late'] and all(c.closed for c in cn.cursors)
    assert cn.commits==0


def test_kpi_rows_are_preserved_while_all_results_are_drained(monkeypatch):
    cn=SingleActiveConnection({'kpis':[(None,[]),(('metric','amount'),[
        ('Merchandise Revenue',Decimal('13221498.11')),('Eligible Orders',Decimal(96478))]),(None,[])]})
    monkeypatch.setattr(etl,'sql_batches',lambda p:['kpis'])
    checks=etl.kpi_reconciliation(cn,{'Merchandise Revenue':(Decimal('13221498.11'),Decimal(0)),
                                    'Eligible Orders':(Decimal(96478),Decimal(0))})
    assert len(checks)==2 and all(c['status']=='PASS' for c in checks)
    assert cn.active is None and cn.cancelled==0 and all(c.closed for c in cn.cursors)


@pytest.mark.parametrize('late_error',[False,True])
def test_run_load_drains_or_rolls_back_before_validation_commit(monkeypatch,late_error):
    cn=validation_fixture(monkeypatch)
    if late_error:cn.responses['warehouse']=[(None,[]),pyodbc.Error('42000','Deferred load failure')]
    monkeypatch.setattr(etl,'connect',lambda:cn)
    monkeypatch.setattr(etl,'assert_owned_database',lambda *a,**k:None)
    monkeypatch.setattr(etl,'load_staging',lambda *a,**k:None)
    monkeypatch.setattr(etl,'verify_staging_round_trip',lambda c:[])
    monkeypatch.setattr(etl,'kpi_reconciliation',lambda *a:[])
    monkeypatch.setattr(etl,'protected_integrity',lambda:83)
    if late_error:
        with pytest.raises(pyodbc.Error,match='Deferred load failure'):etl.run_load({})
        assert cn.rollbacks==1 and cn.outcome=='FAIL'
        assert 'SELECT COUNT_BIG(*) FROM stg.[orders]' not in cn.queries
    else:
        assert etl.run_load({})['validation']
        assert cn.rollbacks==0 and cn.outcome=='PASS'
    assert cn.commits==2 and cn.closed
    assert all(c.closed for c in cn.cursors)


def test_staging_insert_and_audit_cursors_do_not_overlap_results(monkeypatch):
    cn=SingleActiveConnection()
    spec={'rows':2,'sha256':'test','filename':'orders_clean.csv','columns':[{'name':'value'}]}
    monkeypatch.setattr(etl,'CONTRACT',{'orders':spec})
    monkeypatch.setattr(etl,'assert_owned_database',lambda c:None)
    monkeypatch.setattr(etl,'input_sizes',lambda s:[])
    monkeypatch.setattr(etl,'source_rows',lambda n:iter([(1,('a',)),(2,('b',))]))
    etl.load_staging(cn,'load',batch_size=1)
    assert all(c.closed for c in cn.cursors) and cn.cancelled==0
    assert cn.commits==cn.rollbacks==0


def test_roundtrip_extra_rows_are_drained_before_cursor_closes(monkeypatch):
    query='SELECT [value] FROM stg.[orders] ORDER BY SourceRow'
    cn=SingleActiveConnection({query:[(('value',),[('a',),('b',),('c',)]),(None,[])]})
    monkeypatch.setattr(etl,'CONTRACT',{'orders':{'columns':[{'name':'value'}]}})
    monkeypatch.setattr(etl,'source_rows',lambda n:iter([(1,('a',))]))
    checks=etl.verify_staging_round_trip(cn)
    assert checks[0]['status']=='FAIL' and cn.cancelled==0
    assert all(c.closed for c in cn.cursors)


def test_scalar_helper_and_cursor_cleanup_do_not_enable_mars():
    cn=SingleActiveConnection()
    assert etl.fetch_scalar(cn,'SELECT 0')==0
    assert cn.active is None and all(c.closed for c in cn.cursors)
    assert 'mars' not in etl.connection_string().lower()
    assert cn.commits==cn.rollbacks==0


# Exact numerators/denominators independently reconciled to immutable Phase 3 sources.
KPI_PRECISION_CASES=[
    ('Average Freight / Order','average_freight_charge','2198275.64','96478'),
    ('AOV','average_order_value','13221498.11','96478'),
    ('On-Time Rate','on_time_delivery_rate','8993600','96470'),
    ('Average Duration','average_delivery_duration','103678285428','8216380800'),
    ('Average Review Score','average_review_score','400449','96361'),
    ('Repeat Customer Rate','repeat_customer_rate','280100','93358'),
]


def union_decimal_type(left,right):
    # Independent model of Microsoft's documented decimal UNION precision/scale rule.
    scale=max(left[1],right[1]);integer=max(left[0]-left[1],right[0]-right[1])
    return min(38,integer+scale),min(scale,38-integer)


def metric_arm_types(sql):
    lines=[line.strip() for line in sql.splitlines() if re.match(r"(?:UNION ALL )?SELECT '[^']+'",line.strip())]
    result={}
    for line in lines:
        match=re.match(r"(?:UNION ALL )?SELECT '([^']+)'(?: Metric)?,CONVERT\(decimal\((\d+),(\d+)\),",line)
        assert match,'Every metric arm must declare its type before UNION: '+line
        result[match[1]]=(int(match[2]),int(match[3]))
    assert len(result)==25
    return result


def test_union_of_decimal_sums_and_ratios_reproduces_scale_two_loss():
    assert union_decimal_type((38,10),(38,2))==(38,2)
    assert union_decimal_type((38,2),(38,20))==(38,2)
    assert union_decimal_type((38,10),(38,10))==(38,10)


@pytest.mark.parametrize('name,metric,numerator,denominator',KPI_PRECISION_CASES)
def test_all_six_kpis_preserve_phase3_values_and_original_tolerance(monkeypatch,name,metric,numerator,denominator):
    sql=(patch_root()/'sql/06_kpi_validation.sql').read_text(encoding='utf-8')
    types=metric_arm_types(sql)
    combined=next(iter(types.values()))
    for typ in list(types.values())[1:]:combined=union_decimal_type(combined,typ)
    assert combined==(38,10)
    with (PROJECT_ROOT/'reports/eda_kpi_summary.csv').open(encoding='utf-8',newline='') as f:
        expected=Decimal(next(r['value'] for r in csv.DictReader(f) if r['metric']==metric))
    with localcontext() as ctx:
        ctx.prec=70
        exact=Decimal(numerator)/Decimal(denominator)
        corrected=exact.quantize(Decimal(1).scaleb(-combined[1]),rounding=ROUND_HALF_UP)
        old=exact.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    tolerance=Decimal('.000001')
    monkeypatch.setattr(etl,'execute_file',lambda *a,**k:[(name,corrected)])
    result=etl.kpi_reconciliation(None,{name:(expected,tolerance)})[0]
    assert result['status']=='PASS' and Decimal(result['tolerance'])==tolerance
    assert abs(corrected-expected)<Decimal('0.0000000001')
    monkeypatch.setattr(etl,'execute_file',lambda *a,**k:[(name,old)])
    failed=etl.kpi_reconciliation(None,{name:(expected,tolerance)})[0]
    assert failed['status']=='FAIL' and abs(Decimal(failed['difference']))>tolerance
    with (PROJECT_ROOT/'reports/eda_kpi_summary.csv').open(encoding='utf-8',newline='') as f:
        reports={r['metric']:r for r in csv.DictReader(f)}
    pre={'datasets':{n:{'financial_totals':{c:'0'}} for n,c in [('order_items','price'),('payments','payment_value')]}}
    pre['datasets']['order_items']['financial_totals']['freight_value']='0'
    assert etl.expected_kpis(pre)[name]==(expected,tolerance)


@pytest.mark.parametrize('name,metric,numerator,denominator',KPI_PRECISION_CASES)
def test_each_ratio_has_decimal_operands_before_division(name,metric,numerator,denominator):
    sql=(patch_root()/'sql/06_kpi_validation.sql').read_text(encoding='utf-8')
    line=next(line for line in sql.splitlines() if "SELECT '"+name+"'" in line)
    if name=='Average Review Score':
        assert 'AVG(CONVERT(decimal(20,10),ReviewScore))' in line
    else:
        assert 'CONVERT(decimal(28,10),' in line
        assert '/CONVERT(decimal(19,0),' in line
    if name=='Average Duration':
        assert 'SUM(DATEDIFF_BIG(second,PurchaseTimestamp,ActualDeliveryTimestamp))' in line
        assert '/CONVERT(decimal(5,0),86400)' in line


def test_duration_storage_retains_ten_places_without_changing_transaction_guards():
    sql=(patch_root()/'sql/08_load_warehouse.sql').read_text(encoding='utf-8')
    line=next(line for line in sql.splitlines() if 'AS [DeliveryDurationDays]' in line)
    assert 'CONVERT(decimal(28,10),DATEDIFF_BIG(second,' in line
    assert '/CONVERT(decimal(5,0),86400)' in line
    assert 'CASE WHEN v.DurationEligible=1' in line


def test_failed_kpi_details_survive_after_rollback_without_committing_snapshot(monkeypatch,tmp_path):
    cn=setup_load(monkeypatch)
    monkeypatch.setattr(etl,'ROOT',tmp_path)
    kpi=dict(check='AOV',status='FAIL',actual='137.0400000000',expected='137.0415857501192',
             difference='-0.0015857501192',tolerance='0.000001',category='execution')
    monkeypatch.setattr(etl,'kpi_reconciliation',lambda *a:[kpi])
    with pytest.raises(ValueError,match='actual=137.0400000000'):
        etl.run_load({})
    assert cn.events.index('ROLLBACK')<cn.events.index('COMMIT FAIL')
    assert 'COMMIT PASS' not in cn.events
    files=list((tmp_path/'reports/phase_4_terminal_run').glob('failed_load_*_kpi_reconciliation.csv'))
    assert len(files)==1
    with files[0].open(encoding='utf-8',newline='') as f:row=next(csv.DictReader(f))
    assert row['actual']==kpi['actual'] and row['difference']==kpi['difference']
    assert row['tolerance']=='0.000001' and row['snapshot_status']=='ROLLED BACK'


def test_failure_diagnostic_io_error_does_not_replace_original_validation_error(monkeypatch):
    cn=setup_load(monkeypatch)
    row=dict(check='AOV',status='FAIL',actual='137.04',expected='137.0415857501192',category='execution')
    monkeypatch.setattr(etl,'kpi_reconciliation',lambda *a:[row])
    def fail(*a):raise OSError('read-only diagnostic folder')
    monkeypatch.setattr(etl,'persist_failed_kpis',fail)
    with pytest.raises(ValueError,match='Validation failed: AOV') as caught:etl.run_load({})
    assert any('Could not save' in s for s in caught.value.__notes__)
    assert cn.outcome=='FAIL' and cn.closed
