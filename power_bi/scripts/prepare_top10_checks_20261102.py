"""Prepare volume-ranked SQL expectations for the four new visual gates."""
from pathlib import Path
import sys,os,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.data_processing.sql_server_etl import connect
os.environ.setdefault('OLIST_SQL_SERVER',r'lpc:localhost\SQLEXPRESS')
out=ROOT/'reports/completion_20261101'
business=json.loads((out/'business_sql_evidence.json').read_text())['queries']
cn=connect()
try:
 cur=cn.cursor();cur.execute('SELECT g.ApproximateState,COUNT(*) Volume FROM dw.FactReviews r JOIN dw.DimCustomer c ON c.CustomerKey=r.CustomerKey JOIN dw.DimGeography g ON g.GeographyKey=c.GeographyKey WHERE r.ValidScore=1 AND g.ApproximateState IS NOT NULL GROUP BY g.ApproximateState ORDER BY Volume DESC,g.ApproximateState')
 state_reviews=[dict(zip(['ApproximateState','Volume'],list(row))) for row in cur.fetchall()]
finally:cn.rollback();cn.close()
state_delivery=sorted([r for r in business['approximate_state_delivery'] if r['ApproximateState'] is not None],key=lambda r:(-r['DeliveredOrders'],r['ApproximateState']))
cases=[]
for name,field,metric,gate,expected,label,volume in [
 ('Delivery states','DimCustomerGeography[ApproximateState]','Delivered Orders','Show Delivery Top 10 States',state_delivery,'ApproximateState','DeliveredOrders'),
 ('Delivery categories','DimProduct[CategoryLabel]','Category Eligible Deliveries','Show Delivery Top 10 Categories',business['category_delivery'],'CategoryLabel','Eligible'),
 ('Review states','DimCustomerGeography[ApproximateState]','Total Valid Reviews','Show Review Top 10 States',state_reviews,'ApproximateState','Volume'),
 ('Review categories','DimProduct[CategoryLabel]','Category Valid Reviews','Show Review Top 10 Categories',business['category_reviews'],'CategoryLabel','ValidReviews')]:
 cases.append(dict(name=name,field=field,expected=[dict(label=r[label],volume=r[volume]) for r in expected[:10]],dax=f'EVALUATE FILTER(SUMMARIZECOLUMNS({field}, "Volume", [{metric}], "Gate", [{gate}]), [Gate] = 1) ORDER BY [Volume] DESC, {field} ASC'))
(out/'top10_cases.json').write_text(json.dumps(dict(status='PREPARED',cases=cases),indent=2),encoding='utf-8')
print('Prepared four SQL-backed Top-10 gate cases.')
