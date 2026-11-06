"""Observed-window customer and cohort analytics; no writes to source datasets."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from src.analysis.eda import load_data, build_order_view


def customer_analysis(eligible):
    """One customer row per customer_unique_id; monetary amounts remain integer cents."""
    assert eligible["order_id"].is_unique
    assert eligible["customer_unique_id"].notna().all()
    assert eligible["order_purchase_timestamp"].notna().all()
    snapshot = eligible["order_purchase_timestamp"].max().normalize() + pd.Timedelta(days=1)
    customer = eligible.groupby("customer_unique_id").agg(
        first_purchase=("order_purchase_timestamp", "min"),
        last_purchase=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary_cents=("merchandise_revenue_cents", "sum"),
    )
    customer["recency_days"] = (snapshot - customer["last_purchase"].dt.normalize()).dt.days
    # Average ranks keep tied values together. Frequency is deliberately not quantiled:
    # the large one-order population would make five equal-sized groups misleading.
    customer["r_score"] = np.ceil(customer["recency_days"].rank(method="average", ascending=False, pct=True) * 5).clip(1, 5).astype(int)
    customer["f_score"] = customer["frequency"].clip(upper=5).astype(int)
    customer["m_score"] = np.ceil(customer["monetary_cents"].rank(method="average", pct=True) * 5).clip(1, 5).astype(int)
    customer["rfm_code"] = customer[["r_score", "f_score", "m_score"]].astype(str).agg("".join, axis=1)
    repeat = customer["frequency"].ge(2)
    recent = customer["r_score"].ge(4)
    valuable = customer["m_score"].ge(4)
    customer["segment"] = np.select(
        [repeat & recent & valuable, repeat & recent, repeat & ~recent,
         ~repeat & recent & valuable, ~repeat & recent],
        ["Recent high-value repeat", "Recent repeat", "Earlier repeat",
         "Recent high-value single", "Recent single"], default="Earlier single")
    # Assign a customer's geography once using the latest eligible order, with order_id
    # as the deterministic tie-breaker. Order revenue geography remains order-specific.
    latest = eligible.sort_values(["order_purchase_timestamp", "order_id"]).drop_duplicates("customer_unique_id", keep="last").set_index("customer_unique_id")
    customer["latest_customer_state"] = latest["customer_state"]
    segments = customer.groupby("segment").agg(customers=("frequency", "size"),
        orders=("frequency", "sum"), revenue_cents=("monetary_cents", "sum"),
        median_recency_days=("recency_days", "median"))
    segments["customer_share_pct"] = segments["customers"] / len(customer) * 100
    segments["revenue_share_pct"] = segments["revenue_cents"] / customer["monetary_cents"].sum() * 100
    frequency = customer.groupby("frequency").agg(customers=("frequency", "size"), revenue_cents=("monetary_cents", "sum"))
    geography = customer.groupby("latest_customer_state", dropna=False).agg(
        customers=("frequency", "size"), repeat_customers=("frequency", lambda s: s.ge(2).sum()),
        revenue_cents=("monetary_cents", "sum"))
    geography["repeat_customer_rate_pct"] = geography["repeat_customers"] / geography["customers"] * 100
    activity = eligible[["order_id", "customer_unique_id", "order_purchase_timestamp"]].copy()
    activity["month"] = activity["order_purchase_timestamp"].dt.to_period("M")
    activity["first_month"] = activity["customer_unique_id"].map(customer["first_purchase"].dt.to_period("M"))
    activity["customer_type"] = np.where(activity["month"].eq(activity["first_month"]), "First observed month", "Returning month")
    monthly = activity.groupby(["month", "customer_type"])["customer_unique_id"].nunique().unstack(fill_value=0)
    monthly = monthly.reindex(columns=["First observed month", "Returning month"], fill_value=0)
    monthly = monthly.reindex(pd.period_range(activity["month"].min(), activity["month"].max(), freq="M"), fill_value=0)
    monthly.index.name = "month"
    summary = {"eligible_orders": len(eligible), "unique_customers": len(customer),
        "single_order_customers": int((~repeat).sum()), "repeat_customers": int(repeat.sum()),
        "repeat_customer_rate_pct": float(repeat.mean() * 100),
        "orders_per_customer": len(eligible) / len(customer),
        "merchandise_revenue_cents": int(customer["monetary_cents"].sum()),
        "snapshot_date": snapshot.date().isoformat(),
        "first_eligible_purchase": str(eligible["order_purchase_timestamp"].min()),
        "last_eligible_purchase": str(eligible["order_purchase_timestamp"].max()),
        "median_customer_revenue_brl": float(customer["monetary_cents"].median() / 100),
        "top_decile_revenue_share_pct": float(customer["monetary_cents"].sort_values(ascending=False).head(int(np.ceil(len(customer)*.1))).sum() / customer["monetary_cents"].sum() * 100),
        "max_orders_per_customer": int(customer["frequency"].max())}
    assert customer["frequency"].sum() == len(eligible)
    assert customer["monetary_cents"].sum() == eligible["merchandise_revenue_cents"].sum()
    assert segments["customers"].sum() == len(customer)
    assert geography["customers"].sum() == len(customer)
    assert (monthly.sum(axis=1) == activity.groupby("month")["customer_unique_id"].nunique().reindex(monthly.index, fill_value=0)).all()
    return dict(customers=customer, segments=segments, frequency=frequency,
                geography=geography, monthly=monthly, summary=summary)


def cohort_analysis(eligible):
    """Monthly repeat activity, not continuous survival. Future ages are NaN, not zero."""
    activity = eligible[["customer_unique_id", "order_purchase_timestamp"]].copy()
    activity["purchase_month"] = activity["order_purchase_timestamp"].dt.to_period("M")
    activity = activity[["customer_unique_id", "purchase_month"]].drop_duplicates()
    first = activity.groupby("customer_unique_id")["purchase_month"].min()
    activity["cohort_month"] = activity["customer_unique_id"].map(first)
    activity["age"] = activity["purchase_month"].astype("int64") - activity["cohort_month"].astype("int64")
    sizes = first.value_counts().sort_index()
    sizes.index.name = "cohort_month"
    last = activity["purchase_month"].max()
    max_age = last.ordinal - sizes.index.min().ordinal
    counts = activity.groupby(["cohort_month", "age"])["customer_unique_id"].nunique().unstack().reindex(index=sizes.index, columns=range(max_age + 1))
    observed = pd.DataFrame([[cohort.ordinal + age <= last.ordinal for age in counts.columns] for cohort in counts.index], index=counts.index, columns=counts.columns)
    counts = counts.fillna(0).where(observed)
    rates = counts.div(sizes, axis=0) * 100
    assert np.allclose(rates[0], 100)
    assert sizes.sum() == eligible["customer_unique_id"].nunique()
    assert rates.stack().dropna().between(0, 100).all()
    assert counts.where(~observed).isna().all().all()
    long = []
    for cohort in counts.index:
        for age in counts.columns:
            target = cohort + age
            n = counts.loc[cohort, age]
            long.append(dict(cohort_month=str(cohort), age=int(age), activity_month=str(target),
                cohort_customers=int(sizes.loc[cohort]), active_customers=None if pd.isna(n) else int(n),
                retention_pct=None if pd.isna(n) else float(rates.loc[cohort, age]),
                observed=bool(observed.loc[cohort, age]), snapshot_tail=target == last))
    long = pd.DataFrame(long)
    # Exclude the last observed eligible month from pooled repeat-rate claims. This
    # conservative tail exclusion does not establish completeness of earlier months.
    mature = long.loc[long["observed"] & ~long["snapshot_tail"] & long["age"].gt(0)]
    pooled = mature.groupby("age").agg(active_customers=("active_customers", "sum"),
        eligible_cohort_customers=("cohort_customers", "sum"), eligible_cohorts=("cohort_month", "size"))
    pooled["weighted_retention_pct"] = pooled["active_customers"] / pooled["eligible_cohort_customers"] * 100
    return dict(counts=counts, rates=rates, sizes=sizes, long=long, pooled=pooled,
                last_observed_month=str(last))


def load_eligible(project_root):
    orders = build_order_view(load_data(Path(project_root) / "data/processed"))
    return orders.loc[orders["sales_eligible"]].copy()


def export_aggregates(customer, cohort, output_directory):
    """Only aggregate outputs; individual customer identifiers stay in memory."""
    out = Path(output_directory)
    out.mkdir(parents=True, exist_ok=True)
    for key in ["segments", "frequency", "geography", "monthly"]:
        customer[key].to_csv(out / f"customer_{key}.csv")
    for key in ["counts", "rates", "long", "pooled"]:
        cohort[key].to_csv(out / f"cohort_{key}.csv", index=key != "long")
    (out / "customer_summary.json").write_text(json.dumps(customer["summary"], indent=2), encoding="utf-8")
