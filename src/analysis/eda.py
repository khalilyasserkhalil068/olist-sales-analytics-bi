"""Descriptive Olist analysis with explicit populations and exact-cent aggregation."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_processing.cleaning import DATE_COLUMNS, DATE_FORMAT, NUMERIC_COLUMNS

SALES_STATUSES = ("delivered",)
CHRONOLOGY_FLAGS = [
    "dq_approval_before_purchase", "dq_carrier_before_purchase", "dq_delivery_before_purchase",
    "dq_carrier_before_approval", "dq_delivery_before_carrier",
]
DELAY_LABELS = ["14+ days early", "7–13 days early", "1–6 days early", "On estimated day",
                "1–3 days late", "4–7 days late", "8–14 days late", "15+ days late"]


def input_hashes(project_root):
    """Fingerprint all 19 raw/processed CSVs without altering them."""
    root = Path(project_root)
    hashes = {}
    for folder in [root / "data/raw", root / "data/processed"]:
        for path in sorted(folder.glob("*.csv")):
            with path.open("rb") as stream:
                hashes[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes


def to_cents(values):
    """Keep all monetary sums exact; fail instead of rounding fractional cents."""
    def convert(value):
        if pd.isna(value):
            return pd.NA
        amount = Decimal(str(value)) * 100
        if amount != amount.to_integral_value():
            raise ValueError(f"Unexpected fractional cent: {value}")
        return int(amount)
    return values.map(convert).astype("Int64")


def load_data(processed_directory):
    """Load the analytical tables; repeated geographic observations are not joined."""
    directory = Path(processed_directory)
    names = ["orders", "customers", "order_items", "products", "payments", "reviews", "sellers", "category_translations"]
    data = {}
    for name in names:
        frame = pd.read_csv(directory / f"{name}_clean.csv", dtype="string", keep_default_na=False, na_values=[""], encoding="utf-8")
        for column in frame:
            if column.startswith("dq_"):
                assert frame[column].isin(["True", "False"]).all(), f"Invalid flag: {name}.{column}"
                frame[column] = frame[column].map({"True": True, "False": False}).astype("boolean")
        for column in ["price", "freight_value"] if name == "order_items" else ["payment_value"] if name == "payments" else []:
            frame[f"{column}_cents"] = to_cents(frame[column])
        for column in DATE_COLUMNS.get(name, []):
            frame[column] = pd.to_datetime(frame[column], format=DATE_FORMAT, errors="raise")
        for column in NUMERIC_COLUMNS.get(name, []):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        data[name] = frame
    data["zip_lookup"] = pd.read_csv(directory / "geolocation_zip_lookup.csv", dtype="string", keep_default_na=False, na_values=[""])
    for column in data["zip_lookup"]:
        if column.startswith("dq_"):
            data["zip_lookup"][column] = data["zip_lookup"][column].map({"True": True, "False": False}).astype("boolean")
    return data


def delivery_masks(frame):
    """Do not let duration-specific exclusions alter the calendar-day SLA cohort."""
    delivered = frame["order_status"].eq("delivered")
    actual, estimate, purchase = (frame[column] for column in [
        "order_delivered_customer_date", "order_estimated_delivery_date", "order_purchase_timestamp"
    ])
    on_time_eligible = delivered & actual.notna() & estimate.notna()
    on_time = on_time_eligible & actual.dt.normalize().le(estimate.dt.normalize())
    late = on_time_eligible & actual.dt.normalize().gt(estimate.dt.normalize())
    invalid_sequence = pd.Series(False, index=frame.index)
    for first, second in [
        ("order_purchase_timestamp", "order_approved_at"),
        ("order_purchase_timestamp", "order_delivered_carrier_date"),
        ("order_purchase_timestamp", "order_delivered_customer_date"),
        ("order_approved_at", "order_delivered_carrier_date"),
        ("order_delivered_carrier_date", "order_delivered_customer_date"),
    ]:
        if first in frame and second in frame:
            invalid_sequence |= frame[first].notna() & frame[second].notna() & frame[second].lt(frame[first])
    duration_eligible = delivered & purchase.notna() & actual.notna() & actual.ge(purchase) & ~invalid_sequence
    return pd.DataFrame({"is_delivered": delivered, "on_time_eligible": on_time_eligible,
                         "on_time": on_time, "late": late, "invalid_chronology": invalid_sequence,
                         "duration_eligible": duration_eligible}, index=frame.index)


def build_order_view(data):
    """Aggregate detail tables separately before any order-level joins."""
    items, payments, reviews = data["order_items"], data["payments"], data["reviews"]
    item_totals = items.groupby("order_id").agg(
        item_count=("order_item_id", "size"), merchandise_revenue_cents=("price_cents", "sum"),
        freight_cents=("freight_value_cents", "sum"),
    )
    payment_totals = payments.groupby("order_id").agg(
        payment_record_count=("payment_sequential", "size"), payment_type_count=("payment_type", "nunique"),
        recorded_payment_cents=("payment_value_cents", "sum"),
    )
    valid_reviews = reviews.loc[reviews["review_score"].between(1, 5)]
    review_totals = valid_reviews.groupby("order_id").agg(
        valid_review_record_count=("review_score", "size"), review_score_sum=("review_score", "sum"),
        mean_order_review_score=("review_score", "mean"),
    )
    orders = data["orders"].merge(data["customers"], on="customer_id", how="left", validate="many_to_one")
    for aggregate in [item_totals, payment_totals, review_totals]:
        orders = orders.merge(aggregate, on="order_id", how="left", validate="one_to_one")
    assert len(orders) == len(data["orders"]) and orders["order_id"].is_unique
    assert orders["customer_unique_id"].notna().all()
    for column in ["item_count", "payment_record_count", "payment_type_count", "valid_review_record_count"]:
        orders[column] = orders[column].fillna(0).astype("Int64")
    for column in ["merchandise_revenue_cents", "freight_cents", "recorded_payment_cents"]:
        orders[column] = orders[column].astype("Int64")
    orders["sales_eligible"] = orders["order_status"].isin(SALES_STATUSES) & orders["item_count"].gt(0)
    orders["purchase_month"] = orders["order_purchase_timestamp"].dt.to_period("M")
    masks = delivery_masks(orders)
    for column in masks:
        orders[column] = masks[column]
    assert orders["invalid_chronology"].equals(orders[CHRONOLOGY_FLAGS].any(axis=1).astype(bool))
    orders["delivery_duration_days"] = (
        (orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]).dt.total_seconds() / 86400
    ).where(orders["duration_eligible"])
    orders["signed_delivery_delay_days"] = (
        orders["order_delivered_customer_date"].dt.normalize() - orders["order_estimated_delivery_date"].dt.normalize()
    ).dt.days.where(orders["on_time_eligible"])
    comparable = orders[["merchandise_revenue_cents", "freight_cents", "recorded_payment_cents"]].notna().all(axis=1)
    orders["payment_reconciliation_eligible"] = comparable
    orders["payment_minus_items_and_freight_cents"] = (
        orders["recorded_payment_cents"] - orders["merchandise_revenue_cents"] - orders["freight_cents"]
    ).where(comparable)
    return orders


def sales_analysis(orders):
    eligible = orders.loc[orders["sales_eligible"]].copy()
    assert eligible["order_purchase_timestamp"].notna().all(), "Monthly reconciliation requires valid purchase dates."
    month_index = pd.period_range(orders["purchase_month"].min(), orders["purchase_month"].max(), freq="M")
    monthly = eligible.groupby("purchase_month").agg(
        eligible_orders=("order_id", "size"), merchandise_revenue_cents=("merchandise_revenue_cents", "sum"),
        freight_cents=("freight_cents", "sum"), items_sold=("item_count", "sum"),
        unique_customers=("customer_unique_id", "nunique"),
    ).reindex(month_index, fill_value=0)
    monthly.index.name = "purchase_month"
    monthly["all_status_order_count"] = orders.groupby("purchase_month").size().reindex(month_index, fill_value=0)
    monthly["excluded_order_count"] = monthly["all_status_order_count"] - monthly["eligible_orders"]
    monthly["merchandise_revenue_brl"] = monthly["merchandise_revenue_cents"] / 100
    monthly["freight_brl"] = monthly["freight_cents"] / 100
    monthly["average_order_value_brl"] = monthly["merchandise_revenue_brl"] / monthly["eligible_orders"].replace(0, np.nan)
    monthly["average_items_per_order"] = monthly["items_sold"] / monthly["eligible_orders"].replace(0, np.nan)
    first_full_year = orders["order_purchase_timestamp"].min().year + 1
    last_eligible_month = eligible["purchase_month"].max()
    monthly["comparable_month"] = (monthly.index >= pd.Period(f"{first_full_year}-01", freq="M")) & (monthly.index < last_eligible_month)
    monthly["coverage_note"] = np.where(monthly.index < pd.Period(f"{first_full_year}-01", freq="M"),
        "Launch/coverage window: not used for peak/trough or growth claims", np.where(monthly.index >= last_eligible_month,
        "Conservative snapshot-tail exclusion: not used for decline/growth claims", "Interior full calendar month; completeness still not guaranteed"))
    valid_growth = monthly["comparable_month"] & monthly["comparable_month"].shift(fill_value=False) & monthly["merchandise_revenue_cents"].shift().gt(0)
    monthly["monthly_revenue_growth_pct"] = (monthly["merchandise_revenue_cents"].pct_change(fill_method=None) * 100).where(valid_growth)
    monthly = monthly.reset_index()
    monthly["purchase_month"] = monthly["purchase_month"].astype(str)
    status = orders.groupby("order_status").agg(
        orders=("order_id", "size"), orders_with_items=("item_count", lambda values: int(values.gt(0).sum())),
        item_revenue_cents=("merchandise_revenue_cents", lambda values: values.sum(min_count=1)),
        freight_cents=("freight_cents", lambda values: values.sum(min_count=1)), eligible_orders=("sales_eligible", "sum"),
    ).reset_index()
    status["merchandise_revenue_brl"] = status["item_revenue_cents"] / 100
    status["freight_brl"] = status["freight_cents"] / 100
    status["included_in_primary_revenue"] = status["order_status"].isin(SALES_STATUSES)
    return eligible, monthly, status


def product_analysis(data, eligible):
    products = data["products"].copy()
    products["category_type"] = np.select([
        products["dq_category_missing"].to_numpy(dtype=bool), products["dq_category_untranslated"].to_numpy(dtype=bool)
    ], ["missing", "untranslated"], default="translated")
    products["category_label"] = products["product_category_name_english"].astype("string")
    products.loc[products["category_type"].eq("missing"), "category_label"] = "Unknown (missing category)"
    products.loc[products["category_type"].eq("untranslated"), "category_label"] = "Untranslated: " + products["product_category_name"]
    items = data["order_items"].loc[data["order_items"]["order_id"].isin(eligible["order_id"])].merge(
        products[["product_id", "category_label", "category_type"]], on="product_id", how="left", validate="many_to_one"
    )
    assert len(items) == int(eligible["item_count"].sum())
    categories = items.groupby(["category_label", "category_type"], dropna=False).agg(
        merchandise_revenue_cents=("price_cents", "sum"), freight_cents=("freight_value_cents", "sum"),
        items_sold=("order_item_id", "size"), eligible_orders=("order_id", "nunique"), distinct_products=("product_id", "nunique"),
    ).reset_index()
    categories["merchandise_revenue_brl"] = categories["merchandise_revenue_cents"] / 100
    categories["freight_brl"] = categories["freight_cents"] / 100
    categories["average_item_price_brl"] = categories["merchandise_revenue_brl"] / categories["items_sold"]
    categories["revenue_contribution_pct"] = 100 * categories["merchandise_revenue_cents"] / categories["merchandise_revenue_cents"].sum()
    categories = categories.sort_values(["merchandise_revenue_cents", "category_label"], ascending=[False, True]).reset_index(drop=True)
    categories["cumulative_revenue_pct"] = categories["revenue_contribution_pct"].cumsum()
    # One review-mean contribution per order/category, never one per item row.
    order_category = items[["order_id", "category_label"]].drop_duplicates().merge(
        eligible[["order_id", "mean_order_review_score"]], on="order_id", how="left", validate="many_to_one"
    )
    category_scores = order_category.groupby("category_label").agg(
        reviewed_order_categories=("mean_order_review_score", "count"), average_order_review_score=("mean_order_review_score", "mean")
    ).reset_index()
    categories = categories.merge(category_scores, on="category_label", how="left", validate="one_to_one")
    product_totals = items.groupby("product_id").agg(
        merchandise_revenue_cents=("price_cents", "sum"), items_sold=("order_item_id", "size"), eligible_orders=("order_id", "nunique")
    ).reset_index().sort_values(["merchandise_revenue_cents", "product_id"], ascending=[False, True])
    product_totals["merchandise_revenue_brl"] = product_totals["merchandise_revenue_cents"] / 100
    return items, categories, product_totals, order_category


def customer_analysis(eligible):
    customers = eligible.groupby("customer_unique_id").agg(
        eligible_orders=("order_id", "nunique"), items_sold=("item_count", "sum"),
        merchandise_revenue_cents=("merchandise_revenue_cents", "sum"), freight_cents=("freight_cents", "sum"),
        first_observed_purchase=("order_purchase_timestamp", "min"), last_observed_purchase=("order_purchase_timestamp", "max"),
    ).reset_index()
    customers["merchandise_revenue_brl"] = customers["merchandise_revenue_cents"] / 100
    customers["freight_brl"] = customers["freight_cents"] / 100
    customers["average_order_value_brl"] = customers["merchandise_revenue_brl"] / customers["eligible_orders"]
    customers["purchase_segment"] = np.where(customers["eligible_orders"].ge(2), "Repeat: 2+ observed orders", "One observed order")
    latest_state = eligible.sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("customer_unique_id", keep="last")[["customer_unique_id", "customer_state"]]
    latest_state = latest_state.rename(columns={"customer_state": "last_observed_customer_state"})
    customers = customers.merge(latest_state, on="customer_unique_id", validate="one_to_one")
    states = eligible.groupby("customer_state").agg(
        merchandise_revenue_cents=("merchandise_revenue_cents", "sum"), eligible_orders=("order_id", "size"),
        unique_customers_with_orders_in_state=("customer_unique_id", "nunique"), freight_cents=("freight_cents", "sum"),
    ).reset_index()
    states["merchandise_revenue_brl"] = states["merchandise_revenue_cents"] / 100
    states["average_freight_per_order_brl"] = states["freight_cents"] / 100 / states["eligible_orders"]
    distribution = customers["last_observed_customer_state"].value_counts()
    states["customers_by_last_observed_state"] = states["customer_state"].map(distribution).fillna(0).astype(int)
    states = states.sort_values("merchandise_revenue_cents", ascending=False)
    frequency = customers["eligible_orders"].value_counts().sort_index().rename_axis("eligible_orders_per_customer").reset_index(name="customers")
    return customers.sort_values(["merchandise_revenue_cents", "customer_unique_id"], ascending=[False, True]), states, frequency


def payment_analysis(data, orders, eligible):
    payments = data["payments"]
    selected = payments.loc[payments["order_id"].isin(eligible["order_id"])].copy()
    rows = []
    def add(view, group, frame, scope="eligible delivered sales", share_denominator=None):
        count = len(frame)
        denominator = share_denominator if share_denominator is not None else len(selected) if scope == "eligible delivered sales" else len(payments)
        rows.append({"analysis_type": view, "group": str(group), "population": scope,
                     "payment_transactions": count, "distinct_orders": frame["order_id"].nunique(),
                     "recorded_payment_cents": int(frame["payment_value_cents"].sum()),
                     "recorded_payment_brl": frame["payment_value_cents"].sum() / 100,
                     "payment_transaction_denominator": denominator,
                     "payment_transaction_share_pct": 100 * count / denominator if denominator else np.nan,
                     "nonpositive_installment_records": int(frame["payment_installments"].le(0).sum())})
    add("scope_summary", "all recorded payments", payments, "all source order statuses")
    add("scope_summary", "eligible sales payments", selected)
    for name, frame in selected.groupby("payment_type"):
        add("payment_type", name, frame)
    for number, frame in selected.groupby("payment_installments", dropna=False):
        add("installments_all_methods", number, frame)
    credit = selected.loc[selected["payment_type"].eq("credit_card")]
    for number, frame in credit.groupby("payment_installments", dropna=False):
        add("credit_card_installments", number, frame, "eligible sales credit-card payment records", share_denominator=len(credit))
    for column, view in [("payment_type_count", "payment_types_per_order"), ("payment_record_count", "payment_transactions_per_order")]:
        for number, frame in eligible.groupby(column):
            rows.append({"analysis_type": view, "group": str(number), "population": "eligible delivered sales orders",
                         "order_count": len(frame), "order_share_pct": 100 * len(frame) / len(eligible),
                         "order_denominator": len(eligible),
                         "recorded_payment_cents": frame["recorded_payment_cents"].sum(min_count=1),
                         "recorded_payment_brl": frame["recorded_payment_cents"].sum(min_count=1) / 100})
    for status, frame in orders.groupby("order_status"):
        comparable = frame.loc[frame["payment_reconciliation_eligible"]]
        differences = comparable["payment_minus_items_and_freight_cents"]
        rows.append({"analysis_type": "order_reconciliation_by_status", "group": status, "population": "all source order statuses",
                     "order_count": len(frame), "orders_with_items": int(frame["item_count"].gt(0).sum()),
                     "orders_with_payments": int(frame["payment_record_count"].gt(0).sum()), "comparable_orders": len(comparable),
                     "noncomparable_orders": len(frame) - len(comparable),
                     "merchandise_revenue_cents": frame["merchandise_revenue_cents"].sum(min_count=1),
                     "freight_cents": frame["freight_cents"].sum(min_count=1),
                     "recorded_payment_cents": frame["recorded_payment_cents"].sum(min_count=1),
                     "recorded_payment_brl": frame["recorded_payment_cents"].sum(min_count=1) / 100,
                     "exactly_reconciled_orders": int(differences.eq(0).sum()),
                     "payment_above_items_and_freight_orders": int(differences.gt(0).sum()),
                     "payment_below_items_and_freight_orders": int(differences.lt(0).sum()),
                     "comparable_payment_difference_cents": differences.sum(min_count=1)})
    return pd.DataFrame(rows), selected


def delivery_analysis(orders):
    delivered = orders.loc[orders["is_delivered"]].copy()
    rows = []
    for state, frame in [("ALL", delivered), *list(delivered.groupby("customer_state"))]:
        sla = frame.loc[frame["on_time_eligible"]]
        duration = frame.loc[frame["duration_eligible"], "delivery_duration_days"]
        freight = frame.loc[frame["freight_cents"].notna(), "freight_cents"]
        rows.append({"customer_state": state, "population": "order_status == delivered", "delivered_orders": len(frame),
                     "on_time_eligible_orders": len(sla), "on_time_excluded_orders": len(frame) - len(sla),
                     "on_time_orders": int(sla["on_time"].sum()), "late_orders": int(sla["late"].sum()),
                     "on_time_rate_pct": 100 * sla["on_time"].sum() / len(sla) if len(sla) else np.nan,
                     "late_rate_pct": 100 * sla["late"].sum() / len(sla) if len(sla) else np.nan,
                     "duration_eligible_orders": len(duration), "duration_excluded_orders": len(frame) - len(duration),
                     "average_delivery_duration_days": duration.mean(), "median_delivery_duration_days": duration.median(),
                     "p90_delivery_duration_days": duration.quantile(.9), "average_signed_delay_days": sla["signed_delivery_delay_days"].mean(),
                     "freight_eligible_orders": len(freight), "average_freight_charge_brl": freight.mean() / 100,
                     "on_time_reviewed_orders": int(sla.loc[sla["on_time"], "mean_order_review_score"].notna().sum()),
                     "on_time_average_order_review_score": sla.loc[sla["on_time"], "mean_order_review_score"].mean(),
                     "late_reviewed_orders": int(sla.loc[sla["late"], "mean_order_review_score"].notna().sum()),
                     "late_average_order_review_score": sla.loc[sla["late"], "mean_order_review_score"].mean()})
    reviewed = delivered.loc[delivered["on_time_eligible"] & delivered["mean_order_review_score"].notna()].copy()
    reviewed["delay_band"] = pd.cut(reviewed["signed_delivery_delay_days"], [-np.inf, -14, -7, -1, 0, 3, 7, 14, np.inf], labels=DELAY_LABELS)
    delay_reviews = reviewed.groupby("delay_band", observed=False).agg(
        reviewed_orders=("order_id", "size"), average_order_review_score=("mean_order_review_score", "mean")
    ).reset_index()
    delay_reviews["delay_band"] = delay_reviews["delay_band"].astype(str)
    return pd.DataFrame(rows), delivered, reviewed, delay_reviews


def review_analysis(data, eligible, categories, reviewed_delivery, delay_reviews):
    records = data["reviews"].loc[data["reviews"]["order_id"].isin(eligible["order_id"]) & data["reviews"]["review_score"].between(1, 5)].copy()
    rows = []
    for score in range(1, 6):
        selected = records.loc[records["review_score"].eq(score)]
        rows.append({"analysis_type": "review_score_distribution", "group": str(score), "grain": "review/order record",
                     "review_records": len(selected), "reviewed_orders": selected["order_id"].nunique(),
                     "record_share_pct": 100 * len(selected) / len(records), "average_review_score": score})
    covered = eligible["mean_order_review_score"].notna()
    rows.append({"analysis_type": "coverage", "group": "eligible sales orders", "grain": "order",
                 "eligible_orders": len(eligible), "reviewed_orders": int(covered.sum()), "orders_without_valid_review": int((~covered).sum()),
                 "review_records": len(records), "coverage_pct": 100 * covered.mean(),
                 "average_review_score": records["review_score"].mean(), "average_order_review_score": eligible["mean_order_review_score"].mean(),
                 "low_rating_record_pct": 100 * records["review_score"].le(2).mean()})
    for row in categories.itertuples(index=False):
        rows.append({"analysis_type": "category_rating", "group": row.category_label, "grain": "distinct reviewed order/category pair",
                     "reviewed_orders": row.reviewed_order_categories, "average_order_review_score": row.average_order_review_score})
    for label, mask in [("On time", reviewed_delivery["on_time"]), ("Late", reviewed_delivery["late"])]:
        selected = reviewed_delivery.loc[mask]
        rows.append({"analysis_type": "delivery_rating", "group": label, "grain": "reviewed order",
                     "reviewed_orders": len(selected), "average_order_review_score": selected["mean_order_review_score"].mean()})
    for row in delay_reviews.itertuples(index=False):
        rows.append({"analysis_type": "delay_band_rating", "group": row.delay_band, "grain": "reviewed order",
                     "reviewed_orders": row.reviewed_orders, "average_order_review_score": row.average_order_review_score})
    return pd.DataFrame(rows), records


def kpi_dictionary(orders, eligible, customers, review_records, delivery):
    all_count, sales_count = len(orders), len(eligible)
    duration = orders.loc[orders["duration_eligible"], "delivery_duration_days"]
    sla = orders.loc[orders["on_time_eligible"]]
    repeated = int(customers["eligible_orders"].ge(2).sum())
    rows = []
    def add(metric, label, value, unit, numerator, denominator, population, formula, exclusions, eligible_count, excluded_count):
        rows.append({"metric": metric, "kpi": label, "value": float(value), "unit": unit,
                     "numerator": float(numerator), "denominator": int(denominator), "eligible_order_count": int(eligible_count),
                     "excluded_order_count": int(excluded_count), "population": population, "formula": formula, "exclusions": exclusions})
    sales_population = "Delivered orders with >=1 item record; all periods in the observed download"
    sales_exclusions = "Exclude non-delivered statuses and orders without recorded items; no accounting/refund/profit inference"
    revenue = int(eligible["merchandise_revenue_cents"].sum()) / 100
    add("total_merchandise_revenue", "Total Merchandise Revenue", revenue, "BRL", revenue, 1, sales_population, "Sum eligible order_items.price, aggregated per order; exclude freight", sales_exclusions, sales_count, all_count - sales_count)
    add("total_orders", "Total Orders", sales_count, "orders", sales_count, 1, sales_population, "Count distinct eligible order_id", sales_exclusions, sales_count, all_count - sales_count)
    add("average_order_value", "Average Order Value", revenue / sales_count, "BRL/order", revenue, sales_count, sales_population, "Sum order-level merchandise revenue / distinct eligible orders", sales_exclusions, sales_count, all_count - sales_count)
    add("total_unique_customers", "Total Unique Customers", len(customers), "customers", len(customers), 1, sales_population, "Count distinct customer_unique_id after joining orders via customer_id", sales_exclusions, sales_count, all_count - sales_count)
    items = int(eligible["item_count"].sum())
    add("total_items_sold", "Total Items Sold", items, "item records", items, 1, sales_population, "Count eligible order-item rows; one item per source sequence; no quantity field assumed", sales_exclusions, sales_count, all_count - sales_count)
    freight = int(eligible["freight_cents"].sum()) / 100
    add("average_freight_charge", "Average Freight Charge", freight / sales_count, "BRL/order", freight, sales_count, sales_population, "Sum item freight per eligible order / eligible orders; separate from merchandise", sales_exclusions, sales_count, all_count - sales_count)
    on_time = int(sla["on_time"].sum())
    add("on_time_delivery_rate", "On-Time Delivery Rate", 100 * on_time / len(sla), "%", on_time, len(sla), "All delivered-status orders with actual and estimated delivery timestamps", "100 * count(delivered orders where actual calendar date <= estimated calendar date) / count(delivered orders with both dates)", "Exclude non-delivered and missing actual/estimated dates; do not apply duration-only chronology exclusions", len(sla), all_count - len(sla))
    add("average_delivery_duration", "Average Delivery Duration", duration.mean(), "days", duration.sum(), len(duration), "Delivered orders with purchase/delivery endpoints and no known chronology contradictions", "Mean (actual delivery timestamp - purchase timestamp) in elapsed 24-hour days", "Exclude missing endpoints, negative intervals and all known contradictory milestone sequences from duration only; missing intermediate milestones alone are not exclusions", len(duration), all_count - len(duration))
    review_orders = review_records["order_id"].nunique()
    add("average_review_score", "Average Review Score", review_records["review_score"].mean(), "score 1–5", review_records["review_score"].sum(), len(review_records), "Valid review/order records for eligible sales orders", "Sum review scores / valid review record count; preserve distinct (review_id, order_id)", "Exclude non-eligible orders and invalid/missing scores; optional missing review text remains included", review_orders, all_count - review_orders)
    add("repeat_customer_rate", "Repeat Customer Rate", 100 * repeated / len(customers), "%", repeated, len(customers), sales_population, "100 * customer_unique_id with >=2 distinct eligible orders / distinct eligible customers", "Observed-window repeat behavior only; one-purchase group is not proven lifetime first-time acquisition", sales_count, all_count - sales_count)
    return pd.DataFrame(rows)


def quality_impact(data, orders, items, source_flag_report):
    rows = []
    eligible = set(orders.loc[orders["sales_eligible"], "order_id"])
    for name, frame in data.items():
        for column in frame:
            if not column.startswith("dq_") or not pd.api.types.is_bool_dtype(frame[column].dtype):
                continue
            selected = frame.loc[frame[column].fillna(False)]
            if "order_id" in selected:
                impacted = set(selected["order_id"]) & eligible
            elif "customer_id" in selected:
                impacted = set(orders.loc[orders["customer_id"].isin(selected["customer_id"]), "order_id"]) & eligible
            elif "product_id" in selected:
                impacted = set(items.loc[items["product_id"].isin(selected["product_id"]), "order_id"])
            elif "seller_id" in selected:
                impacted = set(items.loc[items["seller_id"].isin(selected["seller_id"]), "order_id"])
            elif "zip_code_prefix" in selected:
                impacted = set(orders.loc[orders["customer_zip_code_prefix"].isin(selected["zip_code_prefix"]), "order_id"]) & eligible
            else:
                impacted = set()
            if len(selected):
                rows.append({"dataset": "geolocation_zip_lookup" if name == "zip_lookup" else name, "rule": column[3:], "source_flagged_records": len(selected), "eligible_sales_orders_affected": len(impacted)})
    report_counts = source_flag_report.groupby(["dataset", "rule"]).size()
    for row in rows:
        assert int(report_counts.get((row["dataset"], row["rule"]), 0)) == row["source_flagged_records"]
    return pd.DataFrame(rows)


def run_analysis(data, source_flag_report):
    orders = build_order_view(data)
    eligible, monthly, status = sales_analysis(orders)
    items, categories, products, order_category = product_analysis(data, eligible)
    customers, states, frequency = customer_analysis(eligible)
    payments, selected_payments = payment_analysis(data, orders, eligible)
    delivery, delivered, reviewed_delivery, delay_reviews = delivery_analysis(orders)
    reviews, review_records = review_analysis(data, eligible, categories, reviewed_delivery, delay_reviews)
    kpis = kpi_dictionary(orders, eligible, customers, review_records, delivery)
    impact = quality_impact(data, orders, items, source_flag_report)
    assert int(items["price_cents"].sum()) == int(eligible["merchandise_revenue_cents"].sum()) == int(monthly["merchandise_revenue_cents"].sum()) == int(categories["merchandise_revenue_cents"].sum()) == int(customers["merchandise_revenue_cents"].sum())
    assert int(customers["eligible_orders"].sum()) == len(eligible)
    assert int(selected_payments["payment_value_cents"].sum()) == int(eligible["recorded_payment_cents"].sum())
    assert len(order_category) == len(items[["order_id", "category_label"]].drop_duplicates())
    return dict(data=data, orders=orders, eligible=eligible, monthly=monthly, status=status, items=items, categories=categories,
                products=products, order_category=order_category, customers=customers, states=states, frequency=frequency,
                payments=payments, selected_payments=selected_payments, delivery=delivery, delivered=delivered,
                reviewed_delivery=reviewed_delivery, delay_reviews=delay_reviews, reviews=reviews, review_records=review_records,
                kpis=kpis, impact=impact)


def export_reports(analysis, reports_directory):
    mapping = {"eda_kpi_summary.csv": "kpis", "monthly_sales_summary.csv": "monthly", "category_performance.csv": "categories",
               "customer_analysis_summary.csv": "customers", "payment_analysis_summary.csv": "payments",
               "delivery_performance_summary.csv": "delivery", "review_analysis_summary.csv": "reviews"}
    for filename, table in mapping.items():
        path = Path(reports_directory) / filename
        frame = analysis[table]
        frame.to_csv(path, index=False, encoding="utf-8", date_format=DATE_FORMAT, lineterminator="\n")
        saved = pd.read_csv(path)
        assert saved.shape == frame.shape
    return list(mapping)


def table_md(frame):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(escape, frame.columns)) + " |", "| " + " | ".join(["---"] * len(frame.columns)) + " |"] +
                     ["| " + " | ".join(map(escape, row)) + " |" for row in frame.itertuples(index=False, name=None)])


def write_insights(a, destination, hashes, figure_names, validation_status):
    k = a["kpis"].set_index("metric")["value"]
    brl = lambda value: f"R$ {value:,.2f}"
    comparable = a["monthly"].loc[a["monthly"]["comparable_month"]]
    peak = comparable.loc[comparable["merchandise_revenue_cents"].idxmax()]
    low = comparable.loc[comparable["merchandise_revenue_cents"].idxmin()]
    top_categories = a["categories"].head(10)
    top_share = top_categories["revenue_contribution_pct"].sum()
    concentration_count = int(a["categories"]["cumulative_revenue_pct"].lt(80).sum()) + 1
    best = top_categories.iloc[0]
    customer_count = len(a["customers"])
    repeats = int(a["customers"]["eligible_orders"].ge(2).sum())
    leading_state = a["states"].iloc[0]
    methods = a["payments"].loc[a["payments"]["analysis_type"].eq("payment_type")].sort_values("recorded_payment_cents", ascending=False)
    leading_method = methods.iloc[0]
    scopes = a["payments"].loc[a["payments"]["analysis_type"].eq("scope_summary")].set_index("group")
    delivery = a["delivery"].loc[a["delivery"]["customer_state"].eq("ALL")].iloc[0]
    coverage = a["reviews"].loc[a["reviews"]["analysis_type"].eq("coverage")].iloc[0]
    day = a["reviewed_delivery"]
    spearman = day["signed_delivery_delay_days"].astype(float).corr(day["mean_order_review_score"].astype(float), method="spearman")
    unknown = a["categories"].loc[~a["categories"]["category_type"].eq("translated")]
    matched = a["eligible"].loc[a["eligible"]["payment_reconciliation_eligible"]]
    different = matched["payment_minus_items_and_freight_cents"].ne(0)
    canceled_delivery_count = int((a["orders"]["order_status"].eq("canceled") & a["orders"]["order_delivered_customer_date"].notna()).sum())
    ambiguous_city_prefixes = int(a["data"]["zip_lookup"]["dq_conflicting_city_labels"].sum())
    ambiguous_state_prefixes = int(a["data"]["zip_lookup"]["dq_conflicting_states"].sum())
    financial_summary = pd.DataFrame([
        {"population": "Eligible delivered sales", "merchandise_brl": a["eligible"]["merchandise_revenue_cents"].sum() / 100,
         "freight_brl": a["eligible"]["freight_cents"].sum() / 100, "recorded_payments_brl": a["eligible"]["recorded_payment_cents"].sum() / 100},
        {"population": "All source statuses", "merchandise_brl": a["data"]["order_items"]["price_cents"].sum() / 100,
         "freight_brl": a["data"]["order_items"]["freight_value_cents"].sum() / 100, "recorded_payments_brl": a["data"]["payments"]["payment_value_cents"].sum() / 100},
    ])
    lines = [
        "# Phase 3 — Exploratory Data Analysis Insights",
        "## Executive Summary",
        f"Observed delivered merchandise revenue is **{brl(k['total_merchandise_revenue'])}** across **{int(k['total_orders']):,} eligible orders** and **{customer_count:,} customer identities**. AOV is **{brl(k['average_order_value'])}**, excluding freight. Calendar-day on-time delivery is **{k['on_time_delivery_rate']:.2f}%**; review-record average is **{k['average_review_score']:.3f}/5**. These are descriptive results for the supplied download, not accounting recognition, profit, forecasts or causal estimates.",
        f"Primary sales population: delivered status and at least one recorded item. Eligible orders={len(a['eligible']):,}; excluded orders={len(a['orders'])-len(a['eligible']):,}; all-status orders={len(a['orders']):,}. Purchase timestamps assign sales periods. Data source: the user's unchanged local Olist CSVs, attributed to Olist's Brazilian E-Commerce Public Dataset.",
        "## KPI Definitions",
        table_md(a["kpis"][["kpi", "value", "unit", "numerator", "denominator", "eligible_order_count", "excluded_order_count"]].round(6)),
        table_md(a["kpis"][["kpi", "population", "formula", "exclusions"]]),
        "All merchandise/freight/payment sums are accumulated as integer cents from exact Decimal strings. Monetary fields in CSV reports include the integer-cent columns; BRL and rates are presentation values. Item totals, payment totals and review means are built separately at order grain and merged with explicit cardinality validation. The primary sales cohort is consistent across products, customers, payment details and review records. Delivery metrics use delivered status independently, with their own explicit date denominators.",
        "## Sales Performance Findings",
        f"**Evidence:** revenue={brl(k['total_merchandise_revenue'])}; AOV={brl(k['average_order_value'])}; items sold={int(k['total_items_sold']):,}; average items/order={a['eligible']['item_count'].mean():.3f}. Freight is separate at {brl(a['eligible']['freight_cents'].sum()/100)} and {brl(k['average_freight_charge'])} per eligible order. **Interpretation:** purchase counts and basket value must be assessed separately. **Action:** reconcile order-level merchandise and freight measures independently in the future warehouse; do not use payment amounts as merchandise revenue.",
        f"**Evidence:** within the conservative comparable interval {comparable['purchase_month'].min()}–{comparable['purchase_month'].max()}, the highest-revenue month is {peak['purchase_month']} ({brl(peak['merchandise_revenue_brl'])}); the lowest is {low['purchase_month']} ({brl(low['merchandise_revenue_brl'])}). **Interpretation:** this is a ranking within the declared interior window, not all calendar months or a causal explanation. **Action:** use only adjacent comparable months for month-over-month claims.",
        "All observed months, including zero-eligible months, remain in monthly_sales_summary.csv and the plots. Launch/coverage months before January of the first full observed calendar year are excluded from peak/trough and growth claims. The last delivered-purchase month and later months are conservatively excluded as a snapshot tail. This interior-window policy does not prove completeness; the file supplies no extraction/completeness metadata. With one full calendar year and limited repeated months, recurring sales seasonality is not established. A peak in a calendar month alone does not prove a holiday or promotion effect.",
        table_md(a["status"]),
        "Revenue by status is a context table across all statuses, not extra primary-cohort revenue. Orders without items have unknown recorded item amounts; their absence is reported rather than imputed as a valid zero-revenue basket.",
        "## Product Performance Findings",
        f"**Evidence:** leading category {best['category_label']} contributes {brl(best['merchandise_revenue_brl'])} ({best['revenue_contribution_pct']:.2f}%). Top ten categories contribute {top_share:.2f}%; {concentration_count} categories reach at least 80% cumulative revenue. **Interpretation:** revenue is concentrated, but category revenue alone does not establish margins or inventory profitability. **Action:** prioritize category-level availability and delivery investigations among the leading categories before making stock-investment decisions.",
        table_md(top_categories[["category_label", "merchandise_revenue_brl", "items_sold", "average_item_price_brl", "revenue_contribution_pct"]].round(3)),
        "Top categories by item count:", table_md(a["categories"].nlargest(10, "items_sold")[["category_label", "items_sold", "merchandise_revenue_brl"]]),
        "Top products are identified by source product_id; product names are not available and were not invented:", table_md(a["products"].head(10)[["product_id", "merchandise_revenue_brl", "items_sold", "eligible_orders"]]),
        "Unknown and untranslated category buckets remain separate:", table_md(unknown[["category_label", "category_type", "items_sold", "merchandise_revenue_brl", "revenue_contribution_pct"]]),
        "## Customer Behavior Findings",
        f"**Evidence:** {repeats:,}/{customer_count:,} observed eligible customer identities placed at least two distinct eligible orders ({k['repeat_customer_rate']:.2f}%). The remaining {customer_count-repeats:,} have one observed eligible purchase. **Interpretation:** repeat purchasing is limited in this observation window; the one-purchase group is not proof of first-ever acquisition or verified churn. **Action:** investigate repeat-purchase opportunities descriptively in the later approved customer phase; do not infer lifetime value or churn here.",
        f"**Evidence:** state {leading_state['customer_state']} leads order-attributed revenue at {brl(leading_state['merchandise_revenue_brl'])}. **Interpretation:** direct source customer_state avoids ambiguous ZIP-based state inference. **Action:** compare state revenue with delivery service and freight before operational prioritization.",
        table_md(a["states"][["customer_state", "eligible_orders", "unique_customers_with_orders_in_state", "customers_by_last_observed_state", "merchandise_revenue_brl"]]),
        "State revenue follows the customer record attached to each order. A customer with purchases in several states can appear in several per-state distinct counts; those counts must not be added nationally. For the geographic customer-distribution chart only, assign each identity to its last observed eligible order's source state (purchase timestamp, then order_id tie-break). This is observed ordering history, not authoritative current residence.",
        "Top customer identities by merchandise revenue (source IDs, not names):", table_md(a["customers"].head(10)[["customer_unique_id", "eligible_orders", "merchandise_revenue_brl", "last_observed_customer_state"]]),
        "## Payment Analysis",
        table_md(financial_summary.round(2)),
        f"**Evidence:** {leading_method['group']} has the largest eligible recorded payment value ({brl(leading_method['recorded_payment_brl'])}), across {int(leading_method['payment_transactions']):,} payment records. Eligible payment total={brl(scopes.loc['eligible sales payments','recorded_payment_brl'])}; all-status recorded payments={brl(scopes.loc['all recorded payments','recorded_payment_brl'])}. **Interpretation:** payment rows are payment sequences, not orders; methods can coexist on an order and may include freight. **Action:** retain payment grain and reconcile only after aggregation to order_id.",
        f"**Evidence:** {int(different.sum()):,}/{len(matched):,} eligible orders with both items and payments have a nonzero exact-cent difference between recorded payment and items plus freight. {int(a['eligible']['payment_record_count'].eq(0).sum())} eligible orders have no payment record. **Interpretation:** these are recorded reconciliation differences, not automatically revenue errors; the dataset cannot explain every adjustment. **Action:** preserve differences for investigation rather than forcing equality or changing values.",
        "Payment reports explicitly distinguish method counts, all-method installment counts, credit-card installment counts, payment types per order, payment records per order, and all-status order reconciliation. Non-positive installments are retained; their source flag counts and eligible impact are shown below. Credit-card installment charts use credit-card records only, with that denominator stated.",
        "## Delivery Performance",
        f"**Evidence:** delivered-status orders={int(delivery['delivered_orders']):,}; on-time eligible={int(delivery['on_time_eligible_orders']):,}; excluded for missing actual/estimated dates={int(delivery['on_time_excluded_orders']):,}. On time={int(delivery['on_time_orders']):,} ({delivery['on_time_rate_pct']:.2f}%); late={int(delivery['late_orders']):,} ({delivery['late_rate_pct']:.2f}%). Compare calendar dates, not timestamps; delivery on the estimated day counts as on time. The {canceled_delivery_count} canceled orders with delivery dates are not delivered-status orders and are excluded.",
        f"**Evidence:** average delivery duration={delivery['average_delivery_duration_days']:.2f} elapsed days; median={delivery['median_delivery_duration_days']:.2f}; p90={delivery['p90_delivery_duration_days']:.2f}; eligible={int(delivery['duration_eligible_orders']):,}; excluded={int(delivery['duration_excluded_orders']):,} delivered orders. **Interpretation:** duration requires purchase/delivery endpoints and no known contradictory milestone chronology. Missing intermediate approval/carrier timestamps alone do not invalidate an available end-to-end duration. These duration-specific exclusions do not remove records from sales, on-time classification or the underlying data. **Action:** publish each metric's denominator separately.",
        table_md(a["delivery"][["customer_state", "delivered_orders", "on_time_eligible_orders", "on_time_rate_pct", "duration_eligible_orders", "average_delivery_duration_days", "average_freight_charge_brl"]].round(3)),
        "Delivery duration plots use a log(1 + days) horizontal coordinate to show the complete long tail without deleting orders. Signed delay is calendar-day actual minus estimated date; negative values are early, zero is the estimated day. The delay-band plot reports average order review and sample count by signed-delay band.",
        "## Customer Satisfaction",
        f"**Evidence:** valid review records={len(a['review_records']):,}; review-record average={coverage['average_review_score']:.3f}/5; low ratings (1–2)={coverage['low_rating_record_pct']:.2f}%; order review coverage={int(coverage['reviewed_orders']):,}/{int(coverage['eligible_orders']):,} ({coverage['coverage_pct']:.2f}%). **Interpretation:** missing optional text is not missing rating and does not exclude reviews. Preserve distinct review/order records even when review_id repeats. **Action:** report both record-weighted average ratings and order coverage.",
        f"**Evidence:** reviewed on-time orders average {delivery['on_time_average_order_review_score']:.3f}/5 (n={int(delivery['on_time_reviewed_orders']):,}); reviewed late orders average {delivery['late_average_order_review_score']:.3f}/5 (n={int(delivery['late_reviewed_orders']):,}). Spearman association of signed delay days and mean order score is {spearman:.3f} across {len(day):,} reviewed delivery-eligible orders. **Interpretation:** this is an observed association, not evidence that delay alone caused a rating. **Action:** prioritize investigation of delivery service alongside other satisfaction drivers; do not claim a causal uplift from this EDA.",
        "Delivery associations first average valid reviews within each order. Category ratings contribute that order mean once per distinct order/category, not once per item. Multi-category orders contribute to each relevant category, so category reviewed-order counts cannot be summed into national coverage. Category ratings describe orders containing the category, not product-specific reviews.",
        "## Data Limitations and Quality Impact",
        table_md(a["impact"]),
        f"Source flags were audited rather than silently repaired. No-item, no-payment, no-review, chronology, category, ZIP and repeated-review conditions have different analytical impacts; the table distinguishes source record counts from affected eligible order counts. Flags can overlap. Unmatched ZIPs do not remove state revenue or customers, because source customer_state is used directly. Geographic reference accuracy and source timezone remain unverified. The ZIP lookup contains {ambiguous_city_prefixes:,} multi-city-label prefixes and {ambiguous_state_prefixes:,} cross-state prefixes; no authoritative state is inferred from those locations.",
        "Snapshot start/end and delivered-status selection can censor activity. Observation-window repeat rates are not retention, cohort analysis, lifetime value or verified churn. Profit, marketing spend, cart abandonment and net refund-adjusted revenue cannot be inferred from these tables. No forecasting or causal model has been implemented.",
        "## Business Recommendations",
        f"1. Prioritize descriptive availability/service reviews for the top ten categories ({top_share:.2f}% of eligible revenue); validate margins and stock constraints with additional sources before spending decisions.",
        f"2. Investigate late-delivery processes using the {int(delivery['late_orders']):,} calendar-day late eligible orders and state-level denominators. Keep correlation with ratings observational.",
        f"3. Examine why {customer_count-repeats:,} observed customers have only one eligible order; the current data does not establish churn. Defer RFM and cohort work to their approved phases.",
        "4. Preserve exact-cent merchandise, freight and payment measures separately, with explicit order-status eligibility. Do not force payment reconciliation differences to zero.",
        "5. Before the separately approved SQL Server/star-schema phase, document source grains, candidate keys, order-level aggregation rules, status/date populations, review/order-category attribution and Unknown/coverage handling. Design and implement nothing in that phase yet.",
        "## Generated Reports and Figures",
        "Reports: eda_kpi_summary.csv; monthly_sales_summary.csv; category_performance.csv; customer_analysis_summary.csv; payment_analysis_summary.csv; delivery_performance_summary.csv; review_analysis_summary.csv; phase_3_insights.md.",
        "Figures (PNG, 300 dpi):\n" + "\n".join(f"- reports/figures/{name}" for name in figure_names),
        "## Validation", validation_status,
        "## Input Fingerprints", table_md(pd.DataFrame([{"input_path": path, "sha256": digest} for path, digest in hashes.items()])),
        "All 19 input CSV fingerprints must remain unchanged after execution and in automated tests. Reports and figures are derived outputs; no raw or processed data is overwritten.",
        "**Phase 3 only. Stop and wait for approval before SQL Server, star-schema design/implementation, Power BI or later customer-analysis phases.**",
    ]
    Path(destination).write_text("\n\n".join(lines) + "\n", encoding="utf-8")
