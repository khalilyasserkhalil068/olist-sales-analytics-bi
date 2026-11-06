"""Read-only SQL evidence plus independent future DAX acceptance definitions.

Does not execute DAX, refresh Power BI, run ETL, or write to SQL Server.
"""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import os, sys, json

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.data_processing.sql_server_etl import connect
os.environ.setdefault('OLIST_SQL_SERVER',r'lpc:localhost\SQLEXPRESS')
OUT=ROOT/'reports/completion_20261101'
sql={
'sales':'''SELECT COUNT(*) SalesOrders,SUM(MerchandiseRevenue) Revenue,SUM(FreightAmount) Freight FROM dw.FactOrders WHERE SalesEligible=1''',
'category_sales':'''SELECT p.CategoryLabel,SUM(i.ItemPrice) Revenue,COUNT(*) ItemRows,COUNT(DISTINCT i.OrderKey) Orders FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey WHERE i.SalesEligible=1 GROUP BY p.CategoryLabel ORDER BY Revenue DESC,p.CategoryLabel''',
'seller_sales':'''SELECT i.SellerKey,SUM(i.ItemPrice) Revenue,COUNT(*) ItemRows,COUNT(DISTINCT i.OrderKey) Orders FROM dw.FactOrderItems i WHERE i.SalesEligible=1 GROUP BY i.SellerKey ORDER BY Revenue DESC,i.SellerKey''',
'approximate_state_sales':'''SELECT g.ApproximateState,SUM(o.MerchandiseRevenue) Revenue,COUNT(*) Orders FROM dw.FactOrders o JOIN dw.DimCustomer c ON c.CustomerKey=o.CustomerKey JOIN dw.DimGeography g ON g.GeographyKey=c.GeographyKey WHERE o.SalesEligible=1 GROUP BY g.ApproximateState ORDER BY Revenue DESC,g.ApproximateState''',
'monthly_sales':'''SELECT CONVERT(char(7),PurchaseTimestamp,126) Month,SUM(MerchandiseRevenue) Revenue,COUNT(*) Orders FROM dw.FactOrders WHERE SalesEligible=1 GROUP BY CONVERT(char(7),PurchaseTimestamp,126) ORDER BY Month''',
'approximate_state_delivery':'''SELECT g.ApproximateState,COUNT(*) DeliveredOrders,SUM(CONVERT(int,o.OnTimeEligible)) Eligible,SUM(CASE WHEN o.IsOnTime=1 THEN 1 ELSE 0 END) OnTimeOrders,SUM(CASE WHEN o.IsOnTime=0 THEN 1 ELSE 0 END) LateOrders,AVG(o.DeliveryDurationDays) AverageDays FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey JOIN dw.DimCustomer c ON c.CustomerKey=o.CustomerKey JOIN dw.DimGeography g ON g.GeographyKey=c.GeographyKey WHERE s.OrderStatus='delivered' GROUP BY g.ApproximateState''',
'category_reviews':'''WITH membership AS (SELECT DISTINCT i.OrderKey,p.CategoryLabel FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey) SELECT m.CategoryLabel,COUNT(*) ValidReviews,AVG(CONVERT(decimal(20,10),r.ReviewScore)) AverageScore FROM membership m JOIN dw.FactReviews r ON r.OrderKey=m.OrderKey WHERE r.ValidScore=1 GROUP BY m.CategoryLabel ORDER BY ValidReviews DESC,m.CategoryLabel''',
'category_delivery':'''WITH membership AS (SELECT DISTINCT i.OrderKey,p.CategoryLabel FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey) SELECT m.CategoryLabel,COUNT(*) Eligible,SUM(CASE WHEN o.IsOnTime=1 THEN 1 ELSE 0 END) OnTimeOrders FROM membership m JOIN dw.FactOrders o ON o.OrderKey=m.OrderKey WHERE o.OnTimeEligible=1 GROUP BY m.CategoryLabel ORDER BY Eligible DESC,m.CategoryLabel''',
'duration_bands':'''SELECT CASE WHEN DeliveryDurationDays<7 THEN '01 | Under 7 days' WHEN DeliveryDurationDays<14 THEN '02 | 7 to <14 days' WHEN DeliveryDurationDays<21 THEN '03 | 14 to <21 days' WHEN DeliveryDurationDays<30 THEN '04 | 21 to <30 days' ELSE '05 | 30+ days' END Band,COUNT(*) Orders FROM dw.FactOrders WHERE DurationEligible=1 GROUP BY CASE WHEN DeliveryDurationDays<7 THEN '01 | Under 7 days' WHEN DeliveryDurationDays<14 THEN '02 | 7 to <14 days' WHEN DeliveryDurationDays<21 THEN '03 | 14 to <21 days' WHEN DeliveryDurationDays<30 THEN '04 | 21 to <30 days' ELSE '05 | 30+ days' END''',
}
cn=connect()
queries={}
try:
    for name,q in sql.items():
        cur=cn.cursor();cur.execute(q);cols=[c[0] for c in cur.description]
        queries[name]=[dict(zip(cols,list(r))) for r in cur.fetchall()]
finally:
    cn.rollback();cn.close()

total=queries['sales'][0]['Revenue']
assert queries['sales'][0]['SalesOrders']==96478
assert total==Decimal('13221498.11')
for key in ['category_sales','seller_sales','approximate_state_sales','monthly_sales']:
    assert sum(r['Revenue'] for r in queries[key])==total,key
assert sum(r['Orders'] for r in queries['duration_bands'])==95097
assert sum(r['Eligible'] for r in queries['approximate_state_delivery'])==96470
assert sum(r['OnTimeOrders'] for r in queries['approximate_state_delivery'])==89936

qa=json.loads((OUT/'qa/warehouse_reconciliation.json').read_text())['queries']
cases=[]
def case(name,pairs,filters=None,tolerance=0.000001):
    # pairs: (expression, expected); use opaque c0.. labels to avoid field-name serialization ambiguity.
    expressions={f'c{i}':e for i,(e,v) in enumerate(pairs)}
    expected={f'c{i}':float(v) if isinstance(v,Decimal) else v for i,(e,v) in enumerate(pairs)}
    q='ROW('+', '.join('"'+k+'", '+e for k,e in expressions.items())+')'
    if filters:q='CALCULATETABLE('+q+', '+', '.join(filters)+')'
    cases.append(dict(name=name,dax='EVALUATE '+q,expected=expected,tolerance=tolerance,expressions=expressions))
case('Original KPI regression',[( '[Order Count]',99441),('[Sales Revenue]',13221498.11),('[Average Sales Order Value]',13221498.11/96478),('[Unique Sales Customers]',93358),('[Repeat Sales Customers]',2801),('[Repeat Customer Rate]',2801/93358),('[Item Revenue]',13591643.70),('[Average Review Score]',4.08642062404257)],tolerance=0.005)
d=qa['delivery'][0];r=qa['reviews'][0]
case('Delivery totals',[('[Delivered Orders]',d['DeliveredOrders']),('[Timeliness Eligible Orders]',d['OnTimeEligible']),('[On Time Deliveries]',d['OnTimeOrders']),('[Late Deliveries]',d['LateOrders']),('[On Time Delivery Rate]',d['OnTimeOrders']/d['OnTimeEligible']),('[Late Delivery Rate]',d['LateOrders']/d['OnTimeEligible']),('[Duration Eligible Orders]',d['DurationEligible']),('[Average Delivery Days]',float(d['AverageDurationDays'])),('[Average Late Delay Days]',float(d['AverageLateDelayDays'])),('[Average Freight per Delivered Order]',float(d['AverageFreightPerSalesOrder']))],tolerance=0.00001)
case('All valid review totals',[('[Total Valid Reviews]',r['ValidReviews']),('[Satisfaction Average Review Score]',float(r['AverageScore'])),('[Positive Review Rate]',r['PositiveReviews']/r['ValidReviews']),('[Negative Review Rate]',r['NegativeReviews']/r['ValidReviews']),('[Five Star Review Rate]',r['FiveStarReviews']/r['ValidReviews'])])
for row in qa['review_timeliness']:
    label='On time' if row['Timeliness']=='On Time' else ('Late' if row['Timeliness']=='Late' else 'Not eligible')
    case('Review timeliness: '+label,[('[Total Valid Reviews]',row['ValidReviews']),('[Satisfaction Average Review Score]',float(row['AverageScore']))],['TREATAS({"'+label+'"}, FactOrders[Delivery Timeliness])'])
for row in qa['review_scores']:
    score=row['ReviewScore']
    case('Review score slicer '+str(score),[('[Total Valid Reviews]',row['Reviews']),('[Positive Review Rate]',int(score>=4)),('[Negative Review Rate]',int(score<=2)),('[Five Star Review Rate]',int(score==5))],[f'TREATAS({{{score}}}, FactReviews[ReviewScore])'])
for row in queries['duration_bands']:
    case('Duration band '+row['Band'],[('[Duration Eligible Orders]',row['Orders'])],['TREATAS({"'+row['Band']+'"}, FactOrders[Delivery Duration Band])'])
for row in queries['approximate_state_delivery']:
    if row['ApproximateState'] is None:continue
    pairs=[('[Delivered Orders]',row['DeliveredOrders']),('[Timeliness Eligible Orders]',row['Eligible']),('[On Time Deliveries]',row['OnTimeOrders']),('[Late Deliveries]',row['LateOrders'])]
    # BLANK counts are equivalent to zero only for count checks, recorded explicitly by runner.
    case('Approximate state '+row['ApproximateState'],pairs,['TREATAS({"'+row['ApproximateState']+'"}, DimCustomerGeography[ApproximateState])'])
for row in queries['category_reviews'][:10]:
    val=row['CategoryLabel'].replace('"','""')
    case('Review category semijoin '+row['CategoryLabel'],[('[Category Valid Reviews]',row['ValidReviews']),('[Category Average Review Score]',float(row['AverageScore']))],['TREATAS({"'+val+'"}, DimProduct[CategoryLabel])'])
for row in queries['category_delivery'][:10]:
    val=row['CategoryLabel'].replace('"','""')
    case('Delivery category semijoin '+row['CategoryLabel'],[('[Category Eligible Deliveries]',row['Eligible']),('[Category On Time Delivery Rate]',row['OnTimeOrders']/row['Eligible'])],['TREATAS({"'+val+'"}, DimProduct[CategoryLabel])'])
for row in queries['monthly_sales']:
    case('Purchase month regression '+row['Month'],[('[Sales Revenue]',row['Revenue']),('[Sales Order Count]',row['Orders'])],['TREATAS({"'+row['Month']+'"}, DimDate[YearMonth])'],tolerance=0.005)
result=dict(executed_utc=datetime.now(timezone.utc).isoformat(),database_mutations=False,queries=queries,query_sql=sql,additive_invariants_passed=9,scope='SQL execution plus internal additive checks. Future runtime cases are PREPARED, not executed DAX.')
(OUT/'business_sql_evidence.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
(OUT/'runtime_cases.json').write_text(json.dumps(dict(status='PREPARED; NOT EXECUTED',caseCount=len(cases),cases=cases),indent=2),encoding='utf-8')
print(json.dumps(dict(sqlQueries=len(sql),additiveChecks=9,runtimeCasesPrepared=len(cases))))
