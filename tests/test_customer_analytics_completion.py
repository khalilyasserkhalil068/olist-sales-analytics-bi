"""Regression cases for customer identity, tied scores, and censored cohorts."""
import pandas as pd
import numpy as np

from src.analysis.customer_analytics import customer_analysis, cohort_analysis


def sample():
    return pd.DataFrame({
        "order_id": ["a1", "a2", "a3", "b1", "c1"],
        "customer_unique_id": ["a", "a", "a", "b", "c"],
        "order_purchase_timestamp": pd.to_datetime(["2018-01-01", "2018-01-05", "2018-03-01", "2018-02-01", "2018-03-01"]),
        "merchandise_revenue_cents": [100, 100, 100, 300, 300],
        "customer_state": ["SP", "RJ", "RJ", "SP", "MG"],
    })


def test_identity_money_and_tied_scores():
    result = customer_analysis(sample())
    assert result["summary"]["unique_customers"] == 3
    assert result["summary"]["repeat_customers"] == 1
    assert result["summary"]["merchandise_revenue_cents"] == 900
    assert result["customers"]["m_score"].nunique() == 1
    assert result["customers"].loc["a", "latest_customer_state"] == "RJ"
    assert result["monthly"].loc[pd.Period("2018-01"), "First observed month"] == 1


def test_cohort_deduplicates_same_month_and_masks_future():
    result = cohort_analysis(sample())
    jan, feb, mar = map(lambda x: pd.Period(x, freq="M"), ["2018-01", "2018-02", "2018-03"])
    assert result["counts"].loc[jan, 0] == 1
    assert result["counts"].loc[jan, 1] == 0
    assert result["counts"].loc[jan, 2] == 1
    assert result["rates"].loc[jan, 2] == 100
    assert np.isnan(result["counts"].loc[mar, 1])
    assert np.isnan(result["counts"].loc[feb, 2])
    # March is the snapshot tail; pooled age-one result uses only January -> February.
    assert result["pooled"].loc[1, "eligible_cohort_customers"] == 1
    assert result["pooled"].loc[1, "weighted_retention_pct"] == 0
