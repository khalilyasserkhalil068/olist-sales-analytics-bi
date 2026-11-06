"""Conservative, reproducible Phase 2 cleaning and integrity checks for Olist."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


DATASET_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translations": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}
DATE_COLUMNS = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
               "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"],
    "reviews": ["review_creation_date", "review_answer_timestamp"],
}
NUMERIC_COLUMNS = {
    "geolocation": ["geolocation_lat", "geolocation_lng"],
    "order_items": ["price", "freight_value"],
    "payments": ["payment_installments", "payment_value"],
    "reviews": ["review_score"],
    "products": ["product_name_lenght", "product_description_lenght", "product_photos_qty",
                 "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
}
PRIMARY_KEYS = {
    "customers": ["customer_id"], "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "payments": ["order_id", "payment_sequential"],
    "reviews": ["review_id", "order_id"], "products": ["product_id"],
    "sellers": ["seller_id"], "category_translations": ["product_category_name"],
    "geolocation_zip_lookup": ["zip_code_prefix"],
}
CORE_RELATIONSHIPS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("payments", "order_id", "orders", "order_id"),
    ("reviews", "order_id", "orders", "order_id"),
]
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FINANCIAL_COLUMNS = {"order_items": ["price", "freight_value"], "payments": ["payment_value"]}


def file_hash(path):
    """Hash source bytes without changing the file."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def frame_hash(frame):
    """Fingerprint DataFrame values, row order, columns and dtypes."""
    digest = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    digest.update(str(list(zip(frame.columns, map(str, frame.dtypes)))).encode("utf-8"))
    return digest.hexdigest()


def read_source_csv(path):
    """Only empty fields are null; preserve literal review text such as 'NA'."""
    return pd.read_csv(path, dtype="string", keep_default_na=False, na_values=[""], encoding="utf-8")


def load_raw_data(raw_directory):
    return {name: read_source_csv(Path(raw_directory) / filename) for name, filename in DATASET_FILES.items()}


def normalize_text(frame):
    """Return an independent copy; trim edges without changing inner text or case."""
    result = frame.copy(deep=True)
    changes = []
    for column in frame.columns:
        if not pd.api.types.is_string_dtype(frame[column].dtype):
            continue
        original = frame[column].astype("string")
        stripped = original.str.strip()
        changed = int((original.notna() & original.ne(stripped)).sum())
        blanks = int(stripped.eq("").sum())
        result[column] = stripped.mask(stripped.eq(""), pd.NA)
        changes.append((column, changed, blanks))
    return result, changes


def key_result(frame, columns):
    nulls = int(frame[columns].isna().any(axis=1).sum())
    duplicates = int(frame.duplicated(subset=columns).sum())
    return {"null_key_rows": nulls, "duplicate_keys_excess": duplicates,
            "valid": nulls == 0 and duplicates == 0}


def relationship_result(child, parent):
    nulls = child.isna()
    matches = child.isin(parent.loc[parent.notna()]) & ~nulls
    unmatched = ~nulls & ~matches
    return {"child_rows": len(child), "null_foreign_key_rows": int(nulls.sum()),
            "matched_rows": int(matches.sum()), "unmatched_rows": int(unmatched.sum()),
            "unmatched_examples": json.dumps(child.loc[unmatched].unique()[:10].tolist())}


def assert_financial_equal(before, after):
    """Compare every monetary amount exactly as decimals, without changing values."""
    assert len(before) == len(after), "Financial row count changed"
    for old, new in zip(before, after):
        if pd.isna(old) or pd.isna(new):
            assert pd.isna(old) and pd.isna(new), "Financial missingness changed"
        else:
            assert Decimal(str(old)) == Decimal(str(new)), f"Monetary value changed: {old} -> {new}"


def build_zip_lookup(geolocation, raw_geolocation):
    """Choose an observed coordinate near the median of the modal state/city pair.

    Work from exact-deduplicated observations, so repeated source rows do not
    bias the result. Ties use state, city, latitude and longitude in ascending
    order. Degree-distance to the joint median is a selection heuristic only;
    it is not a measured travel distance or a precise customer location.
    """
    zip_key = "geolocation_zip_code_prefix"
    state, city = "geolocation_state", "geolocation_city"
    lat, lng = "geolocation_lat", "geolocation_lng"
    columns = [zip_key, lat, lng, city, state]
    geo = geolocation.loc[geolocation[zip_key].notna(), columns].drop_duplicates().copy()
    pair_counts = geo.groupby([zip_key, state, city], dropna=False).size().rename("observations").reset_index()
    chosen_labels = pair_counts.sort_values(
        [zip_key, "observations", state, city], ascending=[True, False, True, True], na_position="last"
    ).drop_duplicates(zip_key)[[zip_key, state, city]]
    candidates = geo.merge(chosen_labels, on=[zip_key, state, city], how="inner", validate="many_to_one")
    valid = (candidates[lat].between(-90, 90) & candidates[lng].between(-180, 180)).fillna(False)
    candidates = candidates.loc[valid].copy()
    medians = candidates.groupby(zip_key)[[lat, lng]].transform("median")
    candidates["distance_to_median"] = ((candidates[[lat, lng]] - medians) ** 2).sum(axis=1)
    representatives = candidates.sort_values([zip_key, "distance_to_median", lat, lng]).drop_duplicates(zip_key)
    lookup = chosen_labels.merge(representatives[[zip_key, lat, lng]], on=zip_key, how="left", validate="one_to_one")
    statistics = geo.groupby(zip_key).agg(
        distinct_observations=(zip_key, "size"),
        distinct_city_labels=(city, "nunique"), distinct_states=(state, "nunique"),
    )
    coordinate_counts = geo.drop_duplicates([zip_key, lat, lng]).groupby(zip_key).size().rename("distinct_coordinate_pairs")
    statistics = statistics.join(coordinate_counts)
    statistics["coordinate_repetitions_excess"] = statistics["distinct_observations"] - statistics["distinct_coordinate_pairs"]
    source_counts = raw_geolocation[zip_key].str.strip().value_counts().rename("source_rows")
    lookup = lookup.merge(statistics, on=zip_key, how="left", validate="one_to_one")
    lookup = lookup.merge(source_counts, left_on=zip_key, right_index=True, how="left", validate="one_to_one")
    lookup = lookup.rename(columns={zip_key: "zip_code_prefix"}).sort_values("zip_code_prefix").reset_index(drop=True)
    assert key_result(lookup, ["zip_code_prefix"])["valid"]
    return lookup


def clean_datasets(raw_datasets):
    """Clean independent copies and return data, decisions and row-level flags."""
    clean = {}
    actions, flag_parts = [], []

    def log(name, action, column, count, reason, decision="changed", details=None):
        actions.append({"dataset": name, "action": action, "column": column,
                        "affected_records": int(count), "decision": decision, "reason": reason,
                        "details": json.dumps(details or {}, default=str, ensure_ascii=False)})

    def flag(name, rule, mask, columns, severity, reason):
        frame = clean[name]
        mask = mask.fillna(False).astype(bool)
        frame[f"dq_{rule}"] = mask.astype("boolean")
        count = int(mask.sum())
        log(name, rule, ", ".join(columns), count, reason, "flagged; retained")
        if not count:
            return
        keys = PRIMARY_KEYS.get(name, ["geolocation_zip_code_prefix"])
        selected = frame.loc[mask]
        records = []
        for index, row in selected.iterrows():
            records.append({
                "dataset": name, "source_record_number": int(index) + 1 if name != "geolocation_zip_lookup" else pd.NA,
                "record_key": json.dumps({key: row[key] for key in keys}, default=str, ensure_ascii=False),
                "rule": rule, "severity": severity,
                "observed_values": json.dumps({column: row[column] for column in columns}, default=str, ensure_ascii=False),
                "decision": "retained; no inferred correction", "explanation": reason,
            })
        flag_parts.append(pd.DataFrame(records))

    for name, raw in raw_datasets.items():
        frame, changes = normalize_text(raw)
        clean[name] = frame
        for column, stripped, blanks in changes:
            log(name, "strip_outer_whitespace", column, stripped, "Trim edges only; preserve inner review content and case.")
            log(name, "blank_text_to_missing", column, blanks, "Whitespace-only fields have no text content; store as missing.")

        for column in DATE_COLUMNS.get(name, []):
            source = frame[column].copy()
            converted = pd.to_datetime(source, format=DATE_FORMAT, errors="coerce")
            invalid = source.notna() & converted.isna()
            # Record original invalid text before replacing the processed column with datetime.
            flag(name, f"invalid_{column}", invalid, [column], "warning", "Unparseable source date; original text retained in flags and raw data.")
            frame[column] = converted
            log(name, "parse_datetime", column, source.notna().sum(), "Parse exact source format without imputation or timezone conversion.", details={"invalid": int(invalid.sum())})

        for column in NUMERIC_COLUMNS.get(name, []):
            source = frame[column].copy()
            converted = pd.to_numeric(source, errors="coerce").astype("Float64")
            invalid = source.notna() & converted.isna()
            flag(name, f"invalid_{column}", invalid, [column], "warning", "Non-numeric source value; original text retained in flags and raw data.")
            frame[column] = converted
            log(name, "parse_numeric", column, source.notna().sum(), "Validate numeric values without rounding, imputation or financial adjustment.", details={"invalid": int(invalid.sum())})

    for name in ["products", "category_translations"]:
        frame = clean[name]
        for column in [column for column in frame.columns if column.startswith("product_category_name")]:
            before = frame[column].copy()
            frame[column] = before.str.lower()
            log(name, "normalize_category_case", column, (before.notna() & before.ne(frame[column])).sum(), "Category lookup labels use lower case; no translations are invented.")

    products = clean["products"]
    missing_category = products["product_category_name"].isna()
    flag("products", "category_missing", missing_category, ["product_category_name"], "info", "Missing source category retained as an explicit Unknown display label.")
    translations = clean["category_translations"]
    assert key_result(translations, ["product_category_name"])["valid"], "Category mapping is not unique"
    mapping = translations.set_index("product_category_name")["product_category_name_english"]
    english = products["product_category_name"].map(mapping).astype("string")
    flag("products", "category_untranslated", ~missing_category & english.isna(), ["product_category_name"], "warning", "Source category absent from translations; retain Portuguese label and use Unknown only in English display field.")
    products["product_category_name"] = products["product_category_name"].fillna("Unknown")
    products["product_category_name_english"] = english.fillna("Unknown")
    log("products", "missing_category_label", "product_category_name", missing_category.sum(), "Unknown is a missingness label, not an inferred category.")
    log("products", "english_category_lookup", "product_category_name_english", english.notna().sum(), "Map only publisher-provided translations; missing and untranslated labels become Unknown.", details={"unknown_labels": int(english.isna().sum())})

    for name, raw in raw_datasets.items():
        frame = clean[name]
        source_columns = list(raw.columns)
        duplicate_mask = frame.duplicated(subset=source_columns)
        if name == "geolocation":
            clean[name] = frame.loc[~duplicate_mask].copy()
            decision = "removed from processed copy"
            reason = "Exact repeated geographic observations add no distinct information and would bias the ZIP representative. Raw file is preserved."
        else:
            decision = "preserved"
            reason = "Preserve all transactional and entity records; repeated order/review IDs are not a deduplication rule."
        log(name, "exact_duplicate_handling", "ALL_SOURCE_COLUMNS", duplicate_mask.sum(), reason, decision,
            {"raw_exact_duplicates": int(raw.duplicated().sum()), "processed_exact_duplicates_before_removal": int(duplicate_mask.sum())})

    clean["geolocation_zip_lookup"] = build_zip_lookup(clean["geolocation"], raw_datasets["geolocation"])
    geo = clean["geolocation"]
    zip_counts = geo["geolocation_zip_code_prefix"].value_counts()
    log("geolocation", "repeated_zip_prefix_observations", "geolocation_zip_code_prefix",
        geo["geolocation_zip_code_prefix"].duplicated(keep=False).sum(),
        "A ZIP prefix may have multiple distinct locations; preserve these observations and use the separate unique lookup for joins.",
        "investigated; retained", {"prefixes_with_multiple_observations": int(zip_counts.gt(1).sum()), "distinct_prefixes": len(zip_counts)})
    log("geolocation", "repeated_coordinate_pairs_within_zip", "geolocation_zip_code_prefix, geolocation_lat, geolocation_lng",
        geo.duplicated(subset=["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"]).sum(),
        "Same ZIP and coordinates can have different city/state labels. Count excess repetitions without deleting distinct labeled observations.",
        "investigated; retained")
    log("geolocation_zip_lookup", "representative_zip_lookup", "zip_code_prefix", len(clean["geolocation_zip_lookup"]),
        "Modal state/city pair among distinct observations; observed coordinate nearest that pair's joint median; deterministic lexical/numeric ties.")

    orders = clean["orders"]
    for child, rule, severity in [("order_items", "no_items", "warning"), ("payments", "no_payments", "warning"), ("reviews", "no_reviews", "info")]:
        flag("orders", rule, ~orders["order_id"].isin(clean[child]["order_id"]), ["order_id", "order_status"], severity, "Missing child-table coverage; preserve order and investigate status/context.")

    for column in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date"]:
        flag("orders", f"missing_{column}", orders[column].isna(), ["order_status", column], "info", "Missing milestone may depend on status; do not invent timestamps.")
        flag("orders", f"delivered_missing_{column}", orders["order_status"].eq("delivered") & orders[column].isna(), ["order_status", column], "warning", "Delivered order lacks a milestone; investigate source completeness, retain record.")

    pairs = [
        ("orders", "order_purchase_timestamp", "order_approved_at", "approval_before_purchase"),
        ("orders", "order_purchase_timestamp", "order_delivered_carrier_date", "carrier_before_purchase"),
        ("orders", "order_purchase_timestamp", "order_delivered_customer_date", "delivery_before_purchase"),
        ("orders", "order_approved_at", "order_delivered_carrier_date", "carrier_before_approval"),
        ("orders", "order_delivered_carrier_date", "order_delivered_customer_date", "delivery_before_carrier"),
        ("reviews", "review_creation_date", "review_answer_timestamp", "answer_before_creation"),
    ]
    for name, earlier, later, rule in pairs:
        frame = clean[name]
        flag(name, rule, frame[earlier].notna() & frame[later].notna() & frame[later].lt(frame[earlier]), [earlier, later], "warning", "Chronological inconsistency; keep original values pending process/source investigation.")

    purchase_by_order = orders.set_index("order_id")["order_purchase_timestamp"]
    items = clean["order_items"]
    item_purchase = items["order_id"].map(purchase_by_order)
    flag("order_items", "shipping_limit_before_purchase", items["shipping_limit_date"].lt(item_purchase), ["order_id", "shipping_limit_date"], "warning", "Shipping deadline precedes purchase timestamp; preserve values.")
    flag("order_items", "shipping_limit_after_purchase_year_range", items["shipping_limit_date"].dt.year.gt(orders["order_purchase_timestamp"].dt.year.max()), ["shipping_limit_date"], "info", "Deadline year exceeds the latest observed purchase year; investigate, not automatically invalid.")

    product_attributes = NUMERIC_COLUMNS["products"]
    flag("products", "missing_attributes", products[product_attributes].isna().any(axis=1), product_attributes, "info", "Missing physical/content attributes remain missing; no dimensional or weight imputation.")
    for column in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
        flag("products", f"nonpositive_{column}", products[column].le(0), [column], "warning", "Non-positive physical measurement retained and flagged; no replacement value is inferred.")
    for name, columns in FINANCIAL_COLUMNS.items():
        for column in columns:
            flag(name, f"negative_{column}", clean[name][column].lt(0), [column], "warning", "Negative monetary value requires investigation; do not silently change financial amounts.")
            flag(name, f"zero_{column}", clean[name][column].eq(0), [column], "info", "Zero monetary value may be legitimate; retained without adjustment.")
    flag("payments", "nonpositive_installments", clean["payments"]["payment_installments"].le(0), ["payment_installments"], "warning", "Non-positive installment count is retained for investigation.")
    for name, column in [("payments", "payment_installments"), ("reviews", "review_score")]:
        flag(name, f"noninteger_{column}", clean[name][column].mod(1).ne(0), [column], "warning", "Expected integer-valued numeric field; preserve unexpected fractional values.")
        if clean[name][column].mod(1).eq(0).fillna(True).all():
            clean[name][column] = clean[name][column].astype("Int64")
    flag("reviews", "score_out_of_range", ~clean["reviews"]["review_score"].between(1, 5), ["review_score"], "warning", "Score outside the observed source rating scale 1–5; retain for review.")
    flag("reviews", "repeated_review_id", clean["reviews"]["review_id"].duplicated(keep=False), ["review_id", "order_id"], "info", "review_id alone is not a primary key; all distinct review/order pairs are preserved.")

    lookup = clean["geolocation_zip_lookup"]
    for name, column in [("customers", "customer_zip_code_prefix"), ("sellers", "seller_zip_code_prefix")]:
        flag(name, "unmatched_zip", clean[name][column].notna() & ~clean[name][column].isin(lookup["zip_code_prefix"]), [column], "warning", "No raw geolocation observation for this prefix; retain entity without inventing a location.")
    for name in ["customers", "sellers", "geolocation"]:
        column = next(column for column in clean[name].columns if "zip_code_prefix" in column)
        flag(name, "invalid_zip_format", clean[name][column].notna() & ~clean[name][column].str.fullmatch(r"\d{5}", na=False), [column], "warning", "ZIP prefix should have five digits; preserve source text instead of guessing padding.")
    geo = clean["geolocation"]
    flag("geolocation", "invalid_coordinate", ~geo["geolocation_lat"].between(-90, 90) | ~geo["geolocation_lng"].between(-180, 180), ["geolocation_lat", "geolocation_lng"], "warning", "Check global bounds only; no Brazilian geographic boundary assumption is applied.")
    for rule, mask, columns, reason in [
        ("conflicting_city_labels", lookup["distinct_city_labels"].gt(1), ["distinct_city_labels"], "Multiple source city labels; modal pair is representative, not a verified address."),
        ("conflicting_states", lookup["distinct_states"].gt(1), ["distinct_states"], "ZIP has observations in multiple states; keep ambiguity flag."),
        ("missing_coordinate", lookup[["geolocation_lat", "geolocation_lng"]].isna().any(axis=1), ["geolocation_lat", "geolocation_lng"], "No valid observed coordinate for chosen pair; leave coordinates missing."),
    ]:
        flag("geolocation_zip_lookup", rule, mask, columns, "warning", reason)

    # Explicitly audit every source column that still has missing values.
    for name, raw in raw_datasets.items():
        for column in raw.columns:
            count = int(clean[name][column].isna().sum())
            if count:
                log(name, "missing_values_preserved", column, count, "Preserve missingness where no justified business value is available.", "preserved")
    flag_columns = ["dataset", "source_record_number", "record_key", "rule", "severity", "observed_values", "decision", "explanation"]
    flags = pd.concat(flag_parts, ignore_index=True) if flag_parts else pd.DataFrame(columns=flag_columns)
    return clean, pd.DataFrame(actions), flags


def validate_integrity(raw, clean):
    """Fail on lost transactions, invalid keys, new broken core links or changed money."""
    rows = []
    for name, before in raw.items():
        after = clean[name]
        if name == "geolocation":
            assert not after.duplicated(subset=list(before.columns)).any()
        else:
            assert len(before) == len(after), f"Unexpected row loss: {name}"
            assert before.index.equals(after.index), f"Row order changed: {name}"
        rows.append({"dataset": name, "rows_before": len(before), "rows_after": len(after), "rows_removed": len(before) - len(after)})
    rows.append({"dataset": "geolocation_zip_lookup", "rows_before": 0, "rows_after": len(clean["geolocation_zip_lookup"]), "rows_removed": 0})
    row_counts = pd.DataFrame(rows)
    key_rows = []
    for name, columns in PRIMARY_KEYS.items():
        result = key_result(clean[name], columns)
        key_rows.append({"dataset": name, "key_columns": " + ".join(columns), **result})
        assert result["valid"], f"Invalid candidate key: {name}, {columns}"
    relationship_rows = []
    for child, foreign_key, parent, primary_key in CORE_RELATIONSHIPS:
        before = relationship_result(raw[child][foreign_key], raw[parent][primary_key])
        result = relationship_result(clean[child][foreign_key], clean[parent][primary_key])
        assert result["unmatched_rows"] <= before["unmatched_rows"], f"New broken relationship: {child}.{foreign_key}"
        assert result["null_foreign_key_rows"] <= before["null_foreign_key_rows"]
        joined = clean[child][[foreign_key]].merge(
            clean[parent][[primary_key]], left_on=foreign_key, right_on=primary_key,
            how="left", validate="many_to_one",
        )
        assert len(joined) == len(clean[child]), f"Core join multiplied rows: {child}"
        relationship_rows.append({"child_dataset": child, "foreign_key": foreign_key, "parent_dataset": parent,
                                  "parent_key": primary_key, "rows_after_join": len(joined), **result})

    # Validate real many-to-one joins rather than assuming a unique ZIP lookup.
    lookup = clean["geolocation_zip_lookup"]
    for name, column in [("customers", "customer_zip_code_prefix"), ("sellers", "seller_zip_code_prefix")]:
        joined = clean[name][[column]].merge(lookup, left_on=column, right_on="zip_code_prefix", how="left", validate="many_to_one")
        assert len(joined) == len(clean[name]), "ZIP join multiplied rows"
        result = relationship_result(clean[name][column], lookup["zip_code_prefix"])
        relationship_rows.append({"child_dataset": name, "foreign_key": column, "parent_dataset": "geolocation_zip_lookup",
                                  "parent_key": "zip_code_prefix", "rows_after_join": len(joined), **result})

    products = clean["products"]
    # Unknown is a sentinel for missing source data, not a new translation row.
    category_source = products["product_category_name"].mask(products["dq_category_missing"], pd.NA)
    result = relationship_result(category_source, clean["category_translations"]["product_category_name"])
    assert result["unmatched_rows"] == int(products["dq_category_untranslated"].sum())
    joined = category_source.to_frame().merge(clean["category_translations"], on="product_category_name", how="left", validate="many_to_one")
    assert len(joined) == len(products)
    relationship_rows.append({"child_dataset": "products", "foreign_key": "product_category_name", "parent_dataset": "category_translations",
                              "parent_key": "product_category_name", "rows_after_join": len(joined), **result})
    finance_rows = []
    for name, columns in FINANCIAL_COLUMNS.items():
        for column in columns:
            assert_financial_equal(raw[name][column], clean[name][column])
            finance_rows.append({"dataset": name, "column": column, "rows_checked": len(raw[name]), "exact_decimal_equality": True})
    for name, frame in clean.items():
        for column in frame.columns:
            if not column.startswith("dq_") and (column.endswith("_id") or "zip_code_prefix" in column or column == "payment_sequential"):
                assert isinstance(frame[column].dtype, pd.StringDtype), f"Identifier is not string: {name}.{column}"
    return row_counts, pd.DataFrame(key_rows), pd.DataFrame(relationship_rows), pd.DataFrame(finance_rows)


def missing_before_after(raw, clean):
    """Compare source columns only; source and processed denominators are explicit."""
    rows = []
    for name, before in raw.items():
        after = clean[name]
        for column in before.columns:
            before_count, after_count = int(before[column].isna().sum()), int(after[column].isna().sum())
            rows.append({"dataset": name, "column": column, "rows_before": len(before), "rows_after": len(after),
                         "dtype_before": str(before[column].dtype), "dtype_after": str(after[column].dtype),
                         "missing_before": before_count, "missing_after": after_count,
                         "missing_change": after_count - before_count,
                         "missing_percentage_before": 100 * before_count / len(before),
                         "missing_percentage_after": 100 * after_count / len(after),
                         "unknown_labels_after": int(after[column].eq("Unknown").sum()) if pd.api.types.is_string_dtype(after[column].dtype) else 0})
    return pd.DataFrame(rows)


def add_validation_actions(actions, row_counts, keys, relationships, financial):
    """Keep keys, FK coverage, join sizes and financial checks in the requested audit CSV."""
    extra = []
    for table, action in [(row_counts, "row_count_validation"), (keys, "primary_key_validation"),
                          (relationships, "relationship_validation"), (financial, "financial_value_validation")]:
        for record in table.to_dict("records"):
            extra.append({"dataset": record.get("dataset", record.get("child_dataset")), "action": action,
                          "column": record.get("key_columns", record.get("foreign_key", record.get("column", "ALL_ROWS"))),
                          "affected_records": record.get("rows_after", record.get("rows_checked", record.get("unmatched_rows", 0))),
                          "decision": "validated", "reason": "See structured details for measured validation results.",
                          "details": json.dumps(record, default=str, ensure_ascii=False)})
    return pd.concat([actions, pd.DataFrame(extra)], ignore_index=True)


def export_and_verify(clean, processed_directory):
    """Write ten UTF-8 CSVs; read back values, types, rows and exact monetary amounts."""
    directory = Path(processed_directory)
    directory.mkdir(parents=True, exist_ok=True)
    export_rows = []
    for name, frame in clean.items():
        filename = f"{name}_clean.csv" if name != "geolocation_zip_lookup" else "geolocation_zip_lookup.csv"
        path = directory / filename
        frame.to_csv(path, index=False, encoding="utf-8", date_format=DATE_FORMAT, lineterminator="\n")
        exported = read_source_csv(path)
        assert list(exported.columns) == list(frame.columns)
        assert len(exported) == len(frame), f"Export row mismatch: {name}"
        for column in FINANCIAL_COLUMNS.get(name, []):
            assert_financial_equal(frame[column], exported[column])
        # CSV has no type metadata; reload using the verified in-memory schema.
        for column, dtype in frame.dtypes.items():
            if pd.api.types.is_datetime64_any_dtype(dtype):
                exported[column] = pd.to_datetime(exported[column], format=DATE_FORMAT, errors="raise")
            elif pd.api.types.is_bool_dtype(dtype):
                exported[column] = exported[column].map({"True": True, "False": False}).astype(dtype)
            elif pd.api.types.is_numeric_dtype(dtype):
                exported[column] = pd.to_numeric(exported[column], errors="raise").astype(dtype)
            else:
                exported[column] = exported[column].astype(dtype)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), exported, check_exact=False, rtol=1e-12, atol=1e-12)
        export_rows.append({"dataset": name, "filename": filename, "rows": len(frame), "columns": frame.shape[1],
                            "bytes": path.stat().st_size, "sha256": file_hash(path), "round_trip_validated": True})
    return pd.DataFrame(export_rows)


def markdown_table(frame):
    """Small dependency-free Markdown tables for generated reports."""
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(escape, frame.columns)) + " |",
             "| " + " | ".join(["---"] * len(frame.columns)) + " |"]
    lines += ["| " + " | ".join(map(escape, row)) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join(lines)
