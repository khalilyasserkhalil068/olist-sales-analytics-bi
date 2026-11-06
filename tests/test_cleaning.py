"""Focused regression tests for preservation, ZIP grain and financial integrity."""
from decimal import Decimal

import pandas as pd
import pytest

from src.data_processing.cleaning import (
    assert_financial_equal, build_zip_lookup, clean_datasets, export_and_verify,
    key_result, normalize_text, read_source_csv, validate_integrity,
)


def strings(data):
    return pd.DataFrame(data, dtype="string")


def test_review_text_preserves_case_accents_and_internal_whitespace():
    raw = strings({"message": ["  Ótimo!\nMuito  bom.  ", " \t ", None, "NA"]})
    snapshot = raw.copy(deep=True)
    cleaned, _ = normalize_text(raw)
    assert cleaned.loc[0, "message"] == "Ótimo!\nMuito  bom."
    assert cleaned.loc[1:2, "message"].isna().all()
    assert cleaned.loc[3, "message"] == "NA"
    pd.testing.assert_frame_equal(raw, snapshot)


def test_csv_loader_preserves_leading_zeros_and_literal_null_words(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("id,zip,text\n001,01037,NA\n002,00001,NULL\n003,00002,\n", encoding="utf-8")
    loaded = read_source_csv(path)
    assert loaded["id"].tolist() == ["001", "002", "003"]
    assert loaded.loc[0, "zip"] == "01037"
    assert loaded.loc[1, "text"] == "NULL"
    assert pd.isna(loaded.loc[2, "text"])


def test_financial_validation_detects_changed_rows_even_if_totals_match():
    before = pd.Series(["10.01", "20.02"])
    assert_financial_equal(before, pd.Series([Decimal("10.010"), Decimal("20.02")]))
    with pytest.raises(AssertionError, match="Monetary value changed"):
        assert_financial_equal(before, pd.Series(["20.02", "10.01"]))


def test_financial_validation_detects_missingness_changes():
    with pytest.raises(AssertionError, match="missingness changed"):
        assert_financial_equal(pd.Series([None]), pd.Series(["0"]))


def test_review_composite_key_does_not_reject_repeated_review_id():
    reviews = strings({"review_id": ["r1", "r1"], "order_id": ["o1", "o2"]})
    assert not key_result(reviews, ["review_id"])["valid"]
    assert key_result(reviews, ["review_id", "order_id"])["valid"]
    reviews.loc[1, "order_id"] = pd.NA
    assert not key_result(reviews, ["review_id", "order_id"])["valid"]


@pytest.fixture
def geographic_observations():
    rows = [("00001", -20.0, -40.0, "a", "SP")] * 10 + [
        ("00001", -23.0, -46.0, "b", "SP"),
        ("00001", -24.0, -45.0, "b", "SP"),
        ("00001", -25.0, -44.0, "b", "SP"),
        ("00002", -22.0, -43.0, "z", "RJ"),
        ("00002", -23.0, -46.0, "a", "SP"),
        ("00003", None, None, "x", "SP"),
    ]
    frame = pd.DataFrame(rows, columns=["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"])
    for column in ["geolocation_zip_code_prefix", "geolocation_city", "geolocation_state"]:
        frame[column] = frame[column].astype("string")
    for column in ["geolocation_lat", "geolocation_lng"]:
        frame[column] = frame[column].astype("Float64")
    return frame


def test_zip_lookup_is_deterministic_and_duplicate_rows_do_not_bias_mode(geographic_observations):
    geo = geographic_observations
    first = build_zip_lookup(geo, geo)
    shuffled = build_zip_lookup(geo.sample(frac=1, random_state=42), geo)
    pd.testing.assert_frame_equal(first, shuffled)
    record = first.set_index("zip_code_prefix").loc["00001"]
    assert record["geolocation_city"] == "b"
    assert record["geolocation_lat"] == -24.0
    assert record["geolocation_lng"] == -45.0
    assert record["distinct_observations"] == 4
    assert record["source_rows"] == 13


def test_zip_lookup_retains_conflicts_and_does_not_invent_coordinates(geographic_observations):
    lookup = build_zip_lookup(geographic_observations, geographic_observations).set_index("zip_code_prefix")
    assert lookup.loc["00002", "distinct_states"] == 2
    assert lookup.loc["00002", "geolocation_state"] == "RJ"
    assert pd.isna(lookup.loc["00003", "geolocation_lat"])
    assert pd.isna(lookup.loc["00003", "geolocation_lng"])


def test_coordinate_repetitions_are_separate_from_exact_duplicate_observations(geographic_observations):
    extra = geographic_observations.iloc[[0]].copy()
    extra["geolocation_city"] = "alternate"
    geo = pd.concat([geographic_observations, extra], ignore_index=True)
    row = build_zip_lookup(geo, geo).set_index("zip_code_prefix").loc["00001"]
    assert row["distinct_observations"] == 5
    assert row["distinct_coordinate_pairs"] == 4
    assert row["coordinate_repetitions_excess"] == 1


def test_zip_join_keeps_rows_and_unmatched_prefixes(geographic_observations):
    lookup = build_zip_lookup(geographic_observations, geographic_observations)
    customers = strings({"customer_zip_code_prefix": ["00001", "00001", "99999"]})
    joined = customers.merge(lookup, left_on="customer_zip_code_prefix", right_on="zip_code_prefix", how="left", validate="many_to_one")
    assert len(joined) == 3
    assert joined["geolocation_city"].isna().sum() == 1
    with pytest.raises(pd.errors.MergeError):
        customers.merge(pd.concat([lookup, lookup]), left_on="customer_zip_code_prefix", right_on="zip_code_prefix", how="left", validate="many_to_one")


@pytest.fixture
def small_raw():
    return {
        "customers": strings({"customer_id": ["c1"], "customer_unique_id": ["u1"], "customer_zip_code_prefix": ["00001"], "customer_city": ["City"], "customer_state": ["SP"]}),
        "orders": strings({"order_id": ["o1", "o2"], "customer_id": ["c1", "c1"], "order_status": ["delivered", "canceled"], "order_purchase_timestamp": ["2018-01-01 10:00:00"] * 2, "order_approved_at": [None, None], "order_delivered_carrier_date": ["bad-date", None], "order_delivered_customer_date": ["2018-01-03 10:00:00", None], "order_estimated_delivery_date": ["2018-01-05 00:00:00"] * 2}),
        "order_items": strings({"order_id": ["o1", "o1"], "order_item_id": ["1", "2"], "product_id": ["p1", "p1"], "seller_id": ["s1", "s1"], "shipping_limit_date": ["2018-01-02 10:00:00"] * 2, "price": ["10.01", "20.02"], "freight_value": ["0.00", "2.00"]}),
        "payments": strings({"order_id": ["o1", "o1"], "payment_sequential": ["1", "2"], "payment_type": ["credit_card", "voucher"], "payment_installments": ["1", "1"], "payment_value": ["10.01", "22.02"]}),
        "reviews": strings({"review_id": ["r1", "r1"], "order_id": ["o1", "o2"], "review_score": ["5", "1"], "review_comment_title": ["  ", None], "review_comment_message": ["  Ótimo!  ", None], "review_creation_date": ["2018-01-04 00:00:00"] * 2, "review_answer_timestamp": ["2018-01-04 10:00:00"] * 2}),
        "products": strings({"product_id": ["p1", "p2"], "product_category_name": [None, "UNMAPPED"], "product_name_lenght": [None, "10"], "product_description_lenght": [None, "20"], "product_photos_qty": [None, "1"], "product_weight_g": ["0", None], "product_length_cm": ["1", None], "product_height_cm": ["2", None], "product_width_cm": ["3", None]}),
        "sellers": strings({"seller_id": ["s1"], "seller_zip_code_prefix": ["00001"], "seller_city": ["City"], "seller_state": ["SP"]}),
        "category_translations": strings({"product_category_name": ["known"], "product_category_name_english": ["known_english"]}),
        "geolocation": strings({"geolocation_zip_code_prefix": ["00001"] * 2, "geolocation_lat": ["-23"] * 2, "geolocation_lng": ["-46"] * 2, "geolocation_city": ["city"] * 2, "geolocation_state": ["SP"] * 2}),
    }


def test_cleaning_preserves_raw_transactions_and_records_invalid_source_text(small_raw):
    snapshots = {name: frame.copy(deep=True) for name, frame in small_raw.items()}
    clean, actions, flags = clean_datasets(small_raw)
    for name, snapshot in snapshots.items():
        pd.testing.assert_frame_equal(small_raw[name], snapshot)
        if name != "geolocation":
            assert len(clean[name]) == len(snapshot)
    assert len(clean["geolocation"]) == 1
    assert len(clean["reviews"]) == 2
    assert clean["products"]["product_category_name"].tolist() == ["Unknown", "unmapped"]
    assert clean["products"]["product_category_name_english"].tolist() == ["Unknown", "Unknown"]
    assert clean["orders"]["order_approved_at"].isna().all()
    assert pd.isna(clean["orders"].loc[0, "order_delivered_carrier_date"])
    invalid = flags.loc[flags["rule"] == "invalid_order_delivered_carrier_date"]
    assert "bad-date" in invalid.iloc[0]["observed_values"]
    assert clean["products"].loc[0, "product_weight_g"] == 0
    assert clean["products"].loc[0, "dq_nonpositive_product_weight_g"]
    assert not actions.empty
    validate_integrity(small_raw, clean)


def test_csv_round_trip_preserves_missingness_identifiers_dates_and_money(small_raw, tmp_path):
    clean, _, _ = clean_datasets(small_raw)
    exported = export_and_verify(clean, tmp_path)
    assert len(exported) == 10
    assert exported["round_trip_validated"].all()
    assert read_source_csv(tmp_path / "customers_clean.csv").loc[0, "customer_zip_code_prefix"] == "00001"
    payments = read_source_csv(tmp_path / "payments_clean.csv")
    assert_financial_equal(small_raw["payments"]["payment_value"], payments["payment_value"])
