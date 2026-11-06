"""Read-only SQL/Python reconciliation. Never invokes ETL or commits database changes."""
from pathlib import Path
import os, sys, json, hashlib
from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_processing.sql_server_etl import connect, sql_batches

OUT = ROOT / 'reports/completion_20261101/qa'
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('OLIST_SQL_SERVER', r'lpc:localhost\SQLEXPRESS')
def read(name):
    return pd.read_csv(ROOT/'data/processed'/f'{name}_clean.csv', dtype='string', keep_default_na=False, na_values=[''])

orders, reviews, customers, items = [read(n) for n in ['orders','reviews','customers','order_items']]
datecols = ['order_purchase_timestamp','order_approved_at','order_delivered_carrier_date','order_delivered_customer_date','order_estimated_delivery_date']
for c in datecols: orders[c] = pd.to_datetime(orders[c], format='%Y-%m-%d %H:%M:%S')
p,a,c,d,e = [orders[x] for x in datecols]
delivered = orders.order_status.eq('delivered')
sla = delivered & d.notna() & e.notna()
on = sla & d.dt.normalize().le(e.dt.normalize())
late = sla & ~on
bad = pd.Series(False,index=orders.index)
for x,y in [(p,a),(p,c),(p,d),(a,c),(c,d)]: bad |= x.notna() & y.notna() & y.lt(x)
duration = delivered & p.notna() & d.ge(p) & ~bad
orders['state'] = orders.customer_id.map(customers.set_index('customer_id').customer_state)
orders['month'] = p.dt.strftime('%Y-%m')
orders['sla'] = sla
orders['ontime'] = on
orders['late'] = late
orders['duration_days'] = ((d-p).dt.total_seconds()/86400).where(duration)
orders['delay_days'] = ((d.dt.normalize()-e.dt.normalize()).dt.days).where(late)
orders['freight'] = orders.order_id.map(items.assign(money=items.freight_value.map(Decimal)).groupby('order_id').money.sum())
orders['sales'] = delivered & orders.order_id.isin(items.order_id)
reviews['score'] = pd.to_numeric(reviews.review_score)
reviews = reviews.loc[reviews.score.between(1,5)].copy()
reviews['month'] = pd.to_datetime(reviews.review_creation_date).dt.strftime('%Y-%m')
order_index = orders.set_index('order_id')
reviews['state'] = reviews.order_id.map(order_index.state)
reviews['timeliness'] = reviews.order_id.map(pd.Series(np.select([on,late],['On Time','Late'],default='Not Eligible'),index=orders.index).set_axis(orders.order_id))

sql = {
'warehouse_counts': "SELECT s.name SchemaName,t.name TableName,SUM(p.rows) [RowCount] FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) WHERE s.name IN ('dw','stg') GROUP BY s.name,t.name ORDER BY s.name,t.name",
'load_history': 'SELECT LoadID,Status FROM audit.LoadRun ORDER BY LoadID',
'foreign_keys': 'SELECT COUNT(*) DeclaredForeignKeys,SUM(CONVERT(int,is_not_trusted)) Untrusted,SUM(CONVERT(int,is_disabled)) Disabled FROM sys.foreign_keys',
'delivery': "SELECT COUNT(*) DeliveredOrders,SUM(CONVERT(int,OnTimeEligible)) OnTimeEligible,SUM(CASE WHEN IsOnTime=1 THEN 1 ELSE 0 END) OnTimeOrders,SUM(CASE WHEN IsOnTime=0 THEN 1 ELSE 0 END) LateOrders,SUM(CONVERT(int,DurationEligible)) DurationEligible,AVG(DeliveryDurationDays) AverageDurationDays,AVG(CASE WHEN IsOnTime=0 THEN CONVERT(decimal(20,10),DATEDIFF(day,EstimatedDeliveryTimestamp,ActualDeliveryTimestamp)) END) AverageLateDelayDays,AVG(CASE WHEN SalesEligible=1 AND ItemCount>0 THEN FreightAmount END) AverageFreightPerSalesOrder FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey WHERE s.OrderStatus='delivered'",
'reviews': 'SELECT COUNT(*) ValidReviews,AVG(CONVERT(decimal(20,10),ReviewScore)) AverageScore,SUM(CASE WHEN ReviewScore>=4 THEN 1 ELSE 0 END) PositiveReviews,SUM(CASE WHEN ReviewScore<=2 THEN 1 ELSE 0 END) NegativeReviews,SUM(CASE WHEN ReviewScore=5 THEN 1 ELSE 0 END) FiveStarReviews,COUNT(DISTINCT OrderID) ReviewedOrders FROM dw.FactReviews WHERE ReviewScore BETWEEN 1 AND 5',
'review_timeliness': "SELECT CASE WHEN o.IsOnTime=1 THEN 'On Time' WHEN o.IsOnTime=0 THEN 'Late' ELSE 'Not Eligible' END Timeliness,COUNT(*) ValidReviews,AVG(CONVERT(decimal(20,10),r.ReviewScore)) AverageScore FROM dw.FactReviews r JOIN dw.FactOrders o ON o.OrderKey=r.OrderKey WHERE r.ReviewScore BETWEEN 1 AND 5 GROUP BY CASE WHEN o.IsOnTime=1 THEN 'On Time' WHEN o.IsOnTime=0 THEN 'Late' ELSE 'Not Eligible' END",
'delivery_by_month_state': "SELECT LEFT(CONVERT(varchar(10),o.PurchaseTimestamp,23),7) Month,c.SourceState State,COUNT(*) DeliveredOrders,SUM(CONVERT(int,o.OnTimeEligible)) OnTimeEligible,SUM(CASE WHEN o.IsOnTime=1 THEN 1 ELSE 0 END) OnTimeOrders,SUM(CASE WHEN o.IsOnTime=0 THEN 1 ELSE 0 END) LateOrders,AVG(o.DeliveryDurationDays) AverageDurationDays FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey JOIN dw.DimCustomer c ON c.CustomerKey=o.CustomerKey WHERE s.OrderStatus='delivered' GROUP BY LEFT(CONVERT(varchar(10),o.PurchaseTimestamp,23),7),c.SourceState",
'reviews_by_month_state': "SELECT LEFT(CONVERT(varchar(10),r.ReviewCreationTimestamp,23),7) Month,c.SourceState State,COUNT(*) ValidReviews,AVG(CONVERT(decimal(20,10),r.ReviewScore)) AverageScore FROM dw.FactReviews r JOIN dw.DimCustomer c ON c.CustomerKey=r.CustomerKey WHERE r.ReviewScore BETWEEN 1 AND 5 GROUP BY LEFT(CONVERT(varchar(10),r.ReviewCreationTimestamp,23),7),c.SourceState",
'review_scores': 'SELECT ReviewScore,COUNT(*) Reviews FROM dw.FactReviews WHERE ReviewScore BETWEEN 1 AND 5 GROUP BY ReviewScore ORDER BY ReviewScore',
}
cn=connect()
result={'executed_utc':datetime.now(timezone.utc).isoformat(),'database_mutations':False,'queries':{},'checks':[]}
def query(q):
    cur=cn.cursor(); cur.execute(q)
    while not cur.description:
        if not cur.nextset(): return []
    cols=[c[0] for c in cur.description]
    return [dict(zip(cols,list(r))) for r in cur.fetchall()]
try:
    result['database']=query('SELECT DB_NAME() DatabaseName,CONVERT(varchar(128),SERVERPROPERTY(\'ServerName\')) ServerName')
    for name,q in sql.items(): result['queries'][name]=query(q)
    for name in ['06_kpi_validation','07_data_quality_checks']:
        result['queries'][name]=query((ROOT/'sql'/f'{name}.sql').read_text())
finally:
    cn.rollback();cn.close()
def check(name,actual,expected,tol=0):
    if pd.isna(expected): ok=actual is None
    else: ok=actual is not None and abs(float(actual)-float(expected))<=tol
    result['checks'].append(dict(name=name,status='PASS' if ok else 'FAIL',sql=actual,python=expected,tolerance=tol))
row=result['queries']['delivery'][0]
expected={'DeliveredOrders':delivered.sum(),'OnTimeEligible':sla.sum(),'OnTimeOrders':on.sum(),'LateOrders':late.sum(),'DurationEligible':duration.sum(),'AverageDurationDays':orders.duration_days.mean(),'AverageLateDelayDays':orders.delay_days.mean(),'AverageFreightPerSalesOrder':orders.loc[orders.sales,'freight'].mean()}
for k,v in expected.items(): check(k,row[k],v,1e-6 if k.startswith('Average') else 0)
r=result['queries']['reviews'][0]
expected={'ValidReviews':len(reviews),'AverageScore':reviews.score.mean(),'PositiveReviews':reviews.score.ge(4).sum(),'NegativeReviews':reviews.score.le(2).sum(),'FiveStarReviews':reviews.score.eq(5).sum(),'ReviewedOrders':reviews.order_id.nunique()}
for k,v in expected.items(): check(k,r[k],v,1e-9 if k=='AverageScore' else 0)
for r in result['queries']['review_timeliness']:
    g=reviews.loc[reviews.timeliness.eq(r['Timeliness'])]
    check('Review timeliness '+r['Timeliness']+' volume',r['ValidReviews'],len(g))
    check('Review timeliness '+r['Timeliness']+' score',r['AverageScore'],g.score.mean(),1e-9)
for r in result['queries']['delivery_by_month_state']:
    g=orders.loc[delivered & orders.month.eq(r['Month']) & orders.state.eq(r['State'])]
    for k,v in {'DeliveredOrders':len(g),'OnTimeEligible':g.sla.sum(),'OnTimeOrders':g.ontime.sum(),'LateOrders':g.late.sum(),'AverageDurationDays':g.duration_days.mean()}.items():check('Delivery '+r['Month']+'/'+r['State']+' '+k,r[k],v,1e-9 if k.startswith('Average') else 0)
for r in result['queries']['reviews_by_month_state']:
    g=reviews.loc[reviews.month.eq(r['Month']) & reviews.state.eq(r['State'])]
    check('Reviews '+r['Month']+'/'+r['State']+' volume',r['ValidReviews'],len(g))
    check('Reviews '+r['Month']+'/'+r['State']+' score',r['AverageScore'],g.score.mean(),1e-9)
result['summary']={s:sum(c['status']==s for c in result['checks']) for s in ['PASS','FAIL']}
result['query_sql']=sql
def encode(x):
    if isinstance(x,Decimal):return str(x)
    if isinstance(x,np.generic):return x.item()
    return str(x)
(OUT/'warehouse_reconciliation.json').write_text(json.dumps(result,indent=2,default=encode),encoding='utf-8')
print(json.dumps({k:result['queries'][k] for k in ['delivery','reviews','review_timeliness']},indent=2,default=encode))
print(result['summary'])
assert not result['summary']['FAIL']
