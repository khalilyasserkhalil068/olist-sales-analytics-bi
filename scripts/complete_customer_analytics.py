"""Build and execute the canonical customer and cohort notebooks."""
from pathlib import Path
import sys
import json
import hashlib
import datetime

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.eda import input_hashes
from src.analysis.customer_analytics import load_eligible, customer_analysis, cohort_analysis, export_aggregates

OUT = ROOT / "reports/completion_20261101/customer_analytics"
OUT.mkdir(parents=True, exist_ok=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

setup = '''from pathlib import Path
import sys, json
ROOT = Path.cwd()
while not (ROOT / 'src/analysis/eda.py').exists():
    if ROOT.parent == ROOT:
        raise RuntimeError('Run this notebook inside the project directory')
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
from src.analysis.customer_analytics import load_eligible, customer_analysis, cohort_analysis
OUT = ROOT / 'reports/completion_20261101/customer_analytics'
OUT.mkdir(parents=True, exist_ok=True)
eligible = load_eligible(ROOT)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': 'white'})
print(f'Eligible delivered orders: {len(eligible):,}; customer IDs use customer_unique_id.')
'''

customer_cells = [
nbf.v4.new_markdown_cell('''# Customer Analysis — Completed

This notebook implements customer analysis for the curated project. It measures **observed-window behavior**, not lifetime acquisition or churn. The population matches the established sales analysis: delivered orders with at least one recorded item. Merchandise revenue excludes freight, uses exact integer cents, and is aggregated to order grain before customer joins.

`customer_id` identifies an order-associated customer record; `customer_unique_id` identifies the repeat customer. Each order is counted once. No raw/cleaned inputs are changed and no individual customer identifiers are exported.
'''),
nbf.v4.new_code_cell(setup),
nbf.v4.new_markdown_cell('''## Customers, repeat behavior and revenue

Single-order and repeat customers are mutually exclusive over the full observed period. In monthly acquisition-style charts, “First observed month” includes all purchases in a customer's first eligible month; “Returning month” refers to later months. Neither proves a first-ever purchase outside the dataset. A customer making multiple purchases in one month contributes once to that month's customer count.
'''),
nbf.v4.new_code_cell('''result = customer_analysis(eligible)
display(pd.Series(result['summary'], name='value').to_frame())
display(result['frequency'])
display(result['monthly'].tail(12))
'''),
nbf.v4.new_markdown_cell('''## RFM segmentation

The reference date is the day after the latest eligible purchase, anchored to this historical dataset. Recency is calendar days since the last eligible purchase. Frequency is the number of distinct eligible orders. Monetary value is the sum of merchandise cents.

R and M use average percentile ranks mapped to scores 1–5; all tied values receive the same score. More recent and higher-value customers score higher. F uses explicit order counts (1, 2, 3, 4, 5+), because a large tied one-order population makes five equal-sized frequency groups misleading. The six segments combine recent (R≥4), repeat (F≥2), and high monetary value (M≥4) as documented in the module. These are descriptive prioritization rules, not validated response or churn predictions.
'''),
nbf.v4.new_code_cell('''display(result['segments'].sort_values('customers', ascending=False))
fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
customers = result['customers']
axes[0,0].bar(['One order', 'Two or more'], [int(customers.frequency.eq(1).sum()), int(customers.frequency.ge(2).sum())], color=['#197A8C','#E09F3E'])
axes[0,0].set(title='Observed customer purchase frequency', ylabel='Customers')
revenue = customers.monetary_cents.astype(float) / 100
axes[0,1].hist(revenue, bins=np.geomspace(max(revenue.min(), .01), revenue.max(), 45), color='#197A8C')
axes[0,1].set_xscale('log')
axes[0,1].set(title='Customer merchandise revenue distribution', xlabel='BRL per customer (log scale)', ylabel='Customers')
segments = result['segments'].sort_values('customers')
axes[1,0].barh(segments.index, segments.customers, color='#197A8C')
axes[1,0].set(title='RFM-based descriptive segments', xlabel='Customers')
geo = result['geography'].nlargest(10, 'customers').sort_values('customers')
axes[1,1].barh(geo.index, geo.customers, color='#197A8C')
axes[1,1].set(title='Top customer states (latest eligible order)', xlabel='Unique customers')
fig.savefig(OUT / 'customer_profile.png', dpi=160)
plt.show()
'''),
nbf.v4.new_markdown_cell('''## Customer geography

For a mutually exclusive customer geographic split, each customer is assigned to their latest eligible order's state; order ID breaks timestamp ties deterministically. Revenue in this table is all eligible lifetime-in-window revenue for customers assigned to that state. It differs deliberately from order-location revenue and should not replace the Power BI order-state sales measure.
'''),
nbf.v4.new_code_cell('''display(result['geography'].sort_values('customers', ascending=False))
monthly = result['monthly'].copy()
monthly.index = monthly.index.astype(str)
fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True, constrained_layout=True)
for ax, name, color in zip(axes, ['First observed month', 'Returning month'], ['#197A8C', '#E09F3E']):
    ax.bar(monthly.index, monthly[name], color=color)
    ax.set(title=name, ylabel='Unique customers')
axes[1].tick_params(axis='x', rotation=60)
axes[1].set_xlabel('Purchase month; edge months have incomplete/unknown coverage')
fig.savefig(OUT / 'customer_monthly_activity.png', dpi=160)
plt.show()
'''),
nbf.v4.new_code_cell('''s = result['summary']
display(Markdown(f"**Interpretation:** {s['repeat_customers']:,} of {s['unique_customers']:,} observed customers made at least two eligible orders ({s['repeat_customer_rate_pct']:.2f}%). Mean orders per customer are {s['orders_per_customer']:.3f}. The top 10% of customers by observed merchandise revenue account for {s['top_decile_revenue_share_pct']:.2f}% of revenue. This suggests testing repeat-purchase propositions and prioritizing service for high-value customers, but does not establish causality, profit, churn or customer lifetime value."))
assert result['customers'].index.is_unique
assert result['customers'].frequency.sum() == len(eligible)
assert result['customers'].monetary_cents.sum() == eligible.merchandise_revenue_cents.sum()
print('PASS: identity, order-count and exact-cent reconciliation assertions.')
''')]

cohort_cells = [
nbf.v4.new_markdown_cell('''# Cohort Analysis — Completed

This notebook implements cohort analysis for the curated project. Cohorts use each `customer_unique_id`'s **first observed eligible purchase month**. Eligible means delivered with at least one item, aligned with established sales metrics. Retention is the fraction of a cohort making at least one eligible purchase in a later calendar month. It is not continuous survival, subscription retention, or the percentage returning at any time.

Customers are deduplicated within month before counting. Month 0 is 100% by construction. A customer may skip a month and return later. Future, not-yet-observed ages are blank; an observable month with no repeat purchase is zero. The latest observed eligible month is marked as a potentially incomplete snapshot tail and excluded from pooled repeat-rate claims. Completeness of earlier months is not guaranteed by the source.
'''),
nbf.v4.new_code_cell(setup),
nbf.v4.new_code_cell('''cohort = cohort_analysis(eligible)
display(cohort['sizes'].rename('cohort_customers').to_frame())
display(cohort['rates'].round(3))
print('Latest observed eligible month:', cohort['last_observed_month'])
'''),
nbf.v4.new_markdown_cell('''## Retention heatmap

Month 0 is omitted from the color scale to make small repeat rates visible. The plotted cells cover ages 1–12. Blank cells are not yet observable; the full matrix, including month 0 and later ages, is available above and in aggregate CSV outputs. The color scale is clipped at 1.5%; the numeric cell labels retain their actual percentages. Some cells in the final observed month may be incomplete.
'''),
nbf.v4.new_code_cell('''matrix = cohort['rates'].reindex(columns=range(1, 13))
fig, ax = plt.subplots(figsize=(13, 10), constrained_layout=True)
colors = plt.get_cmap('YlGnBu').copy()
colors.set_bad('#EEEEEE')
im = ax.imshow(matrix.to_numpy(dtype=float), cmap=colors, vmin=0, vmax=1.5, aspect='auto')
ax.set_xticks(range(12), labels=range(1,13))
ax.set_yticks(range(len(matrix)), labels=[f'{x} (n={cohort["sizes"].loc[x]:,})' for x in matrix.index])
ax.set(xlabel='Months since first observed eligible purchase', ylabel='Customer cohort', title='Monthly repeat-purchase retention (%) | month 0 = 100%')
for row in range(len(matrix)):
    for col in range(12):
        value = matrix.iloc[row, col]
        if pd.notna(value):
            ax.text(col, row, f'{value:.2f}', ha='center', va='center', fontsize=8, color='white' if value >= .85 else '#172B4D')
fig.colorbar(im, ax=ax, label='Retention % (color maximum 1.5)')
fig.savefig(OUT / 'cohort_retention_heatmap.png', dpi=160)
plt.show()
'''),
nbf.v4.new_markdown_cell('''## Weighted retention and censoring

For each age, pooled retention divides total active customers by the sum of sizes of cohorts observable at that age, excluding activity in the last observed eligible month. Denominators change with age; this is not a single fixed-cohort survival curve. Small early cohorts are retained with explicit denominators so their volatile percentages are not mistaken for stable business patterns.
'''),
nbf.v4.new_code_cell('''display(cohort['pooled'].round(4))
fig, axes = plt.subplots(2, 1, figsize=(11,7), sharex=True, constrained_layout=True)
p = cohort['pooled']
axes[0].plot(p.index, p.weighted_retention_pct, marker='o', color='#197A8C')
axes[0].set(ylabel='Weighted monthly retention (%)', title='Observed repeat activity; snapshot-tail activity excluded')
axes[1].bar(p.index, p.eligible_cohort_customers, color='#E09F3E')
axes[1].set_yscale('log')
axes[1].set(xlabel='Cohort age (months)', ylabel='Eligible cohort customers (log scale)', title='Denominator changes by age; small early cohorts are unstable')
axes[1].set_xticks(p.index)
fig.savefig(OUT / 'cohort_weighted_retention.png', dpi=160)
plt.show()
'''),
nbf.v4.new_code_cell('''age1 = cohort['pooled'].loc[1]
display(Markdown(f"**Interpretation:** At age 1, {int(age1.active_customers):,} repeat-active customers / {int(age1.eligible_cohort_customers):,} eligible cohort customers gives {age1.weighted_retention_pct:.3f}% weighted monthly retention, excluding the snapshot tail. This differs from the all-window repeat customer rate because it measures purchases in one specific later month. Consider category-specific repeat-purchase experiments; do not label every inactive customer churned in this non-contractual marketplace."))
assert np.allclose(cohort['rates'][0], 100)
assert cohort['sizes'].sum() == eligible.customer_unique_id.nunique()
assert cohort['rates'].stack().dropna().between(0,100).all()
assert cohort['long'].loc[~cohort['long'].observed, 'retention_pct'].isna().all()
print('PASS: cohort size, month-0, bounded rate and future-censoring assertions.')
''')]


def main():
    before = input_hashes(ROOT)
    eligible = load_eligible(ROOT)
    customer = customer_analysis(eligible)
    cohort = cohort_analysis(eligible)
    export_aggregates(customer, cohort, OUT)
    execution = []
    for name, cells in [("04_customer_analysis.ipynb", customer_cells), ("05_cohort_analysis.ipynb", cohort_cells)]:
        path = ROOT / "notebooks" / name
        notebook = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {
            "display_name": "E-Commerce Sales BI (.venv)", "language": "python", "name": "ecommerce-sales-bi"}})
        NotebookClient(notebook, timeout=180, kernel_name="ecommerce-sales-bi", resources={"metadata": {"path": str(ROOT)}}).execute()
        nbf.validate(notebook)
        nbf.write(notebook, path)
        execution.append({"path": path.relative_to(ROOT).as_posix(), "code_cells_executed": sum(c.cell_type == "code" for c in notebook.cells), "error_outputs": sum(o.output_type == "error" for c in notebook.cells if c.cell_type == "code" for o in c.outputs), "sha256": digest(path)})
    after = input_hashes(ROOT)
    assert before == after, "Raw or processed input changed during analytics execution"
    evidence = {"run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "status": "PASS",
        "input_sha256_before": before, "input_sha256_after": after,
        "notebook_execution": execution, "summary": customer["summary"],
        "cohort_month_count": len(cohort["sizes"]), "last_observed_eligible_month": cohort["last_observed_month"],
        "age_1_tail_excluded": cohort["pooled"].loc[1].to_dict(),
        "runtime": {"python": sys.version, "pandas": __import__('pandas').__version__}}
    (OUT / "execution_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if 'sha256' not in k}, indent=2))


if __name__ == '__main__':
    main()
