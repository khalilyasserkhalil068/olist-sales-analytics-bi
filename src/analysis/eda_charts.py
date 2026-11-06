"""Consistent, static Phase 3 figures; all plotted populations are explicit."""
from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd
import seaborn as sns

NAVY, TEAL, GOLD, RED = "#23445D", "#178B8B", "#DFA740", "#BB4F54"


def brl_axis(value, position=None):
    if abs(value) >= 1e6:
        return f"R$ {value/1e6:.1f}m"
    if abs(value) >= 1000:
        return f"R$ {value/1000:.0f}k"
    return f"R$ {value:,.0f}"


def make_figures(a, directory):
    """Return saved paths in analysis order for notebook display and PNG export."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook", font="DejaVu Sans", palette=[NAVY, TEAL, GOLD, RED])
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
                         "axes.titlepad": 12, "figure.facecolor": "white", "savefig.facecolor": "white"})
    figures = {}

    def finish(name, fig, ax, title, subtitle, xlabel=None, ylabel=None):
        ax.set_title(title, loc="left", fontsize=15)
        if xlabel is not None:
            ax.set_xlabel(xlabel)
        if ylabel is not None:
            ax.set_ylabel(ylabel)
        fig.text(.02, .02, subtitle, ha="left", va="bottom", fontsize=9, color="#52616B", wrap=True)
        fig.tight_layout(rect=(.01, .08, .99, .98))
        fig.savefig(directory / name, dpi=300, bbox_inches="tight")
        figures[name] = directory / name
        plt.close(fig)

    def horizontal(name, frame, labels, values, title, subtitle, currency=False, full_ids=False, percent=False):
        frame = frame.iloc[::-1]
        fig, ax = plt.subplots(figsize=(10.5, 6))
        text = frame[labels].astype(str).tolist()
        text = text if full_ids else [textwrap.fill(label.replace("_", " "), 30) for label in text]
        ax.barh(range(len(frame)), frame[values].astype(float), color=TEAL)
        ax.set_yticks(range(len(frame)), text, fontsize=8 if full_ids else 9)
        ax.grid(axis="y", visible=False)
        if currency:
            ax.xaxis.set_major_formatter(FuncFormatter(brl_axis))
        if percent:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0f}%"))
        finish(name, fig, ax, title, subtitle, values.replace("_", " ").capitalize(), "")

    monthly = a["monthly"]
    for field, filename, title, label, money in [
        ("merchandise_revenue_brl", "01_monthly_revenue_trend.png", "Monthly Merchandise Revenue", "Merchandise revenue (BRL)", True),
        ("eligible_orders", "02_monthly_order_volume.png", "Monthly Eligible Order Volume", "Delivered orders with items", False),
        ("average_order_value_brl", "03_monthly_aov_trend.png", "Average Order Value by Purchase Month", "Merchandise AOV (BRL/order)", True),
    ]:
        fig, ax = plt.subplots(figsize=(11, 5.3))
        positions = np.arange(len(monthly))
        ax.plot(positions, monthly[field].astype(float), color=NAVY, linewidth=2, marker="o", markersize=4)
        for index, comparable in enumerate(monthly["comparable_month"]):
            if not comparable:
                ax.axvspan(index - .5, index + .5, color=GOLD, alpha=.15, linewidth=0)
        ticks = positions[::2]
        ax.set_xticks(ticks, monthly["purchase_month"].iloc[::2], rotation=40, ha="right")
        ax.set_ylim(bottom=0)
        if money:
            ax.yaxis.set_major_formatter(FuncFormatter(brl_axis))
        finish(filename, fig, ax, title, "Delivered sales cohort • Shaded launch/tail months retained but excluded from growth and decline claims.", "Purchase month", label)
    status_chart = a["status"].sort_values("merchandise_revenue_brl", ascending=False).copy()
    status_chart["status_label"] = status_chart["order_status"].astype(str)
    status_chart.loc[status_chart["merchandise_revenue_brl"].isna(), "status_label"] += " (no item records)"
    status_chart["merchandise_revenue_brl"] = status_chart["merchandise_revenue_brl"].fillna(0)
    horizontal("04_revenue_by_order_status.png", status_chart, "status_label", "merchandise_revenue_brl", "Recorded Item Revenue by Order Status",
               "All-status context • No-item label means no recorded amount, not a valid zero basket • Delivered only in primary KPI.", currency=True)

    top_categories = a["categories"].head(10)
    horizontal("05_top_categories_revenue.png", top_categories, "category_label", "merchandise_revenue_brl", "Top 10 Categories by Merchandise Revenue",
               "Delivered sales cohort • English translations where available; missing/untranslated buckets remain in full report.", currency=True)
    horizontal("06_top_products_revenue.png", a["products"].head(10), "product_id", "merchandise_revenue_brl", "Top 10 Products by Merchandise Revenue",
               "Source product IDs are shown in full • No product names are available or inferred.", currency=True, full_ids=True)
    horizontal("07_category_revenue_contribution.png", top_categories, "category_label", "revenue_contribution_pct", "Category Revenue Contribution",
               "Top 10 categories shown • Shares use all eligible category revenue as the denominator.", percent=True)

    customers = a["customers"]
    buckets = customers["eligible_orders"].clip(upper=5).value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
    fig, ax = plt.subplots(figsize=(9.5, 5))
    bars = ax.bar(["1", "2", "3", "4", "5+"], buckets, color=[NAVY, TEAL, TEAL, TEAL, TEAL])
    ax.bar_label(bars, labels=[f"{n:,}" for n in buckets], padding=4, fontsize=9)
    ax.set_ylim(0, buckets.max() * 1.15)
    finish("08_customer_purchase_frequency.png", fig, ax, "Customer Purchase Frequency Distribution", "Distinct customer_unique_id • Count distinct eligible orders, not order-item rows.", "Eligible orders per customer in this download", "Customers")
    horizontal("09_top_states_revenue.png", a["states"].head(10), "customer_state", "merchandise_revenue_brl", "Top States by Merchandise Revenue",
               "Source customer_state attached to each order • No state inferred from ZIP coordinates.", currency=True)
    fig, ax = plt.subplots(figsize=(9.5, 5))
    values = customers["merchandise_revenue_brl"].astype(float)
    sns.histplot(np.log1p(values), bins=55, color=TEAL, ax=ax)
    ticks_brl = [0, 50, 100, 250, 500, 1000, 5000, 20000]
    ticks_brl = [x for x in ticks_brl if x <= values.max()]
    ax.set_xticks(np.log1p(ticks_brl), [f"R$ {x:,}" for x in ticks_brl], rotation=35, ha="right")
    finish("10_customer_revenue_distribution.png", fig, ax, "Customer Merchandise Revenue Distribution", "All eligible customer identities shown • Horizontal position is log(1 + BRL), not a linear currency scale.", "Observed revenue per customer (log1p position; BRL labels)", "Customers per log-revenue bin")
    counts = [int(customers["eligible_orders"].eq(1).sum()), int(customers["eligible_orders"].ge(2).sum())]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bars = ax.bar(["One observed purchase", "Repeat: 2+ purchases"], counts, color=[NAVY, TEAL])
    ax.bar_label(bars, labels=[f"{n:,}\n({100*n/len(customers):.2f}%)" for n in counts], padding=5)
    ax.set_ylim(0, max(counts) * 1.2)
    finish("11_first_time_vs_repeat_customers.png", fig, ax, "First-Time vs Repeat Customers", "“First-time” is an observed-window proxy: one eligible purchase does not prove lifetime first purchase.", "Eligible purchase history in the download", "Distinct customer identities")
    horizontal("12_customer_geographic_distribution.png", a["states"].sort_values("customers_by_last_observed_state", ascending=False),
               "customer_state", "customers_by_last_observed_state", "Geographic Distribution of Eligible Customers",
               "One source state per identity: last observed eligible order • Not authoritative current residence.")

    methods = a["payments"].loc[a["payments"]["analysis_type"].eq("payment_type")].sort_values("payment_transactions", ascending=False)
    horizontal("13_payment_method_distribution.png", methods, "group", "payment_transactions", "Payment Method Distribution",
               "Eligible sales payment records • An order may contain multiple payment methods and sequences.")
    installments = a["payments"].loc[a["payments"]["analysis_type"].eq("credit_card_installments")].copy()
    installments["installments"] = pd.to_numeric(installments["group"])
    installments = installments.sort_values("installments")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(installments["installments"].astype(str), installments["payment_transactions"], color=[RED if n <= 0 else TEAL for n in installments["installments"]])
    ax.tick_params(axis="x", rotation=45)
    finish("14_installment_distribution.png", fig, ax, "Installments per Credit-Card Payment", "Eligible credit-card payment records only • Non-positive counts, when present, are retained and colored red.", "Recorded installments", "Payment records")
    horizontal("15_payment_value_by_type.png", methods.sort_values("recorded_payment_brl", ascending=False), "group", "recorded_payment_brl", "Recorded Payment Value by Type",
               "Eligible sales payment records • Recorded payment value is not merchandise revenue and may include freight.", currency=True)

    overall = a["delivery"].loc[a["delivery"]["customer_state"].eq("ALL")].iloc[0]
    counts = [int(overall["on_time_orders"]), int(overall["late_orders"])]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bars = ax.bar(["On time", "Late"], counts, color=[TEAL, RED])
    ax.bar_label(bars, labels=[f"{n:,}\n({100*n/sum(counts):.2f}%)" for n in counts], padding=5)
    ax.set_ylim(0, max(counts) * 1.2)
    finish("16_on_time_vs_late_delivery.png", fig, ax, "On-Time vs Late Delivery", f"Delivered status only • Calendar-date convention • Eligible n={sum(counts):,}; missing dates excluded.", "Delivery outcome", "Eligible delivered orders")
    duration = a["delivered"].loc[a["delivered"]["duration_eligible"], "delivery_duration_days"].astype(float)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(np.log1p(duration), bins=55, color=NAVY, ax=ax)
    ticks_days = [0, 1, 3, 7, 14, 30, 60, 120, 240]
    ticks_days = [value for value in ticks_days if value <= duration.max()]
    ax.set_xticks(np.log1p(ticks_days), ticks_days)
    finish("17_delivery_duration_distribution.png", fig, ax, "Delivery Duration Distribution", f"All valid durations retained • n={len(duration):,} • Chronology exclusions apply only to duration.", "Elapsed days (log1p position; day labels)", "Orders per log-duration bin")
    states = a["delivery"].loc[~a["delivery"]["customer_state"].eq("ALL")].sort_values("on_time_rate_pct", ascending=False)
    frame = states.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10.5, 8.5))
    bars = ax.barh(frame["customer_state"], frame["on_time_rate_pct"], color=TEAL)
    ax.bar_label(bars, labels=[f"n={int(n):,}" for n in frame["on_time_eligible_orders"]], padding=3, fontsize=8)
    ax.set_xlim(0, 113)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0f}%" if x <= 100 else ""))
    finish("18_delivery_performance_by_state.png", fig, ax, "On-Time Delivery Rate by Customer State", "Source customer_state • Calendar-day delivery denominator shown per state; small states have less stable rates.", "On-time share of date-eligible delivered orders", "Customer state")
    bands = a["delay_reviews"]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    bars = ax.bar(np.arange(len(bands)), bands["average_order_review_score"], color=[TEAL] * 4 + [RED] * 4)
    ax.bar_label(bars, labels=[f"n={int(n):,}" for n in bands["reviewed_orders"]], padding=3, fontsize=8)
    ax.set_xticks(np.arange(len(bands)), bands["delay_band"], rotation=30, ha="right")
    ax.set_ylim(0, 5.5)
    finish("19_delivery_delay_vs_review_score.png", fig, ax, "Delivery Delay vs Average Order Review Score", "One mean rating per reviewed order • Signed calendar-day delay bands • Association does not establish causation.", "Actual minus estimated delivery date", "Mean order review score (1–5)")

    review_counts = a["review_records"]["review_score"].value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(review_counts.index.astype(str), review_counts, color=[RED, RED, GOLD, TEAL, NAVY])
    ax.bar_label(bars, labels=[f"{int(n):,}" for n in review_counts], padding=4)
    ax.set_ylim(0, review_counts.max() * 1.15)
    finish("20_review_score_distribution.png", fig, ax, "Review Score Distribution", "Valid review/order records for eligible sales • Optional missing review text does not remove ratings.", "Recorded score", "Review records")
    category_ratings = top_categories.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    bars = ax.barh(np.arange(len(category_ratings)), category_ratings["average_order_review_score"], color=TEAL)
    ax.set_yticks(np.arange(len(category_ratings)), [textwrap.fill(x.replace("_", " "), 28) for x in category_ratings["category_label"]], fontsize=9)
    ax.bar_label(bars, labels=[f"n={int(n):,}" for n in category_ratings["reviewed_order_categories"]], padding=3, fontsize=8)
    ax.set_xlim(0, 5.6)
    finish("21_average_rating_by_category.png", fig, ax, "Average Rating by Category — Top 10 Revenue Categories", "One order mean per distinct order/category • Ratings describe orders containing a category, not product reviews.", "Average order review score (1–5); n=reviewed orders", "")
    delivery_reviews = a["reviewed_delivery"][["on_time", "mean_order_review_score"]].copy()
    delivery_reviews["Delivery outcome"] = np.where(delivery_reviews["on_time"], "On time", "Late")
    fig, ax = plt.subplots(figsize=(8.5, 5))
    sns.boxplot(data=delivery_reviews, x="Delivery outcome", y="mean_order_review_score", order=["On time", "Late"], color=TEAL, ax=ax, showfliers=False)
    ax.set_ylim(.7, 5.3)
    finish("22_review_score_vs_delivery_performance.png", fig, ax, "Review Scores vs Delivery Performance", "One mean rating per order • Box: quartiles/median; whiskers: 1.5 IQR • Outlier markers omitted, observations retained.", "Calendar-day delivery classification", "Mean order review score (1–5)")
    return figures
