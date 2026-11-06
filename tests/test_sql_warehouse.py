"""Independent source/SQL checks. Live tests skip unless OLIST_SQL_TESTS=1.

Skipped live tests mean NOT EXECUTED, never a warehouse PASS. No test commits
changes to source data or the database; fault injection is performed by the ETL
verification command and independently checked here through its audit evidence.
"""
import csv
from decimal import Decimal
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from src.config import PROJECT_ROOT as ROOT
from src.data_processing.sql_server_etl import CONTRACT, connect, convert_value, sql_batches


@pytest.fixture(scope='module')
def db():
    if os.environ.get('OLIST_SQL_TESTS')!='1':
        pytest.skip('NOT EXECUTED: set OLIST_SQL_TESTS=1 for live SQL Server validation')
    cn=connect()
    yield cn
    cn.rollback(); cn.close()


@pytest.fixture(scope='module')
def source():
    names=['orders','customers','order_items','payments','reviews','products','sellers']
    return {n:pd.read_csv(ROOT/'data/processed'/f'{n}_clean.csv',dtype='string',keep_default_na=False,na_values=['']) for n in names}


def fetch_frame(db,query):
    cur=db.cursor(); cur.execute(query)
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()],columns=[c[0] for c in cur.description])


def test_money_conversion_rejects_rounding_and_preserves_cents():
    col={'name':'price','type':'decimal(19,2)','nullable':False}
    assert convert_value('123.10',col)==Decimal('123.10')
    assert convert_value('0.00',col)==0
    with pytest.raises(ValueError,match='Lossy'): convert_value('0.001',col)
    with pytest.raises(ValueError,match='Non-finite'): convert_value('NaN',col)


def test_source_conversion_preserves_identifiers_and_optional_text():
    assert convert_value('00123',{'name':'zip','type':'varchar(5)','nullable':False})=='00123'
    col={'name':'review','type':'nvarchar(2000)','nullable':True}
    assert convert_value('NA\nÓtimo produto!',col)=='NA\nÓtimo produto!'
    assert convert_value('',col) is None
    with pytest.raises(ValueError): convert_value('',{'name':'order_id','type':'varchar(32)','nullable':False})
    with pytest.raises(ValueError): convert_value('maybe',{'name':'dq','type':'bit','nullable':False})


def test_checked_in_source_contracts_match_all_ten_files():
    assert len(CONTRACT)==10
    for spec in CONTRACT.values():
        path=ROOT/'data/processed'/spec['filename']
        with path.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==spec['sha256']
        with path.open(encoding='utf-8',newline='') as f:
            reader=csv.reader(f); assert next(reader)==[c['name'] for c in spec['columns']]
    assert CONTRACT['reviews']['key']==['review_id','order_id']


def test_sql_scripts_are_batched_and_no_float_money():
    for name in ['01_create_database','02_create_staging_tables','03_create_dimensions','04_create_fact_tables','05_create_indexes','06_kpi_validation','07_data_quality_checks','08_load_warehouse']:
        assert sql_batches(ROOT/'sql'/f'{name}.sql')
    assert all(c['type']=='decimal(19,2)' for s in CONTRACT.values() for c in s['columns'] if c['name'] in ['price','freight_value','payment_value'])


def test_schema_columns_types_and_constraints(db):
    frame=fetch_frame(db,"""SELECT s.name SchemaName,t.name TableName,c.name ColumnName,ty.name TypeName,c.precision,c.scale,c.is_nullable
        FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id
        JOIN sys.types ty ON ty.user_type_id=c.user_type_id WHERE s.name IN ('stg','dw','audit')""")
    assert frame[['SchemaName','TableName']].drop_duplicates().shape[0]==25
    for name,spec in CONTRACT.items():
        actual=frame.loc[(frame.SchemaName=='stg')&(frame.TableName==name)].set_index('ColumnName')
        assert set(actual.index)=={c['name'] for c in spec['columns']}|{'LoadID','SourceRow','LoadedAtUTC'}
        for col in spec['columns']:
            assert actual.loc[col['name'],'TypeName']==col['type'].split('(')[0]
            assert bool(actual.loc[col['name'],'is_nullable'])==col['nullable']
    money=frame.loc[frame.ColumnName.isin(['price','freight_value','payment_value','ItemPrice','FreightValue','PaymentAmount','MerchandiseRevenue','FreightAmount'])]
    assert money.TypeName.eq('decimal').all() and money.scale.eq(2).all()
    assert db.cursor().execute('SELECT COUNT(*) FROM sys.foreign_keys WHERE is_not_trusted=1 OR is_disabled=1').fetchval()==0


def test_staging_row_counts_and_load_lineage(db):
    cur=db.cursor()
    for name,spec in CONTRACT.items():
        row=cur.execute(f'SELECT COUNT_BIG(*),COUNT(DISTINCT LoadID),MIN(SourceRow),MAX(SourceRow) FROM stg.[{name}]').fetchone()
        assert tuple(row)==(spec['rows'],1,1,spec['rows'])
        assert cur.execute(f'SELECT COUNT(*) FROM stg.[{name}] s LEFT JOIN audit.LoadRun r ON r.LoadID=s.LoadID WHERE r.Status<>\'PASS\' OR r.LoadID IS NULL').fetchval()==0


def test_dimensions_unique_with_unknown_members(db,source):
    for table,key,business in [('DimCustomer','CustomerKey','CustomerID'),('DimProduct','ProductKey','ProductID'),('DimSeller','SellerKey','SellerID'),
                               ('DimGeography','GeographyKey','ZipCodePrefix'),('DimPaymentType','PaymentTypeKey','PaymentType'),('DimOrderStatus','OrderStatusKey','OrderStatus')]:
        row=db.cursor().execute(f'SELECT COUNT(*),COUNT(DISTINCT {business}),SUM(CASE WHEN {key}=0 THEN 1 ELSE 0 END) FROM dw.{table}').fetchone()
        assert row[0]==row[1] and row[2]==1
    for table,name in [('DimCustomer','customers'),('DimProduct','products'),('DimSeller','sellers')]:
        assert db.cursor().execute(f'SELECT COUNT(*) FROM dw.{table}').fetchval()==len(source[name])+1


def test_fact_grains_exactly_match_source_business_keys(db,source):
    for table,name,cols,target in [('FactOrders','orders',['order_id'],['OrderID']),('FactOrderItems','order_items',['order_id','order_item_id'],['OrderID','OrderItemID']),
                                  ('FactPayments','payments',['order_id','payment_sequential'],['OrderID','PaymentSequential']),('FactReviews','reviews',['review_id','order_id'],['ReviewID','OrderID'])]:
        frame=fetch_frame(db,f'SELECT '+','.join(target)+f' FROM dw.{table}')
        assert len(frame)==len(source[name]) and not frame.duplicated().any()
        assert set(frame.itertuples(index=False,name=None))==set(source[name][cols].itertuples(index=False,name=None))


def test_referential_integrity_all_declared_foreign_keys(db):
    cur=db.cursor(); cur.execute('DBCC CHECKCONSTRAINTS WITH ALL_CONSTRAINTS, NO_INFOMSGS')
    while True:
        if cur.description: assert not cur.fetchall()
        if not cur.nextset(): break
    assert db.cursor().execute('SELECT COUNT(*) FROM sys.foreign_keys').fetchval()==38


def test_money_preserved_per_source_row(db,source):
    items=fetch_frame(db,'SELECT OrderID,OrderItemID,ItemPrice,FreightValue FROM dw.FactOrderItems').set_index(['OrderID','OrderItemID'])
    expected=source['order_items'].set_index(['order_id','order_item_id'])
    items=items.reindex(expected.index)
    assert items.ItemPrice.eq(expected.price.map(Decimal)).all()
    assert items.FreightValue.eq(expected.freight_value.map(Decimal)).all()
    payments=fetch_frame(db,'SELECT OrderID,PaymentSequential,PaymentAmount,Installments FROM dw.FactPayments').set_index(['OrderID','PaymentSequential'])
    expected=source['payments'].set_index(['order_id','payment_sequential']); payments=payments.reindex(expected.index)
    assert payments.PaymentAmount.eq(expected.payment_value.map(Decimal)).all()
    assert payments.Installments.eq(expected.payment_installments.astype(int)).all()


def test_order_aggregates_and_no_fanout(db,source):
    out=fetch_frame(db,'SELECT OrderID,MerchandiseRevenue,FreightAmount,ItemCount,PaymentRecordCount,ReviewRecordCount FROM dw.FactOrders').set_index('OrderID')
    items=source['order_items'].copy(); items['price']=items.price.map(Decimal); items['freight_value']=items.freight_value.map(Decimal)
    expected=items.groupby('order_id').agg(revenue=('price','sum'),freight=('freight_value','sum'),n=('order_id','size'))
    assert out.reindex(expected.index).MerchandiseRevenue.eq(expected.revenue).all()
    assert out.reindex(expected.index).FreightAmount.eq(expected.freight).all()
    for src,col in [('order_items','ItemCount'),('payments','PaymentRecordCount'),('reviews','ReviewRecordCount')]:
        np.testing.assert_array_equal(out[col],source[src].groupby('order_id').size().reindex(out.index,fill_value=0))
    assert out.loc[out.ItemCount.eq(0),['MerchandiseRevenue','FreightAmount']].isna().all().all()


def test_delivery_eligibility_and_all_date_roles_independent_of_flags(db,source):
    src=source['orders'].set_index('order_id')
    out=fetch_frame(db,'SELECT * FROM dw.FactOrders').set_index('OrderID').reindex(src.index)
    roles={'Purchase':'order_purchase_timestamp','Approval':'order_approved_at','Carrier':'order_delivered_carrier_date','ActualDelivery':'order_delivered_customer_date','EstimatedDelivery':'order_estimated_delivery_date'}
    dates={role:pd.to_datetime(src[c],format='%Y-%m-%d %H:%M:%S') for role,c in roles.items()}
    for role,values in dates.items():
        actual=pd.to_datetime(out[role+'Timestamp'])
        assert (actual.eq(values)|(actual.isna()&values.isna())).all()
        np.testing.assert_array_equal(out[role+'DateKey'],values.dt.strftime('%Y%m%d').fillna('0').astype(int))
    delivered=src.order_status.eq('delivered')
    sla=delivered & dates['ActualDelivery'].notna() & dates['EstimatedDelivery'].notna()
    ontime=dates['ActualDelivery'].dt.normalize().le(dates['EstimatedDelivery'].dt.normalize())
    invalid=pd.Series(False,index=src.index)
    for first,second in [('Purchase','Approval'),('Purchase','Carrier'),('Purchase','ActualDelivery'),('Approval','Carrier'),('Carrier','ActualDelivery')]:
        invalid|=dates[first].notna()&dates[second].notna()&dates[second].lt(dates[first])
    duration=delivered & dates['Purchase'].notna() & dates['ActualDelivery'].ge(dates['Purchase']) & ~invalid
    np.testing.assert_array_equal(out.OnTimeEligible,sla)
    np.testing.assert_array_equal(out.loc[sla,'IsOnTime'].astype(bool),ontime.loc[sla])
    assert out.loc[~sla,'IsOnTime'].isna().all()
    np.testing.assert_array_equal(out.DurationEligible,duration)
    np.testing.assert_array_equal(out.InvalidChronology,invalid)
    expected=(dates['ActualDelivery']-dates['Purchase']).dt.total_seconds()/86400
    np.testing.assert_allclose(out.loc[duration,'DeliveryDurationDays'].astype(float),expected.loc[duration],atol=1e-9,rtol=0)
    assert out.loc[~duration,'DeliveryDurationDays'].isna().all()


def test_review_record_grain_scores_and_text_availability(db,source):
    src=source['reviews'].set_index(['review_id','order_id'])
    out=fetch_frame(db,'SELECT ReviewID,OrderID,ReviewScore,HasTitle,HasMessage FROM dw.FactReviews').set_index(['ReviewID','OrderID']).reindex(src.index)
    np.testing.assert_array_equal(out.ReviewScore,src.review_score.astype(int))
    np.testing.assert_array_equal(out.HasTitle,src.review_comment_title.notna())
    np.testing.assert_array_equal(out.HasMessage,src.review_comment_message.notna())
    assert len(out) - out.reset_index()["review_id"].nunique() == 814

def test_customer_identity_and_geography_source_fields(db,source):
    for table,name,prefix in [('DimCustomer','customers','customer'),('DimSeller','sellers','seller')]:
        src=source[name].set_index(prefix+'_id')
        out=fetch_frame(db,f'SELECT * FROM dw.{table} WHERE {prefix.title()}Key<>0').set_index(prefix.title()+'ID').reindex(src.index)
        for target,col in [('SourceState','state'),('SourceCity','city'),('SourceZipCodePrefix','zip_code_prefix')]:
            assert out[target].eq(src[prefix+'_'+col]).all()
        if name=='customers': assert out.CustomerUniqueID.eq(src.customer_unique_id).all()
    out=fetch_frame(db,'SELECT * FROM dw.DimGeography WHERE GeographyKey<>0')
    assert out.ZipCodePrefix.is_unique
    assert int(out.LookupMatched.sum())==19015
    assert int(out.ConflictingCities.sum())==8555 and int(out.ConflictingStates.sum())==8
    assert out.loc[~out.LookupMatched,['Latitude','Longitude','ApproximateState']].isna().all().all()


def test_calendar_complete_and_english_attributes(db,source):
    out=fetch_frame(db,'SELECT * FROM dw.DimDate WHERE DateKey<>0 ORDER BY FullDate')
    observed=[]
    for name,cols in [('orders',['order_purchase_timestamp','order_approved_at','order_delivered_carrier_date','order_delivered_customer_date','order_estimated_delivery_date']),('order_items',['shipping_limit_date']),('reviews',['review_creation_date','review_answer_timestamp'])]:
        for c in cols: observed.extend(pd.to_datetime(source[name][c]).dropna().dt.date)
    expected=pd.date_range(min(observed),max(observed))
    assert out.FullDate.tolist()==[d.date() for d in expected]
    assert out.DayOfWeek.tolist()==[d.day_of_week+1 for d in expected]
    assert out.DayName.tolist()==[d.day_name() for d in expected]
    assert out.IsWeekend.tolist()==[d.day_of_week>=5 for d in expected]


def test_sql_kpis_match_phase_3_and_user_acceptance_values(db):
    cur=db.cursor()
    for batch in sql_batches(ROOT/'sql/06_kpi_validation.sql'): cur.execute(batch)
    actual={r[0]:r[1] for r in cur.fetchall()}
    expected={'Merchandise Revenue':'13221498.11','Eligible Orders':'96478','Unique Customers':'93358','Items Sold':'110197',
              'Freight Total':'2198275.64','On-Time Eligible Orders':'96470','On-Time Orders':'89936','Late Orders':'6534',
              'Duration-Eligible Orders':'95097','Valid Review Records':'96361','Repeat Customers':'2801'}
    for metric,value in expected.items(): assert actual[metric]==Decimal(value),metric
    for metric,value in {'AOV':'137.041586','Average Freight / Order':'22.785253','Average Duration':'12.618486','Average Review Score':'4.155717'}.items():
        assert abs(actual[metric]-Decimal(value))<=Decimal('0.000001'),metric
    for m in ['Revenue - order totals','Revenue - monthly totals','Revenue - categories','Revenue - customer states']:
        assert actual[m]==actual['Merchandise Revenue']
    report=pd.read_csv(ROOT/'reports/phase_4_kpi_reconciliation.csv',dtype='string')
    assert len(report)==25 and report.status.eq('PASS').all()
    for r in report.itertuples(): assert Decimal(r.actual)==actual[r.check]


def test_each_month_category_and_source_state_reconciles(db,source):
    orders=source['orders'].set_index('order_id')
    items=source['order_items'].copy()
    items=items.loc[items.order_id.isin(orders.loc[orders.order_status.eq('delivered')].index)].copy()
    items['amount']=items.price.map(Decimal)
    items['month']=items.order_id.map(orders.order_purchase_timestamp.str.slice(0,7))
    customers=source['customers'].set_index('customer_id')
    items['state']=items.order_id.map(orders.customer_id).map(customers.customer_state)
    products=source['products'].set_index('product_id')
    label=products.product_category_name_english.copy()
    label.loc[products.dq_category_missing.eq('True')]='Unknown (missing category)'
    untranslated=products.dq_category_untranslated.eq('True')
    label.loc[untranslated]='Untranslated: '+products.loc[untranslated,'product_category_name']
    items['category']=items.product_id.map(label)
    for name,expr,join in [
        ('month','d.YearMonth','JOIN dw.DimDate d ON d.DateKey=i.PurchaseDateKey'),
        ('category','d.CategoryLabel','JOIN dw.DimProduct d ON d.ProductKey=i.ProductKey'),
        ('state','d.SourceState','JOIN dw.DimCustomer d ON d.CustomerKey=i.CustomerKey')]:
        frame=fetch_frame(db,f'SELECT {expr} GroupName,SUM(i.ItemPrice) Revenue FROM dw.FactOrderItems i {join} WHERE i.SalesEligible=1 GROUP BY {expr}').set_index('GroupName')
        expected=items.groupby(name).amount.sum()
        assert set(frame.index)==set(expected.index)
        assert frame.reindex(expected.index).Revenue.eq(expected).all(),name


def test_rerun_and_failure_rollback_evidence_from_database(db):
    evidence=json.loads((ROOT/'reports/phase_4_execution_evidence.json').read_text(encoding='utf-8'))
    assert len(evidence['successful_load_ids'])==2
    for load_id in evidence['successful_load_ids']:
        assert db.cursor().execute('SELECT Status FROM audit.LoadRun WHERE LoadID=?',load_id).fetchval()=='PASS'
        assert db.cursor().execute('SELECT COUNT(*) FROM audit.LoadFile WHERE LoadID=? AND SourceRows=StagedRows',load_id).fetchval()==10
    assert db.cursor().execute("SELECT COUNT(*) FROM audit.LoadRun WHERE Status='FAIL' AND ErrorMessage LIKE 'Intentional rollback verification%'").fetchval()>=1
    report=pd.read_csv(ROOT/'reports/phase_4_etl_validation.csv').set_index('check')
    for name in ['Idempotent rerun including all surrogate keys','Failed ETL restores previous complete snapshot','Unknown product fallback preserves source record','Unknown-member simulation rolled back completely']:
        assert report.loc[name,'status']=='PASS'


def test_original_csvs_and_previous_phase_outputs_unchanged():
    hashes=json.loads((ROOT/'reports/phase_4_protected_files.json').read_text(encoding='utf-8'))
    assert sum(name.startswith(('data/raw/','data/processed/')) and name.endswith('.csv') for name in hashes)==19
    for name,value in hashes.items():
        with (ROOT/name).open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==value,name


def test_review_grain_assertion_after_source_index_alignment_offline(source, monkeypatch):
    """Exercise the live assertion with source-derived rows, including index names."""
    reviews=source['reviews']
    assert len(reviews)-reviews.review_id.nunique()==814
    assert not reviews.duplicated(['review_id','order_id']).any()
    frame=pd.DataFrame({
        'ReviewID':reviews.review_id,
        'OrderID':reviews.order_id,
        'ReviewScore':reviews.review_score.astype(int),
        'HasTitle':reviews.review_comment_title.notna(),
        'HasMessage':reviews.review_comment_message.notna(),
    })
    monkeypatch.setattr(__import__(__name__,fromlist=['fetch_frame']),
                        'fetch_frame',lambda db,query:frame.copy())
    test_review_record_grain_scores_and_text_availability(None,source)
