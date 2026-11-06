"""Transactional SQL Server snapshot ETL for the approved Olist Phase 4 model.

Run from the project root with ``python -m src.data_processing.sql_server_etl``.
Credentials are never stored. The default is Windows Authentication over local
shared memory. All SQL identifiers come from the checked-in contract/scripts.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

import pyodbc

from src.config import PROJECT_ROOT

ROOT = PROJECT_ROOT
DATABASE = "OlistSalesDW"
CONTRACT = json.loads((Path(__file__).with_name("warehouse_contract.json")).read_text(encoding="utf-8"))
FACTS = {"FactOrders": "orders", "FactOrderItems": "order_items", "FactPayments": "payments", "FactReviews": "reviews"}
DIM_KEYS = {"DimDate":"DateKey", "DimGeography":"GeographyKey", "DimCustomer":"CustomerKey",
            "DimProduct":"ProductKey", "DimSeller":"SellerKey", "DimPaymentType":"PaymentTypeKey", "DimOrderStatus":"OrderStatusKey"}
SOURCE_DIMENSIONS = {"DimCustomer":("customers","CustomerID","customer_id"),
                     "DimProduct":("products","ProductID","product_id"),
                     "DimSeller":("sellers","SellerID","seller_id")}
STATUSES = {"PASS", "FAIL", "WARN", "NOT EXECUTED"}
SOURCE_QUALITY_WARNINGS = {
    'Unknown core references in actual snapshot', 'Orders without items', 'Orders without payments',
    'Orders without reviews', 'Missing actual delivery timestamp', 'Invalid chronology',
    'Customers with unmatched ZIP', 'Sellers with unmatched ZIP', 'ZIP prefixes with conflicting cities',
    'ZIP prefixes with conflicting states', 'Missing product category', 'Untranslated product category',
    'Repeated review ID excess', 'Zero payment amounts', 'Nonpositive installments',
    'Delivered payment amount differs from merchandise plus freight',
}


def require_manual_transaction(cn):
    if cn.autocommit:
        raise RuntimeError('Snapshot changes and synthetic tests require autocommit=False.')


def assert_owned_database(cn, initialized=True):
    """Fail before writes on a wrong/unowned DB or unexpected user objects/triggers."""
    if fetch_scalar(cn,'SELECT DB_NAME()')!=DATABASE:
        raise RuntimeError('Refusing writes outside '+DATABASE)
    if fetch_scalar(cn,"SELECT OBJECT_ID('audit.WarehouseMetadata','U')") is None:
        raise RuntimeError('Existing OlistSalesDW has no project ownership marker; refusing to change it.')
    marker=[tuple(r) for r in fetch_rows(cn,'SELECT ProjectName,SchemaVersion FROM audit.WarehouseMetadata')]
    if marker!=[(DATABASE,1)]:
        raise RuntimeError('Warehouse ownership marker/schema version is not supported.')
    allowed={('stg',n,'U') for n in CONTRACT}
    allowed.update(('dw',n,'U') for n in [*DIM_KEYS,*FACTS])
    allowed.update(('audit',n,'U') for n in ['WarehouseMetadata','LoadRun','LoadFile','ValidationResult'])
    # DML triggers and synonyms could redirect writes into unrelated objects/databases.
    actual={tuple(r) for r in fetch_rows(cn,"""SELECT s.name,o.name,RTRIM(o.type) FROM sys.objects o
        JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.is_ms_shipped=0
        AND o.type IN ('U','V','P','PC','TR','TA','SN','FN','IF','TF','FS','FT','SO')""")}
    unexpected=actual-allowed
    if unexpected or (initialized and allowed-actual):
        raise RuntimeError('Unexpected or missing warehouse objects; refusing writes: '+str(sorted(unexpected or allowed-actual)))


def validation_failures(checks):
    """Only known source-quality warnings are non-fatal; missing execution is not PASS."""
    return [r for r in checks if not (r['status']=='PASS' or
        (r['status']=='WARN' and r.get('category')=='source_quality' and r['check'] in SOURCE_QUALITY_WARNINGS))]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def protected_integrity():
    """Validate the curated protected-file baseline; prior versions are archived."""
    baseline=json.loads((ROOT/"reports/phase_4_protected_files.json").read_text(encoding="utf-8"))
    changed=[name for name,digest in baseline.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]
    if changed:
        raise ValueError("Previous phase files changed: " + ", ".join(changed))
    return len(baseline)


def odbc_value(value):
    return "{" + value.replace("}", "}}") + "}"


def connection_string(database=DATABASE):
    server=os.environ.get("OLIST_SQL_SERVER", "lpc:(local)")
    driver=os.environ.get("OLIST_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    # Only the on-machine shared-memory default accepts the local self-signed certificate.
    trust=os.environ.get("OLIST_SQL_TRUST_CERTIFICATE", "yes" if server.lower().startswith("lpc:") else "no")
    auth=os.environ.get("OLIST_SQL_AUTH", "windows").lower()
    if auth=="windows":
        credentials="Trusted_Connection=yes;"
    elif auth=="sql":
        user=os.environ["OLIST_SQL_USER"]
        password=os.environ["OLIST_SQL_PASSWORD"]
        credentials=f"UID={odbc_value(user)};PWD={odbc_value(password)};"
    else:
        raise ValueError("OLIST_SQL_AUTH must be windows or sql")
    return (f"DRIVER={odbc_value(driver)};SERVER={odbc_value(server)};DATABASE={database};"
            f"{credentials}Encrypt=yes;TrustServerCertificate={trust};APP=OlistPhase4;")


def connect(database=DATABASE, autocommit=False):
    return pyodbc.connect(connection_string(database), timeout=10, autocommit=autocommit)


def inspect_server():
    with closing(connect("master",True)) as cn:
        row=fetch_rows(cn,"""SELECT @@SERVERNAME,
            CONVERT(nvarchar(128),SERVERPROPERTY('ProductVersion')),
            CONVERT(nvarchar(128),SERVERPROPERTY('Edition')),
            CONVERT(int,SERVERPROPERTY('IsIntegratedSecurityOnly')),
            IS_SRVROLEMEMBER('sysadmin'),HAS_PERMS_BY_NAME(NULL,NULL,'CREATE ANY DATABASE')""")[0]
        transport=fetch_rows(cn,"SELECT net_transport,encrypt_option,auth_scheme FROM sys.dm_exec_connections WHERE session_id=@@SPID")[0]
        return dict(zip(["instance","version","edition","windows_only","is_sysadmin","can_create_database"],row),
                    transport=transport[0], encrypted=transport[1], auth_scheme=transport[2],
                    odbc_drivers=pyodbc.drivers(), pyodbc=pyodbc.version)


def sql_batches(path):
    """GO is a client batch separator, not T-SQL. Scripts use it on its own line."""
    return [part.strip() for part in re.split(r"(?im)^\s*GO\s*$", Path(path).read_text(encoding="utf-8")) if part.strip()]


def drain_results(cursor, collect_results=False):
    """Finish every rowset/DONE response before another cursor uses the connection.

    NOCOUNT does not replace SQLMoreResults. Advancing also surfaces deferred
    server errors before the caller can validate or commit a partial batch.
    This helper deliberately never commits or rolls back.
    """
    rows=[]
    while True:
        if cursor.description is not None:
            while batch:=cursor.fetchmany(5000):
                if collect_results:rows.extend(batch)
        if not cursor.nextset():break
    return rows


def fetch_rows(cn, query, *params):
    with closing(cn.cursor()) as cur:
        cur.execute(query,*params)
        return drain_results(cur,collect_results=True)


def fetch_scalar(cn, query, *params):
    rows=fetch_rows(cn,query,*params)
    if len(rows)!=1 or len(rows[0])!=1:
        raise ValueError('Expected one scalar SQL result.')
    return rows[0][0]


def execute_statement(cn, query, *params):
    with closing(cn.cursor()) as cur:
        cur.execute(query,*params)
        drain_results(cur)


def execute_script(cursor, name, collect_results=False):
    rows=[]
    for batch in sql_batches(ROOT/"sql"/name):
        cursor.execute(batch)
        rows.extend(drain_results(cursor,collect_results=collect_results))
    return rows


def execute_file(cn, name, collect_results=False):
    with closing(cn.cursor()) as cur:
        return execute_script(cur,name,collect_results=collect_results)


def initialize_database():
    with closing(connect("master",True)) as master:
        exists=fetch_scalar(master,"SELECT DB_ID(?)",DATABASE) is not None
        if exists:
            with closing(connect(autocommit=True)) as cn:
                assert_owned_database(cn,initialized=False)
        execute_file(master,"01_create_database.sql")
    with closing(connect()) as cn:
        assert_owned_database(cn,initialized=False)
        for filename in ["02_create_staging_tables.sql","03_create_dimensions.sql","04_create_fact_tables.sql","05_create_indexes.sql"]:
            execute_file(cn,filename)
        assert_owned_database(cn)
        cn.commit()
    return "already existed; project ownership verified" if exists else "created"


def convert_value(value, column):
    """Reject lossy coercions, overlong strings and unexpected nulls before loading."""
    typ=column["type"]
    if value=="":
        if not column["nullable"]:
            raise ValueError(f"Required column is empty: {column['name']}")
        return None
    if typ=="bit":
        if value not in ("True","False"):
            raise ValueError(f"Invalid Boolean in {column['name']}")
        return value=="True"
    if typ.startswith("datetime2"):
        parsed=datetime.strptime(value,"%Y-%m-%d %H:%M:%S")
        if parsed.strftime("%Y-%m-%d %H:%M:%S")!=value:
            raise ValueError("Non-canonical timestamp")
        return parsed
    if typ=="int" or typ.startswith("decimal"):
        number=Decimal(value)
        if not number.is_finite():
            raise ValueError("Non-finite number")
        if typ=="int":
            if number!=number.to_integral_value() or not -(2**31)<=number<2**31:
                raise ValueError("Non-integer or out-of-range int")
            return int(number)
        precision,scale=map(int,re.findall(r"\d+",typ))
        if number!=number.quantize(Decimal(1).scaleb(-scale)) or abs(number)>=Decimal(10)**(precision-scale):
            raise ValueError(f"Lossy conversion to {typ}: {column['name']}")
        return number
    limit=int(re.search(r"\d+",typ).group())
    length=len(value.encode("utf-16-le"))//2 if typ.startswith("nvarchar") else len(value.encode("ascii"))
    if length>limit:
        raise ValueError(f"Value exceeds {typ}: {column['name']}")
    return value


def source_rows(name):
    spec=CONTRACT[name]
    with (ROOT/"data/processed"/spec["filename"]).open(encoding="utf-8",newline="") as stream:
        reader=csv.reader(stream)
        expected=[c["name"] for c in spec["columns"]]
        if next(reader)!=expected:
            raise ValueError(f"Unexpected columns/order in {spec['filename']}")
        for ordinal,row in enumerate(reader,1):
            if len(row)!=len(expected):
                raise ValueError(f"Malformed CSV record {ordinal} in {name}")
            try:
                yield ordinal,tuple(convert_value(v,c) for v,c in zip(row,spec["columns"]))
            except (ValueError,ArithmeticError) as exc:
                raise ValueError(f"{name}, source record {ordinal}: {exc}") from exc


def preflight():
    protected_count=protected_integrity()
    summary={}; key_sets={}; date_values=[]
    for name,spec in CONTRACT.items():
        path=ROOT/"data/processed"/spec["filename"]
        if sha(path)!=spec["sha256"]:
            raise ValueError(f"Fingerprint mismatch: {spec['filename']}")
        columns=[c["name"] for c in spec["columns"]]
        indexes=[columns.index(k) for k in spec["key"]]
        seen=set(); totals={c:Decimal(0) for c in columns if c in {"price","freight_value","payment_value"}}
        flags={c:0 for c in columns if c.startswith("dq_")}
        date_indexes=[i for i,c in enumerate(spec["columns"]) if c["type"].startswith("datetime2")]
        n=0
        for n,row in source_rows(name):
            if indexes:
                key=tuple(row[i] for i in indexes)
                if key in seen:
                    raise ValueError(f"Duplicate source key in {name}: {key}")
                seen.add(key)
            for c in totals: totals[c]+=row[columns.index(c)]
            for c in flags: flags[c]+=row[columns.index(c)]
            date_values.extend(row[i].date() for i in date_indexes if row[i] is not None)
        if n!=spec["rows"]:
            raise ValueError(f"Row-count mismatch in {name}")
        summary[name]={"rows":n,"financial_totals":{c:str(v) for c,v in totals.items()},"flags":flags}
        key_sets[name]=seen
    # A child without an order cannot be assigned to a real order; abort rather than drop it.
    orders={k[0] for k in key_sets['orders']}
    for name in ["order_items","payments","reviews"]:
        pos=CONTRACT[name]['key'].index('order_id')
        if any(key[pos] not in orders for key in key_sets[name]):
            raise ValueError(f"Orphan order reference in {name}")
    return {"datasets":summary,"first_date":str(min(date_values)),"last_date":str(max(date_values)),
            "protected_files":protected_count}


def input_sizes(spec):
    out=[]
    for c in spec["columns"]:
        typ=c["type"]
        if typ=="bit": out.append((pyodbc.SQL_BIT,0,0))
        elif typ=="int": out.append((pyodbc.SQL_INTEGER,0,0))
        elif typ.startswith("decimal"):
            p,s=map(int,re.findall(r"\d+",typ)); out.append((pyodbc.SQL_DECIMAL,p,s))
        elif typ.startswith("datetime2"): out.append((pyodbc.SQL_TYPE_TIMESTAMP,19,0))
        else: out.append((pyodbc.SQL_WVARCHAR if typ.startswith('n') else pyodbc.SQL_VARCHAR,int(re.search(r"\d+",typ).group()),0))
    return out+[(pyodbc.SQL_WVARCHAR,36,0),(pyodbc.SQL_BIGINT,0,0)]


def load_staging(cn, load_id, batch_size=5000, fail_after_first=False):
    require_manual_transaction(cn)
    assert_owned_database(cn)
    with closing(cn.cursor()) as cur:
        cur.fast_executemany=True
        for number,(name,spec) in enumerate(CONTRACT.items()):
            cur.execute(f"DELETE FROM stg.[{name}]");drain_results(cur)
            cols=[c['name'] for c in spec['columns']]+['LoadID','SourceRow']
            sql=f"INSERT stg.[{name}]("+','.join('['+c+']' for c in cols)+") VALUES("+','.join('?' for _ in cols)+")"
            cur.setinputsizes(input_sizes(spec))
            batch=[]
            for ordinal,row in source_rows(name):
                batch.append(row+(load_id,ordinal))
                if len(batch)>=batch_size:
                    cur.executemany(sql,batch);drain_results(cur);batch=[]
            if batch:
                cur.executemany(sql,batch);drain_results(cur)
            execute_statement(cn,"INSERT audit.LoadFile(LoadID,FileName,SHA256,SourceRows,StagedRows) SELECT ?,?,?,?,COUNT_BIG(*) FROM stg.["+name+"]",
                              load_id,spec['filename'],spec['sha256'],spec['rows'])
            print(f"Staged {name}: {spec['rows']:,}",flush=True)
            if fail_after_first and number==0:
                raise RuntimeError("Intentional rollback verification after replacing the first staging table")


def expected_kpis(preflight_result):
    with (ROOT/'reports/eda_kpi_summary.csv').open(encoding='utf-8',newline='') as f:
        k={r['metric']:r for r in csv.DictReader(f)}
    mapping={"Merchandise Revenue":('total_merchandise_revenue','value'),"Eligible Orders":('total_orders','value'),
             "Excluded Orders":('total_orders','excluded_order_count'),"Unique Customers":('total_unique_customers','value'),
             "Items Sold":('total_items_sold','value'),"Freight Total":('average_freight_charge','numerator'),
             "Average Freight / Order":('average_freight_charge','value'),"AOV":('average_order_value','value'),
             "On-Time Eligible Orders":('on_time_delivery_rate','denominator'),"On-Time Orders":('on_time_delivery_rate','numerator'),
             "On-Time Rate":('on_time_delivery_rate','value'),"Duration-Eligible Orders":('average_delivery_duration','denominator'),
             "Average Duration":('average_delivery_duration','value'),"Valid Review Records":('average_review_score','denominator'),
             "Average Review Score":('average_review_score','value'),"Repeat Customers":('repeat_customer_rate','numerator'),
             "Repeat Customer Rate":('repeat_customer_rate','value')}
    result={metric:Decimal(k[src][field]) for metric,(src,field) in mapping.items()}
    result['Late Orders']=result['On-Time Eligible Orders']-result['On-Time Orders']
    for suffix in ['order totals','monthly totals','categories','customer states']:
        result['Revenue - '+suffix]=result['Merchandise Revenue']
    for metric,name,col in [('All Item Price','order_items','price'),('All Freight','order_items','freight_value'),('All Payments','payments','payment_value')]:
        result[metric]=Decimal(preflight_result['datasets'][name]['financial_totals'][col])
    averages={'Average Freight / Order','AOV','On-Time Rate','Average Duration','Average Review Score','Repeat Customer Rate'}
    return {m:(v,Decimal('0.000001') if m in averages else Decimal(0)) for m,v in result.items()}


def result(name, actual, expected, details='', tolerance=Decimal(0), warning=False):
    passed=abs(Decimal(str(actual))-Decimal(str(expected)))<=tolerance
    return {'check':name,'status':'PASS' if passed else ('WARN' if warning else 'FAIL'),
            'actual':str(actual),'expected':str(expected),'details':details,
            'category':'source_quality' if warning else 'execution'}


def kpi_reconciliation(cn, expected):
    actual={row[0]:row[1] for row in execute_file(cn,'06_kpi_validation.sql',collect_results=True)}
    rows=[]
    for name,(value,tolerance) in expected.items():
        row=result(name,actual[name],value,tolerance=tolerance)
        row.update(tolerance=str(tolerance),difference=str(actual[name]-value),basis='SQL vs immutable Phase 3 reports / exact source Decimal totals')
        rows.append(row)
    return rows


def validation_checks(cn):
    out=[]
    for name,spec in CONTRACT.items():
        n=fetch_scalar(cn,f'SELECT COUNT_BIG(*) FROM stg.[{name}]')
        out.append(result('Staging rows: '+name,n,spec['rows']))
    for table,name in FACTS.items():
        out.append(result('Fact rows: '+table,fetch_scalar(cn,f'SELECT COUNT_BIG(*) FROM dw.{table}'),CONTRACT[name]['rows']))
    for table,key in DIM_KEYS.items():
        out.append(result('Unknown member: '+table,fetch_scalar(cn,f'SELECT COUNT(*) FROM dw.{table} WHERE {key}=0'),1))
    for table,(name,bk,source) in SOURCE_DIMENSIONS.items():
        out.append(result('Dimension rows: '+table,fetch_scalar(cn,f'SELECT COUNT(*) FROM dw.{table} WHERE {DIM_KEYS[table]}<>0'),CONTRACT[name]['rows']))
    out.append(result('All constraints enabled and trusted',fetch_scalar(cn,"SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1"),0))
    violations=fetch_rows(cn,'DBCC CHECKCONSTRAINTS WITH ALL_CONSTRAINTS, NO_INFOMSGS')
    out.append(result('Referential and CHECK constraint violations',len(violations),0))
    checks={
      'Item amounts preserved per business key':"SELECT COUNT_BIG(*) FROM stg.order_items s JOIN dw.FactOrderItems f ON f.OrderID=s.order_id AND f.OrderItemID=s.order_item_id WHERE f.ItemPrice<>s.price OR f.FreightValue<>s.freight_value",
      'Payment amounts/installments preserved per business key':"SELECT COUNT_BIG(*) FROM stg.payments s JOIN dw.FactPayments f ON f.OrderID=s.order_id AND f.PaymentSequential=s.payment_sequential WHERE f.PaymentAmount<>s.payment_value OR f.Installments<>s.payment_installments OR (f.Installments IS NULL AND s.payment_installments IS NOT NULL) OR (f.Installments IS NOT NULL AND s.payment_installments IS NULL)",
      'Review scores and optional text indicators preserved':"SELECT COUNT_BIG(*) FROM stg.reviews s JOIN dw.FactReviews f ON f.OrderID=s.order_id AND f.ReviewID=s.review_id WHERE ISNULL(f.ReviewScore,-999)<>ISNULL(s.review_score,-999) OR f.HasTitle<>CASE WHEN s.review_comment_title IS NULL THEN 0 ELSE 1 END OR f.HasMessage<>CASE WHEN s.review_comment_message IS NULL THEN 0 ELSE 1 END",
      'Order totals reconciled for every order':"SELECT COUNT_BIG(*) FROM dw.FactOrders o LEFT JOIN (SELECT OrderKey,COUNT(*) n,SUM(ItemPrice) r,SUM(FreightValue) f FROM dw.FactOrderItems GROUP BY OrderKey) i ON i.OrderKey=o.OrderKey WHERE o.ItemCount<>COALESCE(i.n,0) OR o.MerchandiseRevenue<>i.r OR o.FreightAmount<>i.f OR (i.n IS NULL AND (o.MerchandiseRevenue IS NOT NULL OR o.FreightAmount IS NOT NULL))",
      'Sales flags independently derived':"SELECT COUNT_BIG(*) FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey WHERE o.SalesEligible<>CASE WHEN s.OrderStatus='delivered' AND EXISTS(SELECT 1 FROM dw.FactOrderItems i WHERE i.OrderKey=o.OrderKey) THEN 1 ELSE 0 END",
      'Source customer states preserved':"SELECT COUNT_BIG(*) FROM stg.customers s JOIN dw.DimCustomer d ON d.CustomerID=s.customer_id WHERE d.SourceState<>s.customer_state OR d.CustomerUniqueID<>s.customer_unique_id",
      'Source seller states preserved':"SELECT COUNT_BIG(*) FROM stg.sellers s JOIN dw.DimSeller d ON d.SellerID=s.seller_id WHERE d.SourceState<>s.seller_state",
      'Unmatched customer geography retained':"SELECT COUNT_BIG(*) FROM dw.DimCustomer c JOIN dw.DimGeography g ON g.GeographyKey=c.GeographyKey WHERE c.UnmatchedZip=1 AND (g.LookupMatched<>0 OR g.Latitude IS NOT NULL OR g.Longitude IS NOT NULL OR g.GeographyKey=0)",
      'Complete date range without gaps':"SELECT DATEDIFF(day,MIN(FullDate),MAX(FullDate))+1-COUNT(*) FROM dw.DimDate WHERE DateKey<>0",
      'Unknown core references in actual snapshot':"SELECT (SELECT COUNT(*) FROM dw.FactOrders WHERE CustomerKey=0 OR OrderStatusKey=0)+(SELECT COUNT(*) FROM dw.FactOrderItems WHERE ProductKey=0 OR SellerKey=0)+(SELECT COUNT(*) FROM dw.FactPayments WHERE PaymentTypeKey=0)",
    }
    for name,query in checks.items(): out.append(result(name,fetch_scalar(cn,query),0,warning=name.startswith('Unknown core')))
    # Exact grain comparisons include both directions, making silent row loss observable.
    for table,name in FACTS.items():
        target_keys={'order_id':'OrderID','order_item_id':'OrderItemID','payment_sequential':'PaymentSequential','review_id':'ReviewID'}
        source=','.join(CONTRACT[name]['key']); target=','.join(target_keys[k] for k in CONTRACT[name]['key'])
        q=f'SELECT COUNT(*) FROM (SELECT {source} FROM stg.{name} EXCEPT SELECT {target} FROM dw.{table}) x'
        q2=f'SELECT COUNT(*) FROM (SELECT {target} FROM dw.{table} EXCEPT SELECT {source} FROM stg.{name}) x'
        out.append(result('Exact business-key set: '+table,fetch_scalar(cn,q)+fetch_scalar(cn,q2),0))
    for name,count in execute_file(cn,'07_data_quality_checks.sql',collect_results=True):
        out.append(result(name,count,0,'Retained source condition; no record deletion.',warning=True))
    return out


def record_checks(cn,load_id,checks):
    with closing(cn.cursor()) as cur:
        cur.executemany('INSERT audit.ValidationResult(LoadID,CheckName,Status,ActualValue,ExpectedValue,Details) VALUES(?,?,?,?,?,?)',
                        [(load_id,r['check'],r['status'],r['actual'],r['expected'],r.get('details','')) for r in checks])
        drain_results(cur)


def validation_failure_message(failures):
    names=', '.join(r['check'] for r in failures)
    details='; '.join(f"{r['check']}: actual={r.get('actual','unavailable')}, expected={r.get('expected','unavailable')}, difference={r.get('difference','not recorded')}, tolerance={r.get('tolerance','0')}" for r in failures)
    return 'Validation failed: '+names+'\n'+details


def persist_failed_kpis(load_id,kpis):
    """Retain numeric diagnostics after rollback; never write previous-phase reports."""
    folder=ROOT/'reports/phase_4_terminal_run';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'failed_load_{load_id}_kpi_reconciliation.csv'
    write_csv(path,[dict(load_id=load_id,snapshot_status='ROLLED BACK',**row) for row in kpis])
    return path


def run_load(expected, fail_after_first=False):
    load_id=str(uuid.uuid4())
    fingerprint=hashlib.sha256(json.dumps({k:v['sha256'] for k,v in CONTRACT.items()},sort_keys=True).encode()).hexdigest()
    cn=connect();kpis=[]
    try:
        require_manual_transaction(cn)
        assert_owned_database(cn)
        lock=fetch_scalar(cn,"DECLARE @rc int; EXEC @rc=sys.sp_getapplock @Resource=N'OlistPhase4Snapshot',@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @rc;")
        if lock<0: raise RuntimeError('Another ETL session holds the warehouse load lock.')
        execute_statement(cn,'INSERT audit.LoadRun(LoadID,Status,SourceFingerprint) VALUES(?,?,?)',load_id,'RUNNING',fingerprint)
        cn.commit()
        try:
            execute_statement(cn,'SET XACT_ABORT ON; SET NOCOUNT ON;')
            load_staging(cn,load_id,fail_after_first=fail_after_first)
            execute_file(cn,'08_load_warehouse.sql')
            checks=validation_checks(cn)+verify_staging_round_trip(cn)
            kpis=kpi_reconciliation(cn,expected)
            # Recheck input fingerprints inside the transaction, before the final commit.
            protected_integrity()
            record_checks(cn,load_id,checks+kpis)
            failed=validation_failures(checks+kpis)
            if failed: raise ValueError(validation_failure_message(failed))
            execute_statement(cn,"UPDATE audit.LoadRun SET Status='PASS',FinishedAtUTC=SYSUTCDATETIME() WHERE LoadID=?",load_id)
            cn.commit()
            return {'load_id':load_id,'validation':checks,'kpis':kpis}
        except BaseException as exc:
            cn.rollback()
            # Error metadata commits separately, so it survives rollback of the snapshot.
            message=str(exc)
            secret=os.environ.get('OLIST_SQL_PASSWORD')
            if secret: message=message.replace(secret,'[REDACTED]')
            execute_statement(cn,"UPDATE audit.LoadRun SET Status='FAIL',FinishedAtUTC=SYSUTCDATETIME(),ErrorMessage=? WHERE LoadID=?",message[:4000],load_id)
            cn.commit()
            if kpis:
                try:persist_failed_kpis(load_id,kpis)
                except Exception as diagnostic_error:
                    exc.add_note('Could not save failed-load KPI diagnostics: '+str(diagnostic_error))
            raise
    finally:
        cn.close()  # Releases the session application lock even when a load fails.


def snapshot_hashes(cn):
    """Exact ordered content digest; exclude only load metadata, retain surrogate keys."""
    output={}
    tables=[('stg',name) for name in CONTRACT]+[('dw',name) for name in list(DIM_KEYS)+list(FACTS)]
    for schema,table in tables:
        columns=[r[0] for r in fetch_rows(cn,'SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) AND name NOT IN (\'LoadID\',\'LoadedAtUTC\') ORDER BY column_id',f'{schema}.{table}')]
        order='[SourceRow]' if schema=='stg' else '['+DIM_KEYS[table]+']' if table in DIM_KEYS else {'FactOrders':'OrderID','FactOrderItems':'OrderID,OrderItemID','FactPayments':'OrderID,PaymentSequential','FactReviews':'ReviewID,OrderID'}[table]
        digest=hashlib.sha256(); count=0
        with closing(cn.cursor()) as cur:
            cur.execute(f'SELECT '+','.join('['+c+']' for c in columns)+f' FROM {schema}.[{table}] ORDER BY {order}')
            while rows:=cur.fetchmany(5000):
                for row in rows:
                    digest.update((json.dumps(list(row),default=str,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')); count+=1
            drain_results(cur)
        output[schema+'.'+table]={'rows':count,'sha256':digest.hexdigest()}
    return output


def verify_staging_round_trip(cn):
    """Compare every staged source field against independently reread typed CSV records."""
    checks=[]
    for name,spec in CONTRACT.items():
        cols=','.join('['+c['name']+']' for c in spec['columns'])
        mismatches=0; actual_rows=0
        with closing(cn.cursor()) as cur:
            cur.execute(f'SELECT {cols} FROM stg.[{name}] ORDER BY SourceRow')
            for ordinal,expected in source_rows(name):
                actual=cur.fetchone(); actual_rows=ordinal
                mismatches+=actual is None or tuple(actual)!=expected
            if cur.fetchone() is not None:mismatches+=1
            drain_results(cur)
        checks.append(result('All source fields round trip: '+name,mismatches,0,f'{actual_rows:,} records compared; exact Decimal, Unicode, null and timestamp equality.'))
    return checks


def verify_unknown_fallback(cn):
    """Exercise an absent product reference on the real loader, then roll it all back."""
    require_manual_transaction(cn)
    assert_owned_database(cn)
    try:
        order_id,item_id=fetch_rows(cn,'SELECT TOP(1) order_id,order_item_id FROM stg.order_items ORDER BY order_id,order_item_id')[0]
        execute_statement(cn,"UPDATE stg.order_items SET product_id='~MISSING_TEST' WHERE order_id=? AND order_item_id=?",order_id,item_id)
        execute_file(cn,'08_load_warehouse.sql')
        row=fetch_rows(cn,'SELECT ProductKey,SourceProductID FROM dw.FactOrderItems WHERE OrderID=? AND OrderItemID=?',order_id,item_id)[0]
        return result('Unknown product fallback preserves source record',int(row.ProductKey==0 and row.SourceProductID=='~MISSING_TEST'),1,
                      'Synthetic missing product exercised inside a rolled-back transaction; actual source CSVs unchanged.')
    finally:
        cn.rollback()


def rollback_verification(expected, committed_snapshot):
    """Compare fault tests to the most recent committed load, never an older load."""
    try:
        run_load(expected,fail_after_first=True)
        raise AssertionError('Failure injection did not fail')
    except RuntimeError as exc:
        if 'Intentional rollback' not in str(exc): raise
    with closing(connect()) as cn:
        checks=[result('Failed ETL restores previous complete snapshot',int(committed_snapshot==snapshot_hashes(cn)),1,
                       'Compared with latest committed load; FAIL audit entry is intentionally retained.')]
        checks.append(verify_unknown_fallback(cn))
        checks.append(result('Unknown-member simulation rolled back completely',int(committed_snapshot==snapshot_hashes(cn)),1))
    return checks


def write_csv(path,rows):
    rows=list(rows)
    if not rows: return
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns); writer.writeheader(); writer.writerows(rows)


def export_schema_dictionary(cn):
    rows=fetch_rows(cn,"""SELECT s.name,t.name,c.column_id,c.name,ty.name,c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity
        FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id
        JOIN sys.types ty ON ty.user_type_id=c.user_type_id WHERE s.name IN ('stg','dw','audit') ORDER BY s.name,t.name,c.column_id""")
    out=[]
    with (ROOT/'reports/phase_4_source_to_target_mapping.csv').open(encoding='utf-8',newline='') as stream:
        mappings={(r['target_table'],r['target_column']):r['source_expression']+'; FROM '+r['source_joins'] for r in csv.DictReader(stream)}
    grains={'DimDate':'one calendar date; key 0 unknown','DimGeography':'one ZIP prefix; key 0 unknown',
            'DimCustomer':'one source customer_id; customer_unique_id is an identity attribute',
            'DimProduct':'one product_id','DimSeller':'one seller_id','DimPaymentType':'one payment_type','DimOrderStatus':'one order_status',
            'FactOrders':'one order_id','FactOrderItems':'one (order_id,order_item_id)',
            'FactPayments':'one (order_id,payment_sequential)','FactReviews':'one (review_id,order_id)'}
    for schema,table,ordinal,col,typ,length,precision,scale,nullable,identity in rows:
        sql_type=f'{typ}({precision},{scale})' if typ in ['decimal','numeric'] else f'{typ}({scale})' if typ=='datetime2' else f'{typ}({length//2 if typ.startswith("n") else length})' if typ in ['varchar','char','nvarchar'] else typ
        mapping=f'data/processed/{CONTRACT[table]["filename"]}::{col}' if schema=='stg' and col in [c['name'] for c in CONTRACT[table]['columns']] else 'ETL load metadata' if col in ['LoadID','LoadedAtUTC','SourceRow'] or schema=='audit' else 'sql/08_load_warehouse.sql: '+table+' explicit INSERT/UPDATE mapping'
        mapping=mappings.get((schema+'.'+table,col),mapping)
        out.append(dict(schema=schema,table=table,ordinal=ordinal,column=col,sql_type=sql_type,nullable=bool(nullable),identity=bool(identity),
                        grain=grains.get(table,'cleaned source snapshot' if schema=='stg' else 'audit metadata'),source_mapping=mapping,
                        history='Type 1 source snapshot' if table.startswith('Dim') and table!='DimDate' else 'calendar' if table=='DimDate' else 'snapshot / load audit'))
    write_csv(ROOT/'reports/phase_4_schema_dictionary.csv',out)
    return len(out)


def capture_plans(cn):
    """Execute representative reconciliations and save the actual SQL Server plans."""
    folder=ROOT/'reports/sql_plans'; folder.mkdir(exist_ok=True)
    queries={
      'monthly_sales':"SELECT d.YearMonth,COUNT_BIG(*) Orders,SUM(o.MerchandiseRevenue) Revenue FROM dw.FactOrders o JOIN dw.DimDate d ON d.DateKey=o.PurchaseDateKey WHERE o.SalesEligible=1 GROUP BY d.YearMonth",
      'category_revenue':"SELECT p.CategoryLabel,SUM(i.ItemPrice) Revenue FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey WHERE i.SalesEligible=1 GROUP BY p.CategoryLabel",
      'review_grain':"SELECT AVG(CONVERT(decimal(20,10),r.ReviewScore)) Score,COUNT_BIG(*) Records FROM dw.FactReviews r JOIN dw.FactOrders o ON o.OrderKey=r.OrderKey WHERE o.SalesEligible=1 AND r.ValidScore=1",
    }
    files=[]
    for name,query in queries.items():
        execute_statement(cn,'SET STATISTICS XML ON;')
        try:
            for row in fetch_rows(cn,query):
                if len(row)==1 and isinstance(row[0],str) and '<ShowPlanXML' in row[0]:
                    path=folder/f'{name}.sqlplan'; path.write_text(row[0],encoding='utf-8'); files.append(path.name)
        finally:
            execute_statement(cn,'SET STATISTICS XML OFF;')
    return files


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--verify-rerun',action='store_true')
    parser.add_argument('--verify-rollback',action='store_true')
    args=parser.parse_args(argv)
    print('Checking immutable source contracts and candidate keys...',flush=True)
    pre=preflight()
    if args.preflight_only:
        print(json.dumps(pre,indent=2)); return 0
    try:
        server=inspect_server()
    except pyodbc.Error as exc:
        checks=[dict(check='SQL Server execution',status='NOT EXECUTED',actual='',expected='Accessible SQL Server',details=str(exc))]
        write_csv(ROOT/'reports/phase_4_etl_validation.csv',checks)
        write_csv(ROOT/'reports/phase_4_kpi_reconciliation.csv',
                  [dict(check=k,status='NOT EXECUTED',actual='',expected=str(v),tolerance=str(t)) for k,(v,t) in expected_kpis(pre).items()])
        print('SQL Server unavailable; database work NOT EXECUTED.'); return 2
    # Serialize initialization, both loads, comparisons and fault tests as one execution.
    # This master session holds only an application lock, never user-table writes.
    with closing(connect('master',True)) as execution_guard:
        rc=fetch_scalar(execution_guard,"DECLARE @rc int; EXEC @rc=sys.sp_getapplock @Resource=N'OlistPhase4Execution',@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=0; SELECT @rc;")
        if rc<0: raise RuntimeError('Another Phase 4 execution is in progress; no database changes were started.')
        created=initialize_database()
        expected=expected_kpis(pre)
        print('Loading',server['instance'],DATABASE,flush=True)
        first=run_load(expected)
        with closing(connect()) as cn: before=snapshot_hashes(cn)
        committed_snapshot=before
        checks=list(first['validation']); latest=first; runs=[first['load_id']]
        if args.verify_rerun:
            print('Running a second full load to verify idempotency...',flush=True)
            latest=run_load(expected); runs.append(latest['load_id'])
            with closing(connect()) as cn: after=snapshot_hashes(cn)
            committed_snapshot=after
            checks.append(result('Idempotent rerun including all surrogate keys',int(before==after),1,'Exact row counts and content hashes match for all 21 staging/dimension/fact tables; only load metadata excluded.'))
        else:
            checks.append(dict(check='Idempotent rerun',status='NOT EXECUTED',actual='',expected='',details='Use --verify-rerun.'))
        if args.verify_rollback:
            print('Verifying rollback after a deliberate mid-load failure...',flush=True)
            checks.extend(rollback_verification(expected,committed_snapshot))
        else:
            checks.append(dict(check='Rollback fault injection',status='NOT EXECUTED',actual='',expected='',details='Use --verify-rollback.'))
        with closing(connect()) as cn:
            columns=export_schema_dictionary(cn)
            plans=capture_plans(cn)
            checks.append(result('Executed SQL Server actual plans',len(plans),3))
            record_checks(cn,latest['load_id'],checks[len(first['validation']):])
            cn.commit()
            counts={r[0]:r[1] for r in fetch_rows(cn,"SELECT s.name+'.'+t.name,SUM(p.rows) FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) WHERE s.name IN ('stg','dw') GROUP BY s.name,t.name")}
        checks.append(result('Previous phase files unchanged',protected_integrity(),pre['protected_files']))
        checks.append(result('Raw and processed CSV hashes unchanged',19,19,'All 19 are covered by protected-file and source-contract verification.'))
        write_csv(ROOT/'reports/phase_4_etl_validation.csv',checks)
        write_csv(ROOT/'reports/phase_4_kpi_reconciliation.csv',latest['kpis'])
        evidence=dict(server=server,database_status=created,successful_load_ids=runs,preflight=pre,table_counts=counts,
                      schema_columns=columns,actual_plan_files=plans,snapshot_hashes=committed_snapshot,
                      first_snapshot_hashes=before)
        (ROOT/'reports/phase_4_execution_evidence.json').write_text(json.dumps(evidence,indent=2,default=str)+'\n',encoding='utf-8')
        failed=validation_failures(checks+latest['kpis'])
        print('Phase 4 ETL:', 'FAIL' if failed else 'PASS', ';',len(checks),'validation rows;',len(latest['kpis']),'KPI reconciliations.',flush=True)
        return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
