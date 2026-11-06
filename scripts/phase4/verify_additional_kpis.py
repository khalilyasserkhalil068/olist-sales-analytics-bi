"""Read-only SQL Server checks for the remaining Phase 3 acceptance findings."""
import csv
from decimal import Decimal
import json
from pathlib import Path
import sys

def verify(project):
    sys.path.insert(0,str(project))
    from src.data_processing.sql_server_etl import connect
    checks=[]
    def rows(name):
        with (project/'reports'/name).open(encoding='utf-8-sig',newline='') as f:
            return list(csv.DictReader(f))
    delivery=next(r for r in rows('delivery_performance_summary.csv') if r['customer_state']=='ALL')
    categories=rows('category_performance.csv')
    eligible="FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey WHERE s.OrderStatus='delivered' AND EXISTS(SELECT 1 FROM dw.FactOrderItems i WHERE i.OrderKey=o.OrderKey)"
    with connect() as cn:
        def check(name,query,expected,tol='0'):
            actual=cn.cursor().execute(query).fetchval()
            passed=actual is not None and abs(Decimal(str(actual))-Decimal(str(expected)))<=Decimal(tol)
            checks.append(dict(check=name,status='PASS' if passed else 'FAIL',actual=str(actual),expected=str(expected),tolerance=tol))
        check('Review score sum',"SELECT SUM(CONVERT(bigint,r.ReviewScore)) FROM dw.FactReviews r JOIN dw.FactOrders o ON o.OrderKey=r.OrderKey WHERE o.SalesEligible=1 AND r.ReviewScore BETWEEN 1 AND 5",400449)
        check('Reviewed eligible orders',"SELECT COUNT(DISTINCT r.OrderKey) FROM dw.FactReviews r JOIN dw.FactOrders o ON o.OrderKey=r.OrderKey WHERE o.SalesEligible=1 AND r.ReviewScore BETWEEN 1 AND 5",95832)
        check('Eligible payment discrepancies',"SELECT COUNT(*) FROM dw.FactOrders o JOIN (SELECT OrderKey,SUM(PaymentAmount) amount FROM dw.FactPayments GROUP BY OrderKey) p ON p.OrderKey=o.OrderKey WHERE o.SalesEligible=1 AND p.amount<>o.MerchandiseRevenue+o.FreightAmount",569)
        for scope in rows('payment_analysis_summary.csv'):
            if scope['analysis_type']!='scope_summary':continue
            condition=' WHERE p.SalesEligible=1' if scope['group']=='eligible sales payments' else ''
            for label,expr,field in [('records','COUNT_BIG(*)','payment_transactions'),('orders','COUNT(DISTINCT p.OrderKey)','distinct_orders'),('amount','SUM(p.PaymentAmount)*100','recorded_payment_cents')]:
                check(scope['group']+' '+label,'SELECT '+expr+' FROM dw.FactPayments p'+condition,scope[field])
        check('SP revenue cents',"SELECT SUM(i.ItemPrice)*100 FROM dw.FactOrderItems i JOIN dw.DimCustomer c ON c.CustomerKey=i.CustomerKey WHERE i.SalesEligible=1 AND c.SourceState='SP'",506763316)
        check('November 2017 cents',"SELECT SUM(i.ItemPrice)*100 FROM dw.FactOrderItems i JOIN dw.DimDate d ON d.DateKey=i.PurchaseDateKey WHERE i.SalesEligible=1 AND d.YearMonth='2017-11'",98776537)
        check('Comparable-window peak month',"SELECT COUNT(*) FROM (SELECT TOP(1) d.YearMonth FROM dw.FactOrderItems i JOIN dw.DimDate d ON d.DateKey=i.PurchaseDateKey WHERE i.SalesEligible=1 AND d.YearMonth BETWEEN '2017-01' AND '2018-07' GROUP BY d.YearMonth ORDER BY SUM(i.ItemPrice) DESC,d.YearMonth) x WHERE YearMonth='2017-11'",1)
        top10=sum(sorted((int(r['merchandise_revenue_cents']) for r in categories),reverse=True)[:10])
        check('Top ten category revenue cents',"SELECT SUM(revenue)*100 FROM (SELECT TOP(10) SUM(i.ItemPrice) revenue FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey WHERE i.SalesEligible=1 GROUP BY p.CategoryLabel ORDER BY SUM(i.ItemPrice) DESC) x",top10)
        check('health_beauty cents',"SELECT SUM(i.ItemPrice)*100 FROM dw.FactOrderItems i JOIN dw.DimProduct p ON p.ProductKey=i.ProductKey WHERE i.SalesEligible=1 AND p.CategoryLabel='health_beauty'",123313172)
        review_cte="""WITH r AS (SELECT OrderKey,AVG(CONVERT(decimal(20,10),ReviewScore)) score FROM dw.FactReviews WHERE ReviewScore BETWEEN 1 AND 5 GROUP BY OrderKey)
            SELECT {expr} FROM dw.FactOrders o JOIN dw.DimOrderStatus s ON s.OrderStatusKey=o.OrderStatusKey JOIN r ON r.OrderKey=o.OrderKey
            WHERE s.OrderStatus='delivered' AND o.ActualDeliveryTimestamp IS NOT NULL AND o.EstimatedDeliveryTimestamp IS NOT NULL
            AND CAST(o.ActualDeliveryTimestamp AS date){op}CAST(o.EstimatedDeliveryTimestamp AS date)"""
        for label,op in [('on_time','<='),('late','>')]:
            check(label+' reviewed order count',review_cte.format(expr='COUNT_BIG(*)',op=op),delivery[label+'_reviewed_orders'])
            check(label+' order-weighted review score',review_cte.format(expr='AVG(r.score)',op=op),delivery[label+'_average_order_review_score'],'0.000001')
        # Check SQL storage types as well as every row's exact financial equality.
        check('All warehouse money columns are DECIMAL(19,2)',"""SELECT COUNT(*) FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
          WHERE c.object_id IN (OBJECT_ID('dw.FactOrders'),OBJECT_ID('dw.FactOrderItems'),OBJECT_ID('dw.FactPayments'))
          AND c.name IN ('MerchandiseRevenue','FreightAmount','ItemPrice','FreightValue','PaymentAmount')
          AND ty.name='decimal' AND c.precision=19 AND c.scale=2""",5)
        check('Item money per-key mismatches',"SELECT COUNT(*) FROM stg.order_items s FULL JOIN dw.FactOrderItems f ON f.OrderID=s.order_id AND f.OrderItemID=s.order_item_id WHERE s.order_id IS NULL OR f.OrderID IS NULL OR s.price<>f.ItemPrice OR s.freight_value<>f.FreightValue",0)
        check('Payment money per-key mismatches',"SELECT COUNT(*) FROM stg.payments s FULL JOIN dw.FactPayments f ON f.OrderID=s.order_id AND f.PaymentSequential=s.payment_sequential WHERE s.order_id IS NULL OR f.OrderID IS NULL OR s.payment_value<>f.PaymentAmount",0)
    return checks

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.project);a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f"Additional SQL checks: {sum(r['status']=='PASS' for r in result)}/{len(result)} passed")
    raise SystemExit(0 if all(r['status']=='PASS' for r in result) else 1)
