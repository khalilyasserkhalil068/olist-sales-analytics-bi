"""Independent report checks plus focused eligibility tests; no source writes."""
from decimal import Decimal
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
import pytest

from src.analysis.eda import delivery_masks, to_cents

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return pd.read_csv(ROOT / "data/processed" / f"{name}_clean.csv", dtype="string", keep_default_na=False, na_values=[""])


def independent_cents(values):
    return values.map(lambda value: int(Decimal(value) * 100)).astype("int64")


@pytest.fixture(scope="module")
def oracle():
    orders, items, customers = read("orders"), read("order_items"), read("customers")
    payments, reviews, products = read("payments"), read("reviews"), read("products")
    sales_ids = set(orders.loc[orders.order_status.eq("delivered"), "order_id"]) & set(items.order_id)
    selected_items = items.loc[items.order_id.isin(sales_ids)].copy()
    selected_items["cents"] = independent_cents(selected_items.price)
    selected_items["freight_cents"] = independent_cents(selected_items.freight_value)
    order_revenue = selected_items.groupby("order_id").cents.sum()
    order_freight = selected_items.groupby("order_id").freight_cents.sum()
    sales = orders.loc[orders.order_id.isin(sales_ids)].copy()
    customer_identities = customers.set_index("customer_id").customer_unique_id
    customer_states = customers.set_index("customer_id").customer_state
    sales["identity"] = sales.customer_id.map(customer_identities)
    sales["state"] = sales.customer_id.map(customer_states)
    sales["revenue"] = sales.order_id.map(order_revenue)
    frequency = sales.groupby("identity").order_id.nunique()
    p = payments.loc[payments.order_id.isin(sales_ids)].copy()
    p["cents"] = independent_cents(p.payment_value)
    r = reviews.loc[reviews.order_id.isin(sales_ids)].copy()
    r["score"] = pd.to_numeric(r.review_score)
    r = r.loc[r.score.between(1, 5)]
    mean_reviews = r.groupby("order_id").score.mean()
    dates = orders.copy()
    date_columns = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]
    for column in date_columns:
        dates[column] = pd.to_datetime(dates[column], format="%Y-%m-%d %H:%M:%S", errors="raise")
    delivered = dates.order_status.eq("delivered")
    actual, estimate, purchase = dates.order_delivered_customer_date, dates.order_estimated_delivery_date, dates.order_purchase_timestamp
    sla = delivered & actual.notna() & estimate.notna()
    on_time = sla & (actual.dt.date <= estimate.dt.date)
    invalid = pd.Series(False, index=dates.index)
    for first, second in [(date_columns[0], date_columns[1]), (date_columns[0], date_columns[2]), (date_columns[0], date_columns[3]), (date_columns[1], date_columns[2]), (date_columns[2], date_columns[3])]:
        invalid |= dates[first].notna() & dates[second].notna() & dates[second].lt(dates[first])
    duration = delivered & actual.notna() & purchase.notna() & actual.ge(purchase) & ~invalid
    return dict(orders=orders, items=items, products=products, sales_ids=sales_ids, selected_items=selected_items,
                order_revenue=order_revenue, order_freight=order_freight, sales=sales, frequency=frequency,
                payments=payments, selected_payments=p, reviews=r, mean_reviews=mean_reviews, dates=dates,
                delivered=delivered, sla=sla, on_time=on_time, duration=duration, customer_states=customer_states)


@pytest.fixture(scope="module")
def reports():
    names = ["eda_kpi_summary", "monthly_sales_summary", "category_performance", "customer_analysis_summary", "payment_analysis_summary", "delivery_performance_summary", "review_analysis_summary"]
    frames = {name: pd.read_csv(ROOT / "reports" / f"{name}.csv") for name in names}
    frames["kpis"] = frames["eda_kpi_summary"].set_index("metric")
    return frames


def test_exact_cent_conversion_does_not_round():
    assert to_cents(pd.Series(["0.10", "123456.78", "0.00"])).tolist() == [10, 12345678, 0]
    with pytest.raises(ValueError, match="fractional cent"):
        to_cents(pd.Series(["1.001"]))


def test_delivery_calendar_rule_keeps_duration_cohort_separate():
    frame = pd.DataFrame({
        "order_status": ["delivered", "delivered", "canceled", "delivered"],
        "order_purchase_timestamp": pd.to_datetime(["2018-01-01"] * 4),
        "order_approved_at": pd.to_datetime(["2018-01-03", "2018-01-01", "2018-01-01", "2018-01-01"]),
        "order_delivered_carrier_date": pd.to_datetime(["2018-01-02", "2018-01-02", "2018-01-02", "2018-01-02"]),
        "order_delivered_customer_date": pd.to_datetime(["2018-01-05 23:59:59", "2018-01-06 00:00:00", "2018-01-05 10:00:00", None]),
        "order_estimated_delivery_date": pd.to_datetime(["2018-01-05"] * 4),
    })
    flags = delivery_masks(frame)
    assert flags.on_time.tolist() == [True, False, False, False], "Same estimated calendar day must count as on time."
    assert flags.on_time_eligible.tolist() == [True, True, False, False]
    assert flags.duration_eligible.tolist() == [False, True, False, False], "Invalid carrier/approval sequence affects duration only."


def test_revenue_and_order_population_reconcile(oracle, reports):
    expected = int(oracle["selected_items"].cents.sum())
    k = reports["kpis"]
    assert round(k.loc["total_merchandise_revenue", "value"] * 100) == expected
    assert int(k.loc["total_orders", "value"]) == len(oracle["sales_ids"])
    assert int(k.loc["total_items_sold", "value"]) == len(oracle["selected_items"])
    assert k.loc["total_orders", "excluded_order_count"] == len(oracle["orders"]) - len(oracle["sales_ids"])
    assert oracle["sales"].order_id.is_unique, "Sales aggregation must remain one row per eligible order."


def test_order_level_aov_and_freight(oracle, reports):
    n = len(oracle["sales_ids"])
    expected = Decimal(int(oracle["selected_items"].cents.sum())) / 100 / n
    expected_freight = Decimal(int(oracle["selected_items"].freight_cents.sum())) / 100 / n
    assert float(reports["kpis"].loc["average_order_value", "value"]) == pytest.approx(float(expected), abs=1e-10)
    assert float(reports["kpis"].loc["average_freight_charge", "value"]) == pytest.approx(float(expected_freight), abs=1e-10)


def test_monthly_revenue_orders_and_growth(oracle, reports):
    sales = oracle["sales"].copy()
    sales["month"] = pd.to_datetime(sales.order_purchase_timestamp).dt.strftime("%Y-%m")
    sums = sales.groupby("month").revenue.sum()
    counts = sales.groupby("month").size()
    out = reports["monthly_sales_summary"].set_index("purchase_month")
    for month, row in out.iterrows():
        assert int(row.merchandise_revenue_cents) == int(sums.get(month, 0)), month
        assert int(row.eligible_orders) == int(counts.get(month, 0)), month
    assert int(out.merchandise_revenue_cents.sum()) == int(sales.revenue.sum())
    valid = out.comparable_month & out.comparable_month.shift(fill_value=False) & out.merchandise_revenue_cents.shift().gt(0)
    assert out.loc[~valid, "monthly_revenue_growth_pct"].isna().all(), "Do not report boundary/gap growth as a business decline."
    expected_growth = out.merchandise_revenue_cents.pct_change(fill_method=None) * 100
    np.testing.assert_allclose(out.loc[valid, "monthly_revenue_growth_pct"], expected_growth.loc[valid], rtol=1e-10)


def independent_categories(oracle):
    products = oracle["products"].set_index("product_id")
    labels = products.product_category_name_english.copy()
    labels.loc[products.dq_category_missing.eq("True")] = "Unknown (missing category)"
    labels.loc[products.dq_category_untranslated.eq("True")] = "Untranslated: " + products.product_category_name
    frame = oracle["selected_items"].copy()
    frame["category"] = frame.product_id.map(labels)
    return frame


def test_category_revenue_and_item_reconciliation(oracle, reports):
    source = independent_categories(oracle)
    expected = source.groupby("category").agg(cents=("cents", "sum"), items=("order_id", "size"))
    actual = reports["category_performance"].set_index("category_label").reindex(expected.index)
    assert actual.merchandise_revenue_cents.notna().all()
    np.testing.assert_array_equal(expected.cents, actual.merchandise_revenue_cents)
    np.testing.assert_array_equal(expected["items"], actual.items_sold)
    assert actual.revenue_contribution_pct.sum() == pytest.approx(100)
    assert int(actual.merchandise_revenue_cents.sum()) == int(oracle["selected_items"].cents.sum())


def test_distinct_customers_repeat_rate_and_state(oracle, reports):
    frequency = oracle["frequency"]
    expected_repeat = 100 * frequency.ge(2).mean()
    k = reports["kpis"]
    actual = reports["customer_analysis_summary"].set_index("customer_unique_id")
    assert int(k.loc["total_unique_customers", "value"]) == len(frequency) == len(actual)
    assert k.loc["repeat_customer_rate", "value"] == pytest.approx(expected_repeat)
    np.testing.assert_array_equal(actual.reindex(frequency.index).eligible_orders, frequency)
    assert int(actual.eligible_orders.sum()) == len(oracle["sales_ids"])
    expected_revenue = oracle["sales"].groupby("identity").revenue.sum()
    np.testing.assert_array_equal(actual.reindex(expected_revenue.index).merchandise_revenue_cents, expected_revenue)
    latest = oracle["sales"].sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("identity", keep="last").set_index("identity").state
    assert actual.reindex(latest.index).last_observed_customer_state.eq(latest).all()


def test_payments_preserve_their_grain_and_values(oracle, reports):
    p = oracle["selected_payments"]
    out = reports["payment_analysis_summary"]
    methods = out.loc[out.analysis_type.eq("payment_type")].set_index("group")
    expected = p.groupby("payment_type").agg(cents=("cents", "sum"), count=("order_id", "size"))
    for method, row in expected.iterrows():
        assert int(methods.loc[method, "recorded_payment_cents"]) == row.cents
        assert int(methods.loc[method, "payment_transactions"]) == row["count"]
    assert methods.payment_transaction_share_pct.sum() == pytest.approx(100)
    source_total = sum(Decimal(value) for value in oracle["payments"].payment_value)
    source_row = out.loc[out.analysis_type.eq("scope_summary") & out.group.eq("all recorded payments")].iloc[0]
    assert Decimal(str(source_row.recorded_payment_brl)) == source_total
    for view in ["installments_all_methods", "credit_card_installments"]:
        selected = out.loc[out.analysis_type.eq(view)]
        assert selected.payment_transaction_share_pct.sum() == pytest.approx(100)
    types = p.groupby("order_id").payment_type.nunique().reindex(sorted(oracle["sales_ids"]), fill_value=0)
    actual = out.loc[out.analysis_type.eq("payment_types_per_order")].copy()
    for _, row in actual.iterrows():
        assert int(row.order_count) == int(types.eq(int(float(row["group"]))).sum())


def test_payment_reconciliation_differences_are_reported_not_forced(oracle, reports):
    payments = oracle["payments"].copy()
    payments["cents"] = independent_cents(payments.payment_value)
    item_amounts = oracle["items"].copy()
    item_amounts["total_cents"] = independent_cents(item_amounts.price) + independent_cents(item_amounts.freight_value)
    item_totals = item_amounts.groupby("order_id").total_cents.sum()
    payment_totals = payments.groupby("order_id").cents.sum()
    out = reports["payment_analysis_summary"]
    for row in out.loc[out.analysis_type.eq("order_reconciliation_by_status")].itertuples(index=False):
        ids = set(oracle["orders"].loc[oracle["orders"].order_status.eq(row.group), "order_id"])
        common = sorted(ids & set(item_totals.index) & set(payment_totals.index))
        difference = payment_totals.reindex(common) - item_totals.reindex(common)
        assert int(row.comparable_orders) == len(common)
        assert int(row.exactly_reconciled_orders) == int(difference.eq(0).sum())
        assert int(row.payment_above_items_and_freight_orders) == int(difference.gt(0).sum())
        assert int(row.payment_below_items_and_freight_orders) == int(difference.lt(0).sum())


def test_delivery_calendar_denominators_and_duration(oracle, reports):
    d = reports["delivery_performance_summary"].set_index("customer_state").loc["ALL"]
    assert int(d.delivered_orders) == int(oracle["delivered"].sum())
    assert int(d.on_time_eligible_orders) == int(oracle["sla"].sum())
    assert int(d.on_time_orders) == int(oracle["on_time"].sum())
    assert int(d.late_orders) == int(oracle["sla"].sum() - oracle["on_time"].sum())
    assert d.on_time_rate_pct == pytest.approx(100 * oracle["on_time"].sum() / oracle["sla"].sum())
    assert int(d.duration_eligible_orders) == int(oracle["duration"].sum())
    frame = oracle["dates"]
    duration = ((frame.order_delivered_customer_date - frame.order_purchase_timestamp).dt.total_seconds() / 86400).loc[oracle["duration"]]
    assert d.average_delivery_duration_days == pytest.approx(duration.mean())
    canceled_with_delivery = frame.order_status.eq("canceled") & frame.order_delivered_customer_date.notna()
    assert not (canceled_with_delivery & oracle["delivered"]).any()
    assert reports["kpis"].loc["on_time_delivery_rate", "denominator"] == oracle["sla"].sum()
    assert reports["kpis"].loc["average_delivery_duration", "denominator"] == oracle["duration"].sum()


def test_delivery_by_state_uses_source_customer_state(oracle, reports):
    actual = reports["delivery_performance_summary"].set_index("customer_state")
    states = oracle["orders"].customer_id.map(oracle["customer_states"])
    for state in states.unique():
        within = states.eq(state)
        assert actual.loc[state, "delivered_orders"] == int((within & oracle["delivered"]).sum())
        assert actual.loc[state, "on_time_eligible_orders"] == int((within & oracle["sla"]).sum())
        assert actual.loc[state, "on_time_orders"] == int((within & oracle["on_time"]).sum())


def test_review_records_order_means_and_category_attribution(oracle, reports):
    r = oracle["reviews"]
    k = reports["kpis"]
    assert k.loc["average_review_score", "value"] == pytest.approx(r.score.mean())
    assert int(k.loc["average_review_score", "denominator"]) == len(r)
    out = reports["review_analysis_summary"]
    coverage = out.loc[out.analysis_type.eq("coverage")].iloc[0]
    assert int(coverage.reviewed_orders) == r.order_id.nunique()
    assert coverage.low_rating_record_pct == pytest.approx(100 * r.score.le(2).mean())
    assert not r.duplicated(["review_id", "order_id"]).any()
    order_categories = independent_categories(oracle)[["order_id", "category"]].drop_duplicates()
    order_categories["order_mean"] = order_categories.order_id.map(oracle["mean_reviews"])
    expected = order_categories.groupby("category").agg(score=("order_mean", "mean"), reviewed=("order_mean", "count"))
    actual = reports["category_performance"].set_index("category_label").reindex(expected.index)
    np.testing.assert_allclose(actual.average_order_review_score, expected.score, rtol=1e-10, equal_nan=True)
    np.testing.assert_array_equal(actual.reviewed_order_categories, expected.reviewed)


def test_kpi_dictionary_is_complete_and_documented(reports):
    k = reports["eda_kpi_summary"]
    assert len(k) == 10 and k.metric.is_unique
    for column in ["population", "formula", "exclusions", "denominator", "eligible_order_count", "excluded_order_count"]:
        assert k[column].notna().all(), f"Missing KPI definition field: {column}"


def test_no_input_csv_changed():
    import json
    fingerprints = json.loads((ROOT / "scripts/phase4/fingerprints.json").read_text(encoding="utf-8"))
    assert len(fingerprints) == 19, "Expected all nine raw and ten processed fingerprints."
    for relative, expected in fingerprints.items():
        with (ROOT / relative).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected, f"Input modified: {relative}"


def test_all_figures_are_high_resolution_pngs():
    expected = [path for path in (ROOT / "reports/figures").glob("[0-9][0-9]_*.png")]
    assert len(expected) == 22, "All requested chart families plus customer geography should be generated."
    for path in expected:
        with Image.open(path) as image:
            assert image.format == "PNG" and min(image.size) >= 900
            assert min(image.info.get("dpi", (0, 0))) >= 290
