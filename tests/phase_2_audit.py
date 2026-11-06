"""Independent read-only audit. Existing cleaning helpers are not audit oracles.

The existing implementation is imported only in the explicitly labelled
reproducibility control. All expected values, keys, flags and ZIP statistics
are computed independently from the CSVs first. Reports are written exclusively
to new files, only when requested by the separate pytest suite.
"""
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import gc
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import sys

import numpy as np
import pandas as pd
import nbformat

RAW_FILES = {
    "customers": "olist_customers_dataset.csv", "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv", "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv", "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv", "category_translations": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}
KEYS = {
    "customers": ["customer_id"], "orders": ["order_id"], "order_items": ["order_id", "order_item_id"],
    "payments": ["order_id", "payment_sequential"], "reviews": ["review_id", "order_id"],
    "products": ["product_id"], "sellers": ["seller_id"], "category_translations": ["product_category_name"],
    "geolocation_zip_lookup": ["zip_code_prefix"],
}
DATES = {
    "orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
    "order_items": ["shipping_limit_date"], "reviews": ["review_creation_date", "review_answer_timestamp"],
}
NUMBERS = {
    "order_items": ["price", "freight_value"], "payments": ["payment_installments", "payment_value"],
    "reviews": ["review_score"], "products": ["product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
    "geolocation": ["geolocation_lat", "geolocation_lng"],
}
LINKS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("payments", "order_id", "orders", "order_id"),
    ("reviews", "order_id", "orders", "order_id"),
    ("products", "product_category_name", "category_translations", "product_category_name"),
    ("customers", "customer_zip_code_prefix", "geolocation_zip_lookup", "zip_code_prefix"),
    ("sellers", "seller_zip_code_prefix", "geolocation_zip_lookup", "zip_code_prefix"),
]
GROUPS = ["preservation", "transformation", "missing_values", "duplicates_keys", "financial", "timestamps",
          "relationships", "geolocation", "business_rules", "quality_flags", "report_accuracy", "reproducibility", "limits"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path):
    return pd.read_csv(path, dtype="string", keep_default_na=False, na_values=[""], encoding="utf-8")


def trimmed(series):
    result = series.str.strip()
    return result.mask(result.eq(""), pd.NA)


def equal_text(left, right):
    return left.fillna("\0NULL\0").eq(right.fillna("\0NULL\0"))


def decimal_value(value):
    return None if pd.isna(value) else Decimal(str(value))


def key_tuples(frame, columns):
    return list(frame[columns].itertuples(index=False, name=None))


def table_md(frame):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    rows = ["| " + " | ".join(map(escape, frame.columns)) + " |", "| " + " | ".join(["---"] * len(frame.columns)) + " |"]
    rows += ["| " + " | ".join(map(escape, values)) + " |" for values in frame.itertuples(index=False, name=None)]
    return "\n".join(rows)


class IndependentAudit:
    def __init__(self, root):
        self.root = Path(root)
        self.results, self.inventory, self.financial, self.row_counts = [], [], [], []
        self.expected_flags = {}
        self.protected = self.snapshot()
        self.raw = {name: read_csv(self.root / "data/raw" / filename) for name, filename in RAW_FILES.items()}
        self.processed = {name: read_csv(self.root / "data/processed" / f"{name}_clean.csv") for name in RAW_FILES}
        self.processed["geolocation_zip_lookup"] = read_csv(self.root / "data/processed/geolocation_zip_lookup.csv")
        self.actions = pd.read_csv(self.root / "reports/cleaning_summary.csv", keep_default_na=False)
        self.missing_report = pd.read_csv(self.root / "reports/missing_values_before_after.csv", keep_default_na=False)
        self.flag_report = read_csv(self.root / "reports/data_quality_flags.csv")
        self.summaries = {phase: (self.root / "docs/data_quality.md").read_text(encoding="utf-8") for phase in [1, 2]}
        self.notebooks = {phase: nbformat.read(self.root / f"notebooks/0{phase}_{'data_understanding' if phase == 1 else 'data_cleaning'}.ipynb", as_version=4) for phase in [1, 2]}
        # Read existing implementation/tests as evidence without executing them.
        self.implementation_text = (self.root / "src/data_processing/cleaning.py").read_text(encoding="utf-8")
        self.original_tests = (self.root / "tests/test_cleaning.py").read_text(encoding="utf-8")
        self.base = {name: frame.apply(trimmed) for name, frame in self.raw.items()}
        for name in ["products", "category_translations"]:
            for column in self.base[name]:
                if column.startswith("product_category_name"):
                    self.base[name][column] = self.base[name][column].str.lower()
        self.parsed_dates = {}
        for name, columns in DATES.items():
            for column in columns:
                self.parsed_dates[(name, column)] = pd.to_datetime(self.base[name][column], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        for name, columns in NUMBERS.items():
            for column in columns:
                self.base[name][column] = pd.to_numeric(self.base[name][column], errors="coerce")
        self.geo = self.base["geolocation"].drop_duplicates().copy()
        self.base["geolocation"] = self.geo
        self.lookup_expected = None

    def snapshot(self):
        paths = [p for folder in ["data/raw", "data/processed", "notebooks", "src", "tests", "reports"]
                 for p in (self.root / folder).rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and "audit" not in p.relative_to(self.root).parts]
        paths += [self.root / name for name in ["README.md", "docs/architecture.md", "requirements.txt", ".gitignore", "data/DATASET_MANIFEST.json"]]
        return {str(path.relative_to(self.root)): sha(path) for path in paths}

    def add(self, group, name, dataset, expected, actual, affected=0, ok=True, status=None,
            severity=None, evidence=None, correction="None required."):
        status = status or ("PASS" if ok else "FAIL")
        self.results.append({"test_name": name, "category": group, "dataset": dataset, "status": status,
                             "expected_behavior": expected, "actual_behavior": actual, "affected_records": int(affected),
                             "severity": severity or ("none" if status == "PASS" else "high" if status == "FAIL" else "medium" if status == "WARN" else "limitation"),
                             "evidence": json.dumps(evidence or {}, default=str, ensure_ascii=False),
                             "recommended_correction": correction})

    def aligned(self, name):
        if name == "geolocation":
            # No natural PK exists: compare complete normalized observation signatures.
            columns = list(self.raw[name].columns)
            source = self.raw[name].loc[self.geo.index].copy()
            source.index = pd.MultiIndex.from_frame(self.geo[columns])
            actual = self.processed[name].copy()
            for column in NUMBERS[name]:
                actual[column] = pd.to_numeric(actual[column], errors="coerce")
            actual.index = pd.MultiIndex.from_frame(actual[columns])
        else:
            columns = KEYS[name]
            source = self.raw[name].copy()
            source.index = pd.MultiIndex.from_frame(self.base[name][columns])
            actual = self.processed[name].copy()
            actual.index = pd.MultiIndex.from_frame(actual[columns])
        if not source.index.is_unique or not actual.index.is_unique:
            raise AssertionError(f"Cannot independently align ambiguous keys: {name}")
        missing, extra = source.index.difference(actual.index), actual.index.difference(source.index)
        self.add("transformation", f"business_key_alignment_{name}", name,
                 "Every retained source business key/full geographic observation is preserved exactly once.",
                 f"Missing keys={len(missing)}; unexpected keys={len(extra)}.", len(missing) + len(extra),
                 ok=not len(missing) and not len(extra), evidence={"key_columns": columns, "missing_examples": missing[:5].tolist(), "extra_examples": extra[:5].tolist()})
        common = source.index.intersection(actual.index, sort=False)
        return source.loc[common], actual.loc[common]

    def transformations(self):
        for name, raw in self.raw.items():
            source, actual = self.aligned(name)
            missing_columns = set(raw.columns) - set(actual.columns)
            self.add("transformation", f"source_columns_preserved_{name}", name,
                     "Every original source column remains in processed data.", f"Missing columns: {sorted(missing_columns)}.", len(missing_columns), ok=not missing_columns,
                     evidence={"raw_columns": len(raw.columns), "processed_columns": len(actual.columns)})
            expected_rows = len(self.geo) if name == "geolocation" else len(raw)
            self.row_counts.append({"dataset": name, "raw_rows": len(raw), "expected_rows": expected_rows, "actual_rows": len(self.processed[name]),
                                    "raw_columns": raw.shape[1], "processed_columns": self.processed[name].shape[1]})
            self.add("transformation", f"row_reconciliation_{name}", name,
                     f"{expected_rows:,} rows; only exact geographic duplicates may be removed.",
                     f"{len(self.processed[name]):,} rows; difference={len(self.processed[name]) - expected_rows}.",
                     abs(len(self.processed[name]) - expected_rows), ok=len(self.processed[name]) == expected_rows)
            for column in raw.columns:
                old, new = source[column], actual[column]
                expected = trimmed(old)
                rule, justification = "Trim outer whitespace; empty text becomes missing.", "Consistent optional text without changing meaning or inner formatting."
                expected_type = "string"
                affected = int((~equal_text(old, expected)).sum())
                if column.startswith("product_category_name"):
                    expected = expected.str.lower()
                    rule += " Normalize category case."
                    if name == "products":
                        expected = expected.fillna("Unknown")
                        rule += " Fill missing category only with Unknown sentinel."
                    justification = "Join-label consistency; preserve genuine labels and expose missingness."
                if column in NUMBERS.get(name, []):
                    expected_type = "numeric; integer-valued score/installments where applicable"
                    rule = "Explicit numeric parsing; no business-value rounding or imputation."
                    justification = "Usable numeric types with preserved original values."
                    affected = int(old.notna().sum())
                    if name == "geolocation":
                        x = pd.to_numeric(expected, errors="coerce")
                        y = pd.to_numeric(new, errors="coerce")
                        matches = x.eq(y) | (x.isna() & y.isna())
                    else:
                        matches = pd.Series([decimal_value(x) == decimal_value(y) for x, y in zip(expected, new)], index=source.index)
                else:
                    matches = equal_text(expected, new)
                if column in DATES.get(name, []):
                    expected_type = "timezone-naive datetime, serialized YYYY-MM-DD HH:MM:SS"
                    rule = "Parse fixed-format timestamps without shifting, inventing or dropping values."
                    justification = "Explicit date types; absent business events remain absent."
                    affected = int(old.notna().sum())
                failures = int((~matches.fillna(False)).sum())
                test_name = f"transform_{name}_{column}"
                self.add("transformation", test_name, name, rule, f"{len(source):,} keyed comparisons; {failures} unexpected value/null changes.", failures,
                         ok=failures == 0, evidence={"column": column, "affected_by_documented_rule": affected, "business_key_comparison": True,
                                                  "examples": source.loc[~matches.fillna(False), [column]].head(5).to_dict("records")}, correction="Restore source values outside documented transformations." if failures else "None required.")
                self.inventory.append({"dataset": name, "column": column, "original_value_or_dtype": f"CSV text; example {str(old.loc[old.notna()].iloc[0])[:70]!r}" if old.notna().any() else "CSV text; all missing",
                                       "transformation_rule": rule, "expected_output": expected_type, "affected_records": affected,
                                       "business_justification": justification, "independent_validation": "PASS" if failures == 0 else "FAIL"})
        translations = self.base["category_translations"].set_index("product_category_name")["product_category_name_english"]
        mapped = self.base["products"]["product_category_name"].map(translations).fillna("Unknown")
        actual = self.processed["products"].set_index("product_id")["product_category_name_english"].reindex(self.base["products"]["product_id"])
        failures = int((~equal_text(mapped.reset_index(drop=True), actual.reset_index(drop=True))).sum())
        self.add("transformation", "english_category_mapping", "products", "Use supplied translations; Unknown for missing/unmapped source categories.",
                 f"{failures} mismatches; {int(mapped.eq('Unknown').sum())} Unknown English labels.", failures, ok=failures == 0)
        self.inventory.append({"dataset": "products", "column": "product_category_name_english", "original_value_or_dtype": "New derived field",
                               "transformation_rule": "Map the publisher translation dictionary; use Unknown sentinel only for absent mappings.", "expected_output": "string",
                               "affected_records": len(mapped), "business_justification": "Display known English labels without invented translations.", "independent_validation": "PASS" if not failures else "FAIL"})

    def missing_values(self):
        wrong = []
        for name, raw in self.raw.items():
            output = self.processed[name]
            for column in raw:
                before, after = int(raw[column].isna().sum()), int(output[column].isna().sum())
                record = self.missing_report.loc[(self.missing_report["dataset"] == name) & (self.missing_report["column"] == column)]
                ok = len(record) == 1
                if ok:
                    r = record.iloc[0]
                    ok = (int(r["missing_before"]) == before and int(r["missing_after"]) == after
                          and int(r["missing_change"]) == after - before and int(r["rows_before"]) == len(raw)
                          and int(r["rows_after"]) == len(output)
                          and math.isclose(float(r["missing_percentage_before"]), 100 * before / len(raw), abs_tol=1e-10)
                          and math.isclose(float(r["missing_percentage_after"]), 100 * after / len(output), abs_tol=1e-10)
                          and int(r["unknown_labels_after"]) == int(output[column].eq("Unknown").sum()))
                if not ok:
                    wrong.append(f"{name}.{column}")
        self.add("missing_values", "missing_report_all_columns", "all", "Exact counts and percentages for all 52 source columns.",
                 f"{len(wrong)} incorrect entries; {len(self.missing_report)} entries total.", len(wrong), ok=not wrong and len(self.missing_report) == 52, evidence={"mismatches": wrong})
        for column in ["review_comment_title", "review_comment_message"]:
            raw = self.raw["reviews"].set_index(["review_id", "order_id"])[column]
            out = self.processed["reviews"].set_index(["review_id", "order_id"])[column].reindex(raw.index)
            blanks = raw.notna() & raw.str.fullmatch(r"\s*", na=False)
            wrong = int((blanks & out.notna()).sum())
            self.add("missing_values", f"review_blank_conversion_{column}", "reviews", "Convert precisely the whitespace-only fields to missing; preserve all other content except edge trim.",
                     f"{int(blanks.sum())} whitespace-only fields; {wrong} not converted.", wrong, ok=wrong == 0,
                     evidence={"before_missing": int(raw.isna().sum()), "after_missing": int(out.isna().sum()), "blank_fields": int(blanks.sum())})
        p = self.raw["products"].set_index("product_id")["product_category_name"]
        c = self.processed["products"].set_index("product_id")["product_category_name"].reindex(p.index)
        genuine = trimmed(p).notna()
        overwritten = int((genuine & ~equal_text(trimmed(p).str.lower(), c)).sum())
        correct_unknown = int((~genuine & c.eq("Unknown")).sum())
        self.add("missing_values", "unknown_category_scope", "products", "Only the 610 missing categories become Unknown; no genuine label overwritten.",
                 f"Unknown for {correct_unknown} missing categories; overwritten genuine labels={overwritten}.", overwritten,
                 ok=overwritten == 0 and correct_unknown == int((~genuine).sum()) == 610)

    def duplicates_and_keys(self):
        for name, raw in self.raw.items():
            out = self.processed[name]
            before, after = int(raw.duplicated().sum()), int(out.duplicated(list(raw.columns)).sum())
            expected = 0 if name == "geolocation" else before
            self.add("duplicates_keys", f"exact_duplicates_{name}", name, f"Preserve source information; expected processed excess duplicates={expected}.",
                     f"Raw excess={before}; processed excess={after}.", abs(after - expected), ok=after == expected,
                     evidence={"raw_excess": before, "processed_excess": after, "removed_rows": len(raw) - len(out)})
            self.inventory.append({"dataset": name, "column": "ALL_SOURCE_COLUMNS / row policy", "original_value_or_dtype": f"{len(raw):,} source rows; {before:,} excess exact duplicates",
                                   "transformation_rule": "Remove exact geographic duplicate observations only." if name == "geolocation" else "Preserve every source entity/transaction row, including repeated IDs at legitimate detail grains.",
                                   "expected_output": f"{len(self.geo) if name == 'geolocation' else len(raw):,} processed rows", "affected_records": before if name == "geolocation" else 0,
                                   "business_justification": "Identical geographic observations need not bias the representative; transactional repetition is not an error.",
                                   "independent_validation": "PASS" if after == expected else "FAIL"})
        for name, columns in KEYS.items():
            frame = self.processed[name]
            nulls, duplicates = int(frame[columns].isna().any(axis=1).sum()), int(frame.duplicated(columns).sum())
            self.add("duplicates_keys", f"primary_key_{name}", name, "Unique non-null key at the documented grain.", f"Nulls={nulls}; excess duplicates={duplicates}.", nulls + duplicates,
                     ok=nulls == duplicates == 0, evidence={"key": columns})
        for name, column in [("order_items", "order_id"), ("payments", "order_id"), ("reviews", "review_id"), ("customers", "customer_unique_id")]:
            source = self.raw[name][column].value_counts()
            out = self.processed[name][column].value_counts()
            mismatch = int(source.subtract(out, fill_value=0).ne(0).sum())
            self.add("duplicates_keys", f"legitimate_repetition_{name}", name, "Keep every occurrence of intentionally repeated identifiers.",
                     f"{int(source.gt(1).sum())} repeated values; {mismatch} changed multiplicities.", mismatch, ok=mismatch == 0,
                     evidence={"column": column, "excess_repetitions": int((source - 1).sum())})

    def money(self):
        for name, columns in [("order_items", ["price", "freight_value"]), ("payments", ["payment_value"])]:
            columns_key = KEYS[name]
            raw = self.raw[name].set_index(columns_key)
            clean = self.processed[name].set_index(columns_key).reindex(raw.index)
            for column in columns:
                before, after = raw[column].map(decimal_value), clean[column].map(decimal_value)
                failures = sum(a != b for a, b in zip(before, after))
                old_total = sum((x for x in before if x is not None), Decimal(0))
                new_total = sum((x for x in after if x is not None), Decimal(0))
                negative = sum(x is not None and x < 0 for x in before)
                zero = sum(x is not None and x == 0 for x in before)
                self.add("financial", f"money_{name}_{column}", name, "Every keyed monetary value and exact Decimal total must be unchanged; no rounding or invalid conversion.",
                         f"Mismatches={failures}; exact totals {old_total} -> {new_total}; negatives={negative}; zero values={zero}.", failures,
                         ok=failures == 0 and old_total == new_total, severity="critical" if failures or old_total != new_total else "none",
                         evidence={"key": columns_key, "rows_checked": len(raw), "before_total": str(old_total), "after_total": str(new_total), "negative_count": negative, "zero_count": zero})
                self.financial.append({"dataset": name, "column": column, "records": len(raw), "raw_total": str(old_total), "processed_total": str(new_total), "mismatches": failures})

    def timestamps(self):
        for name, columns in DATES.items():
            source = self.raw[name].set_index(KEYS[name])
            actual = self.processed[name].set_index(KEYS[name]).reindex(source.index)
            for column in columns:
                invalid = []
                for value in source[column].loc[source[column].notna()].unique():
                    try:
                        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
                            raise ValueError("Format mismatch")
                        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        invalid.append(value)
                mismatch = int((~equal_text(trimmed(source[column]), actual[column])).sum())
                self.add("timestamps", f"timestamp_{name}_{column}", name, "Valid timestamps remain exactly the same by business key; missing values remain missing; no timezone shift.",
                         f"Invalid source strings={len(invalid)}; changed/invented/lost timestamps={mismatch}.", mismatch,
                         ok=mismatch == 0 and not invalid, evidence={"invalid_examples": invalid[:5], "missing_before": int(source[column].isna().sum()), "missing_after": int(actual[column].isna().sum())})
        orders = self.base["orders"]
        delivered, estimated = self.parsed_dates[("orders", "order_delivered_customer_date")], self.parsed_dates[("orders", "order_estimated_delivery_date")]
        late_timestamp = int(delivered.gt(estimated).sum())
        late_day = int(delivered.dt.normalize().gt(estimated.dt.normalize()).sum())
        self.add("timestamps", "delivery_after_estimate", "orders", "Preserve late deliveries as source performance outcomes, not cleaning defects; distinguish time from calendar-day comparisons.",
                 f"After estimated timestamp={late_timestamp}; after estimated calendar day={late_day}. Existing cleaning has no late-delivery flag.", late_day,
                 status="WARN" if late_day else "PASS", severity="low", evidence={"after_timestamp": late_timestamp, "after_calendar_day": late_day},
                 correction="Define the delivery-lateness convention before EDA; report denominators and preserve these orders.")

    def relationships(self):
        for child, fk, parent, pk in LINKS:
            source = self.base[child][fk]
            parent_keys = self.base[parent][pk] if parent in self.base else self.lookup_expected[pk]
            null = source.isna()
            unmatched = ~null & ~source.isin(parent_keys)
            actual_source = self.processed[child][fk]
            if child == "products":
                missing_ids = self.base["products"].loc[null, "product_id"]
                actual_source = actual_source.mask(self.processed[child]["product_id"].isin(missing_ids))
            actual_unmatched = actual_source.notna() & ~actual_source.isin(self.processed[parent][pk])
            same_records = set(self.base[child].loc[unmatched, fk]) == set(actual_source.loc[actual_unmatched])
            joined = self.processed[child][[fk]].merge(self.processed[parent][[pk]], left_on=fk, right_on=pk, how="left", validate="many_to_one")
            multiplied = len(joined) - len(self.processed[child])
            ok = same_records and int(actual_unmatched.sum()) == int(unmatched.sum()) and multiplied == 0
            self.add("relationships", f"foreign_key_{child}_{fk}", child, "No new orphans; preserve known optional/missing relationships and child-row counts in many-to-one joins.",
                     f"Null source keys={int(null.sum())}; unmatched source rows={int(unmatched.sum())}; processed unmatched={int(actual_unmatched.sum())}; multiplied rows={multiplied}.",
                     abs(int(actual_unmatched.sum()) - int(unmatched.sum())) + abs(multiplied), ok=ok,
                     evidence={"parent": parent, "parent_key": pk, "child_rows": len(source), "joined_rows": len(joined), "null_source_keys": int(null.sum()), "unmatched_source": int(unmatched.sum()), "unmatched_processed": int(actual_unmatched.sum()),
                               "maximum_children_per_key": int(source.value_counts().max()), "unmatched_examples": source.loc[unmatched].unique()[:5].tolist()})
            if unmatched.any():
                self.add("relationships", f"source_coverage_{child}_{fk}", child, "Source coverage gaps remain visible and do not justify fabricated parents or entity deletion.",
                         f"{int(unmatched.sum())} rows lack a source parent; records are retained.", int(unmatched.sum()), status="WARN", severity="low",
                         evidence={"parent": parent}, correction="Use missing/unknown groups and coverage disclosures in EDA; do not invent matches.")
        customers = self.raw["customers"]
        orders = self.raw["orders"]
        correct = set(orders["customer_id"]) <= set(customers["customer_id"])
        self.add("relationships", "customer_identity_semantics", "customers", "Join orders via customer_id; customer_unique_id may repeat across order-linked customer records.",
                 f"Customer records={len(customers)}; customer_id distinct={customers['customer_id'].nunique()}; customer_unique_id distinct={customers['customer_unique_id'].nunique()}.",
                 ok=correct and customers["customer_id"].is_unique and not customers["customer_unique_id"].is_unique,
                 evidence={"join_column_in_cleaner": "orders.customer_id -> customers.customer_id", "maximum_records_per_identity": int(customers["customer_unique_id"].value_counts().max())})

    def independent_lookup(self):
        # Independent per-prefix Counter/median implementation, not the cleaner's groupby pipeline.
        geo = self.geo
        z, state, city = "geolocation_zip_code_prefix", "geolocation_state", "geolocation_city"
        lat, lon = "geolocation_lat", "geolocation_lng"
        source_counts = self.raw["geolocation"][z].str.strip().value_counts().to_dict()
        rows = []
        for prefix, group in geo.groupby(z, sort=True):
            pairs = Counter(zip(group[state], group[city]))
            chosen = min(pairs, key=lambda pair: (-pairs[pair], pair[0], pair[1]))
            observations = [(float(x), float(y)) for s, c, x, y in group[[state, city, lat, lon]].itertuples(index=False, name=None)
                            if (s, c) == chosen and pd.notna(x) and pd.notna(y) and -90 <= x <= 90 and -180 <= y <= 180]
            if observations:
                median_x = statistics.median(point[0] for point in observations)
                median_y = statistics.median(point[1] for point in observations)
                chosen_point = min(observations, key=lambda point: ((point[0] - median_x) ** 2 + (point[1] - median_y) ** 2, point[0], point[1]))
            else:
                chosen_point = (np.nan, np.nan)
            coordinate_pairs = len(set(zip(group[lat], group[lon])))
            rows.append({"zip_code_prefix": prefix, state: chosen[0], city: chosen[1], lat: chosen_point[0], lon: chosen_point[1],
                         "distinct_observations": len(group), "distinct_city_labels": group[city].nunique(), "distinct_states": group[state].nunique(),
                         "distinct_coordinate_pairs": coordinate_pairs, "coordinate_repetitions_excess": len(group) - coordinate_pairs,
                         "source_rows": source_counts[prefix]})
        self.lookup_expected = pd.DataFrame(rows)
        self.base["geolocation_zip_lookup"] = self.lookup_expected
        actual = self.processed["geolocation_zip_lookup"].set_index("zip_code_prefix")
        expected = self.lookup_expected.set_index("zip_code_prefix")
        key_difference = len(expected.index.difference(actual.index)) + len(actual.index.difference(expected.index))
        self.add("geolocation", "zip_coverage_and_key", "geolocation_zip_lookup", "Exactly one non-null row for every source ZIP prefix.",
                 f"Expected={len(expected)}; actual={len(actual)}; key differences={key_difference}; duplicates={int(actual.index.duplicated().sum())}.",
                 key_difference, ok=key_difference == 0 and actual.index.is_unique and actual.index.notna().all())
        self.inventory.append({"dataset": "geolocation_zip_lookup", "column": "zip_code_prefix", "original_value_or_dtype": "Repeated source ZIP strings, preserving leading zeros",
                               "transformation_rule": "Create one derived row per distinct non-null source ZIP prefix.", "expected_output": "Unique non-null string key",
                               "affected_records": len(expected), "business_justification": "Support many-to-one geographic joins without row multiplication.",
                               "independent_validation": "PASS" if key_difference == 0 and actual.index.is_unique else "FAIL"})
        actual = actual.reindex(expected.index)
        for column in expected:
            if column in [state, city]:
                matches = equal_text(expected[column].astype("string"), actual[column])
            else:
                # Standard CSV float64 precision is acceptable for approximate coordinates;
                # financial fields are audited separately with exact Decimal equality.
                matches = pd.Series(np.isclose(pd.to_numeric(actual[column]).to_numpy(dtype=float), expected[column].to_numpy(dtype=float), rtol=0, atol=1e-12, equal_nan=True), index=expected.index)
            count = int((~matches).sum())
            self.add("geolocation", f"lookup_field_{column}", "geolocation_zip_lookup", "Recompute modal labels, nearest-median observed coordinate and source statistics independently.",
                     f"{count} mismatched prefixes across {len(expected):,}.", count, ok=count == 0,
                     evidence={"column": column, "coordinate_absolute_tolerance_degrees": 1e-12 if column in [lat, lon] else 0,
                               "examples": expected.loc[~matches].head(5).reset_index().to_dict("records")})
            self.inventory.append({"dataset": "geolocation_zip_lookup", "column": column, "original_value_or_dtype": "Derived from immutable source observations",
                                   "transformation_rule": "Modal state/city pair; observed point nearest joint median; distinct/source observation statistics.",
                                   "expected_output": "string label, numeric coordinate or integer count as named", "affected_records": len(expected),
                                   "business_justification": "A unique, traceable ZIP representative avoids row multiplication.", "independent_validation": "PASS" if not count else "FAIL"})
        valid_range = pd.to_numeric(actual[lat]).between(-90, 90) & pd.to_numeric(actual[lon]).between(-180, 180)
        self.add("geolocation", "coordinate_ranges", "geolocation_zip_lookup", "Representative coordinates fall within global geographic bounds.", f"Invalid representatives={int((~valid_range).sum())}.", int((~valid_range).sum()), ok=valid_range.all())
        conflicts_city, conflicts_state = int(expected["distinct_city_labels"].gt(1).sum()), int(expected["distinct_states"].gt(1).sum())
        self.add("geolocation", "geographic_ambiguity", "geolocation_zip_lookup", "Preserve ambiguous source labels and explicitly document the representative heuristic.",
                 f"Multiple city labels={conflicts_city}; multiple states={conflicts_state}.", conflicts_city, status="WARN", severity="medium",
                 evidence={"ambiguous_state_prefixes": expected.loc[expected["distinct_states"].gt(1)].reset_index().to_dict("records")},
                 correction="Treat coordinates as approximate; inspect flagged prefixes for geographic analyses and disclose ambiguity.")

    def make_flag_conditions(self):
        def put(name, rule, mask):
            self.expected_flags[(name, rule)] = mask.fillna(False).astype(bool)
        for name in RAW_FILES:
            for column in DATES.get(name, []):
                put(name, f"invalid_{column}", trimmed(self.raw[name][column]).notna() & self.parsed_dates[(name, column)].isna())
            for column in NUMBERS.get(name, []):
                values = self.base[name][column]
                original = trimmed(self.raw[name].loc[self.base[name].index, column])
                put(name, f"invalid_{column}", original.notna() & values.isna())
        products, orders = self.base["products"], self.base["orders"]
        category = products["product_category_name"]
        put("products", "category_missing", category.isna())
        put("products", "category_untranslated", category.notna() & ~category.isin(self.base["category_translations"]["product_category_name"]))
        for child, rule in [("order_items", "no_items"), ("payments", "no_payments"), ("reviews", "no_reviews")]:
            put("orders", rule, ~orders["order_id"].isin(self.base[child]["order_id"]))
        for column in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date"]:
            missing = self.parsed_dates[("orders", column)].isna()
            put("orders", f"missing_{column}", missing)
            put("orders", f"delivered_missing_{column}", orders["order_status"].eq("delivered") & missing)
        pairs = [
            ("orders", "order_purchase_timestamp", "order_approved_at", "approval_before_purchase"),
            ("orders", "order_purchase_timestamp", "order_delivered_carrier_date", "carrier_before_purchase"),
            ("orders", "order_purchase_timestamp", "order_delivered_customer_date", "delivery_before_purchase"),
            ("orders", "order_approved_at", "order_delivered_carrier_date", "carrier_before_approval"),
            ("orders", "order_delivered_carrier_date", "order_delivered_customer_date", "delivery_before_carrier"),
            ("reviews", "review_creation_date", "review_answer_timestamp", "answer_before_creation"),
        ]
        for name, first, second, rule in pairs:
            earlier, later = self.parsed_dates[(name, first)], self.parsed_dates[(name, second)]
            put(name, rule, earlier.notna() & later.notna() & later.lt(earlier))
        purchases = pd.Series(self.parsed_dates[("orders", "order_purchase_timestamp")].to_numpy(), index=orders["order_id"])
        shipping = self.parsed_dates[("order_items", "shipping_limit_date")]
        put("order_items", "shipping_limit_before_purchase", shipping.lt(self.base["order_items"]["order_id"].map(purchases)))
        put("order_items", "shipping_limit_after_purchase_year_range", shipping.dt.year.gt(purchases.dt.year.max()))
        put("products", "missing_attributes", products[NUMBERS["products"]].isna().any(axis=1))
        for column in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
            put("products", f"nonpositive_{column}", products[column].le(0))
        for name, columns in [("order_items", ["price", "freight_value"]), ("payments", ["payment_value"])]:
            for column in columns:
                put(name, f"negative_{column}", self.base[name][column].lt(0))
                put(name, f"zero_{column}", self.base[name][column].eq(0))
        put("payments", "nonpositive_installments", self.base["payments"]["payment_installments"].le(0))
        for name, column in [("payments", "payment_installments"), ("reviews", "review_score")]:
            put(name, f"noninteger_{column}", self.base[name][column].mod(1).ne(0))
        put("reviews", "score_out_of_range", ~self.base["reviews"]["review_score"].between(1, 5))
        put("reviews", "repeated_review_id", self.base["reviews"]["review_id"].duplicated(keep=False))
        for name, column in [("customers", "customer_zip_code_prefix"), ("sellers", "seller_zip_code_prefix")]:
            put(name, "unmatched_zip", self.base[name][column].notna() & ~self.base[name][column].isin(self.lookup_expected["zip_code_prefix"]))
        for name, column in [("customers", "customer_zip_code_prefix"), ("sellers", "seller_zip_code_prefix"), ("geolocation", "geolocation_zip_code_prefix")]:
            put(name, "invalid_zip_format", self.base[name][column].notna() & ~self.base[name][column].str.fullmatch(r"\d{5}", na=False))
        put("geolocation", "invalid_coordinate", ~self.geo["geolocation_lat"].between(-90, 90) | ~self.geo["geolocation_lng"].between(-180, 180))
        put("geolocation_zip_lookup", "conflicting_city_labels", self.lookup_expected["distinct_city_labels"].gt(1))
        put("geolocation_zip_lookup", "conflicting_states", self.lookup_expected["distinct_states"].gt(1))
        put("geolocation_zip_lookup", "missing_coordinate", self.lookup_expected[["geolocation_lat", "geolocation_lng"]].isna().any(axis=1))

    def signature(self, name, frame):
        if name != "geolocation":
            return key_tuples(frame, KEYS[name])
        values = frame[list(self.raw[name].columns)].copy()
        for column in NUMBERS[name]:
            values[column] = pd.to_numeric(values[column], errors="coerce")
        return key_tuples(values, list(values.columns))

    def quality_flags(self):
        self.make_flag_conditions()
        flag_group_sets = {}
        trace_errors, observed_errors = [], []
        for row in self.flag_report.itertuples(index=False):
            name, rule = row.dataset, row.rule
            key = json.loads(row.record_key)
            if name not in self.base:
                trace_errors.append((name, rule, "unknown dataset"))
                continue
            if name == "geolocation_zip_lookup":
                columns = KEYS[name]
                identity = tuple(key.get(column) for column in columns)
                source_rows = self.lookup_expected.set_index("zip_code_prefix")
                source_row = source_rows.loc[key["zip_code_prefix"]]
            else:
                ordinal = int(Decimal(row.source_record_number)) - 1
                if ordinal < 0 or ordinal >= len(self.raw[name]):
                    trace_errors.append((name, rule, "invalid source ordinal"))
                    continue
                source_row = self.base[name].loc[ordinal] if ordinal in self.base[name].index else None
                original = self.raw[name].iloc[ordinal]
                declared = KEYS.get(name, ["geolocation_zip_code_prefix"])
                if any(str(original[column]).strip() != key.get(column) for column in declared):
                    trace_errors.append((name, rule, row.record_key))
                if source_row is None:
                    trace_errors.append((name, rule, "record was removed as geographic duplicate"))
                    continue
                identity = self.signature(name, source_row.to_frame().T)[0]
            flag_group_sets.setdefault((name, rule), set()).add(identity)
            for column, observed in json.loads(row.observed_values).items():
                if column not in source_row.index:
                    observed_errors.append((name, rule, column, "field not in independently reconstructed record"))
                    continue
                expected = source_row[column]
                if pd.isna(expected):
                    matches = observed is None or str(observed) in ["<NA>", "NaT", "nan", "None"]
                elif column in NUMBERS.get(name, []) or column in ["distinct_city_labels", "distinct_states"]:
                    matches = Decimal(str(expected)) == Decimal(str(observed))
                else:
                    matches = str(expected) == str(observed)
                if not matches:
                    observed_errors.append((name, rule, column, str(expected), str(observed)))
        duplicate_count = int(self.flag_report.duplicated(["dataset", "rule", "record_key", "source_record_number"]).sum())
        self.add("quality_flags", "flag_report_traceability", "all", "Each report row resolves to its actual raw business key/source ordinal or derived ZIP; observed evidence must agree.",
                 f"Bad source references={len(trace_errors)}; wrong observed values={len(observed_errors)}; duplicate report rows={duplicate_count}.",
                 len(trace_errors) + len(observed_errors) + duplicate_count, ok=not trace_errors and not observed_errors and duplicate_count == 0,
                 evidence={"trace_examples": trace_errors[:10], "observed_value_examples": observed_errors[:10]})
        expected_names = set(self.expected_flags)
        actual_names = {(name, column[3:]) for name, frame in self.processed.items() for column in frame if column.startswith("dq_")}
        self.add("quality_flags", "flag_schema_inventory", "all", "Every existing flag has an independently specified condition; no missing or unexplained flag columns.",
                 f"Expected={len(expected_names)}; actual={len(actual_names)}; differences={sorted(expected_names ^ actual_names)}.", len(expected_names ^ actual_names), ok=expected_names == actual_names)
        for (name, rule), mask in self.expected_flags.items():
            expected_frame = self.base[name]
            expected = set(self.signature(name, expected_frame.loc[mask]))
            frame = self.processed[name]
            column = f"dq_{rule}"
            if column not in frame:
                actual, invalid_booleans = set(), 0
            else:
                invalid_booleans = int((~frame[column].isin(["True", "False"])).sum())
                actual = set(self.signature(name, frame.loc[frame[column].eq("True")]))
            reported = flag_group_sets.get((name, rule), set())
            false_positive, false_negative = actual - expected, expected - actual
            report_difference = reported ^ expected
            failure_count = len(false_positive) + len(false_negative) + len(report_difference) + invalid_booleans
            self.add("quality_flags", f"flag_{name}_{rule}", name, "Processed Boolean flags and long-report record IDs equal the independently recomputed source condition.",
                     f"Expected={len(expected)}; Boolean IDs={len(actual)}; report IDs={len(reported)}; FP={len(false_positive)}; FN={len(false_negative)}; report differences={len(report_difference)}.",
                     failure_count, ok=failure_count == 0, evidence={"expected_flagged_records": len(expected), "false_positives": list(false_positive)[:5], "false_negatives": list(false_negative)[:5], "report_differences": list(report_difference)[:5]})
            self.inventory.append({"dataset": name, "column": column, "original_value_or_dtype": "New quality metadata, absent from raw",
                                   "transformation_rule": f"Boolean source rule: {rule}; record/rule trace retained in long report.", "expected_output": "True/False, no nulls",
                                   "affected_records": len(expected), "business_justification": "Make unresolved conditions visible without deleting or changing business records.",
                                   "independent_validation": "PASS" if failure_count == 0 else "FAIL"})
        extra_reports = set(flag_group_sets) - expected_names
        self.add("quality_flags", "unexpected_report_rules", "all", "No unexplained groups in the flag report.", str(sorted(extra_reports)), len(extra_reports), ok=not extra_reports)

    def business_rules(self):
        attention = [
            ("orders", "no_items"), ("orders", "no_payments"), ("orders", "no_reviews"),
            ("orders", "missing_order_approved_at"), ("orders", "missing_order_delivered_carrier_date"), ("orders", "missing_order_delivered_customer_date"),
            ("orders", "delivered_missing_order_approved_at"), ("orders", "delivered_missing_order_delivered_carrier_date"), ("orders", "delivered_missing_order_delivered_customer_date"),
            ("orders", "carrier_before_purchase"), ("orders", "carrier_before_approval"), ("orders", "delivery_before_carrier"),
            ("products", "missing_attributes"), ("products", "nonpositive_product_weight_g"), ("payments", "nonpositive_installments"),
            ("products", "category_missing"), ("products", "category_untranslated"),
        ]
        for name, rule in attention:
            count = int(self.expected_flags[(name, rule)].sum())
            self.add("business_rules", f"source_limitation_{name}_{rule}", name, "Preserve source records and documented flags; the condition needs analysis context rather than automatic deletion.",
                     f"{count} retained source records meet {rule}.", count, status="WARN" if count else "PASS", severity="low",
                     correction="Use the existing flag to define and disclose analytic eligibility; investigate source meaning before changing values.")
        orders = self.base["orders"]
        delivery = self.parsed_dates[("orders", "order_delivered_customer_date")]
        non_delivered = ~orders["order_status"].eq("delivered") & delivery.notna()
        counts = orders.loc[non_delivered, "order_status"].value_counts().to_dict()
        self.add("business_rules", "non_delivered_status_with_delivery_date", "orders", "Retain potentially ambiguous status/event combinations and identify them before delivery EDA.",
                 f"{int(non_delivered.sum())} non-delivered-status orders have customer delivery dates; status counts={counts}. No dedicated status/event contradiction flag exists.",
                 int(non_delivered.sum()), status="WARN" if non_delivered.any() else "PASS", severity="medium", evidence={"status_counts": counts, "order_ids": orders.loc[non_delivered, "order_id"].tolist()},
                 correction="Review cancellations/status transitions and define EDA eligibility; do not infer incorrect source dates from status alone.")
        dimensions = ["product_length_cm", "product_height_cm", "product_width_cm"]
        bad_dimensions = int(self.base["products"][dimensions].le(0).any(axis=1).sum())
        negative_money = sum(int(self.base[name][column].lt(0).sum()) for name, columns in [("order_items", ["price", "freight_value"]), ("payments", ["payment_value"])] for column in columns)
        unknown_statuses = sorted(set(orders["order_status"]) - {"delivered", "shipped", "canceled", "unavailable", "invoiced", "processing", "approved", "created"})
        self.add("business_rules", "numeric_and_status_domains", "products/orders/payments/items", "Investigate invalid dimensions, negative financial values and unknown status labels; no silent correction.",
                 f"Non-positive dimensions={bad_dimensions}; negative money={negative_money}; unknown statuses={unknown_statuses}.", bad_dimensions + negative_money + len(unknown_statuses),
                 status="WARN" if bad_dimensions or negative_money or unknown_statuses else "PASS", evidence={"zero_freight_values": int(self.base['order_items']['freight_value'].eq(0).sum()), "zero_payments": int(self.base['payments']['payment_value'].eq(0).sum())},
                 correction="Retain legitimate zeros; use range flags and business context for exclusions.")

    def reports_and_schema(self):
        for name, frame in self.processed.items():
            originals = set(self.raw[name].columns) if name in self.raw else set(self.lookup_expected.columns)
            derived = {f"dq_{rule}" for table, rule in self.expected_flags if table == name}
            if name == "products":
                derived.add("product_category_name_english")
            expected = originals | derived
            actual = set(frame.columns)
            self.add("report_accuracy", f"complete_schema_{name}", name, "All original and justified derived columns, without unexplained additions/removals.",
                     f"Columns={len(actual)}; missing={sorted(expected-actual)}; unexplained={sorted(actual-expected)}.", len(expected ^ actual), ok=expected == actual)
        wrong_actions = []
        # Recalculate every transformation/action count, not just the highlighted summary.
        for record in self.actions.itertuples(index=False):
            name, action, column = record.dataset, record.action, record.column
            raw = self.raw.get(name)
            expected = None
            if action == "strip_outer_whitespace":
                original = raw[column]
                expected = int((original.notna() & original.ne(original.str.strip())).sum())
            elif action == "blank_text_to_missing":
                expected = int(raw[column].notna().where(raw[column].str.fullmatch(r"\s*", na=False), False).sum())
            elif action in ["parse_datetime", "parse_numeric"]:
                expected = int(trimmed(raw[column]).notna().sum())
                details = json.loads(record.details)
                expected_invalid = int(self.expected_flags[(name, f"invalid_{column}")].sum())
                if details.get("invalid") != expected_invalid:
                    wrong_actions.append((name, action, column, "incorrect invalid count"))
            elif action == "normalize_category_case":
                values = trimmed(raw[column])
                expected = int((values.notna() & values.ne(values.str.lower())).sum())
            elif action == "missing_category_label":
                expected = int(trimmed(raw[column]).isna().sum())
            elif action == "english_category_lookup":
                expected = int((~self.expected_flags[("products", "category_missing")] & ~self.expected_flags[("products", "category_untranslated")]).sum())
            elif action == "exact_duplicate_handling":
                normalized = self.base[name]
                expected = len(raw) - len(self.geo) if name == "geolocation" else int(normalized.duplicated().sum())
                if json.loads(record.details).get("raw_exact_duplicates") != int(raw.duplicated().sum()):
                    wrong_actions.append((name, action, column, "incorrect raw duplicate count"))
            elif action == "representative_zip_lookup":
                expected = len(self.lookup_expected)
            elif action == "repeated_zip_prefix_observations":
                expected = int(self.geo["geolocation_zip_code_prefix"].duplicated(keep=False).sum())
            elif action == "repeated_coordinate_pairs_within_zip":
                expected = int(self.geo.duplicated(["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"]).sum())
            elif record.decision == "flagged; retained":
                expected = int(self.expected_flags[(name, action)].sum())
            elif action == "missing_values_preserved":
                expected = int(self.processed[name][column].isna().sum())
            elif action == "row_count_validation":
                details = json.loads(record.details)
                expected = len(self.processed[name])
                before = len(raw) if raw is not None else 0
                if details != {"dataset": name, "rows_before": before, "rows_after": expected, "rows_removed": before - expected if raw is not None else 0}:
                    wrong_actions.append((name, action, column, "row-count detail mismatch"))
            elif action == "primary_key_validation":
                d = json.loads(record.details)
                keys = KEYS[name]
                nulls = int(self.processed[name][keys].isna().any(axis=1).sum())
                duplicate = int(self.processed[name].duplicated(keys).sum())
                expected = 0
                if d.get("null_key_rows") != nulls or d.get("duplicate_keys_excess") != duplicate or d.get("valid") != (nulls == duplicate == 0):
                    wrong_actions.append((name, action, column, "key detail mismatch"))
            elif action == "financial_value_validation":
                expected = len(raw)
                if not json.loads(record.details).get("exact_decimal_equality"):
                    wrong_actions.append((name, action, column, "financial result incorrect"))
            elif action == "relationship_validation":
                d = json.loads(record.details)
                child = self.base[name][column]
                parent = self.base[d["parent_dataset"]][d["parent_key"]]
                unmatched = int((child.notna() & ~child.isin(parent)).sum())
                expected = unmatched
                if d.get("child_rows") != len(child) or d.get("unmatched_rows") != unmatched or d.get("null_foreign_key_rows") != int(child.isna().sum()) or d.get("matched_rows") != len(child) - unmatched - int(child.isna().sum()) or d.get("rows_after_join") != len(child):
                    wrong_actions.append((name, action, column, "relationship detail mismatch"))
            if expected is None:
                wrong_actions.append((name, action, column, "unverified action rule"))
            elif int(record.affected_records) != expected:
                wrong_actions.append((name, action, column, int(record.affected_records), expected))
        self.add("report_accuracy", "all_cleaning_action_counts", "all", "Independently verified counts/details for every existing cleaning-summary action.",
                 f"Reviewed {len(self.actions)} actions; mismatches={len(wrong_actions)}.", len(wrong_actions), ok=not wrong_actions, evidence={"mismatches": wrong_actions[:30]})
        for phase, notebook in self.notebooks.items():
            nbformat.validate(notebook)
            cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
            executed = [cell.execution_count for cell in cells] == list(range(1, len(cells) + 1))
            errors = sum(output.output_type == "error" for cell in cells for output in cell.outputs)
            self.add("report_accuracy", f"saved_notebook_execution_phase_{phase}", "notebook", "Valid notebook schema and saved sequential executions without error outputs; no notebook re-execution.",
                     f"{len(cells)} code cells; sequential={executed}; saved errors={errors}.", errors, ok=executed and errors == 0)
        # Verify all quantitative tables in the Phase 2 Markdown report against actual CSVs.
        summary_mismatches = []
        for line in self.summaries[2].splitlines():
            if not line.startswith("| "):
                continue
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) == 7 and parts[1].endswith(".csv"):
                name, filename, rows, cols, size, expected_hash, checked = parts
                path = self.root / "data/processed" / filename
                if int(rows) != len(self.processed[name]) or int(cols) != len(self.processed[name].columns) or int(size) != path.stat().st_size or expected_hash != sha(path) or checked != "True":
                    summary_mismatches.append((name, "export inventory"))
            elif len(parts) == 4 and parts[0] in self.processed and all(re.fullmatch(r"\d+", part) for part in parts[1:]):
                name, before, after, removed = parts
                expected_before = len(self.raw[name]) if name in self.raw else 0
                expected_after = len(self.processed[name])
                if int(before) != expected_before or int(after) != expected_after or int(removed) != (expected_before - expected_after if name in self.raw else 0):
                    summary_mismatches.append((name, "row inventory"))
        self.add("report_accuracy", "markdown_quantitative_inventory", "all", "Summary row-count/export tables and SHA-256 hashes match saved outputs.", f"Mismatches={len(summary_mismatches)}.", len(summary_mismatches), ok=not summary_mismatches, evidence={"mismatches": summary_mismatches})

    def reproducibility(self):
        # This control alone calls the existing implementation. It does not supply
        # expected answers to any independent validation above and never exports.
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("audited_cleaner_readonly", self.root / "src/data_processing/cleaning.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw_fingerprints = {name: hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest() for name, frame in self.raw.items()}
        repeated, _, repeated_flags = module.clean_datasets(self.raw)
        changed = []
        for name, frame in repeated.items():
            payload = frame.to_csv(index=False, encoding="utf-8", date_format="%Y-%m-%d %H:%M:%S", lineterminator="\n").encode("utf-8")
            path = self.root / "data/processed" / (f"{name}_clean.csv" if name != "geolocation_zip_lookup" else "geolocation_zip_lookup.csv")
            if hashlib.sha256(payload).hexdigest() != sha(path):
                changed.append(name)
        self.add("reproducibility", "full_pipeline_in_memory_reproduction", "all", "Running the existing cleaner without exports reproduces all saved CSV bytes; independent checks remain separate.",
                 f"Different datasets={changed}; no existing output files were written.", len(changed), ok=not changed)
        lookup_again = module.build_zip_lookup(repeated["geolocation"].iloc[::-1], self.raw["geolocation"])
        left = repeated["geolocation_zip_lookup"].drop(columns=[column for column in repeated["geolocation_zip_lookup"] if column.startswith("dq_")])
        mismatch = False
        try:
            pd.testing.assert_frame_equal(left, lookup_again)
        except AssertionError:
            mismatch = True
        self.add("reproducibility", "zip_lookup_input_order_independence", "geolocation_zip_lookup", "Repeated selection with reversed source-observation order returns the same ZIP representatives and statistics.",
                 f"Mismatch={mismatch}; original and reversed in-memory runs compared.", int(mismatch), ok=not mismatch)
        raw_changed = [name for name, frame in self.raw.items() if hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest() != raw_fingerprints[name]]
        self.add("preservation", "in_memory_raw_preservation", "all", "Existing cleaner does not mutate caller-owned raw DataFrame values/order.", f"Changed source DataFrames={raw_changed}.", len(raw_changed), ok=not raw_changed)
        # Reproduced runtime schemas verify type expectations; CSV itself has no dtypes.
        bad_types = []
        reported_dtype_mismatches = []
        for name, frame in repeated.items():
            for column, dtype in frame.dtypes.items():
                if column in DATES.get(name, []):
                    valid = pd.api.types.is_datetime64_any_dtype(dtype)
                elif column in NUMBERS.get(name, []):
                    valid = pd.api.types.is_numeric_dtype(dtype)
                elif column.startswith("dq_"):
                    valid = pd.api.types.is_bool_dtype(dtype)
                else:
                    valid = True
                if not valid:
                    bad_types.append(f"{name}.{column}:{dtype}")
                if not column.startswith("dq_") and (column.endswith("_id") or "zip_code_prefix" in column or column == "payment_sequential") and not isinstance(dtype, pd.StringDtype):
                    bad_types.append(f"{name}.{column}:{dtype}")
                if name in self.raw and column in self.raw[name]:
                    reported = self.missing_report.loc[(self.missing_report["dataset"] == name) & (self.missing_report["column"] == column)]
                    if len(reported) != 1 or reported.iloc[0]["dtype_before"] != str(self.raw[name][column].dtype) or reported.iloc[0]["dtype_after"] != str(dtype):
                        reported_dtype_mismatches.append(f"{name}.{column}")
        self.add("reproducibility", "runtime_schema_reproduced", "all", "Dates, numeric values, identifiers/ZIPs and Boolean flags have appropriate types when recreated in memory.", f"Incorrect runtime types={bad_types}.", len(bad_types), ok=not bad_types,
                 evidence={"limitation": "CSV format does not carry type metadata; downstream readers must specify a schema."})
        self.add("report_accuracy", "reported_before_after_dtypes", "all", "All 52 recorded before/after dtype labels agree with the recreated source and processed schemas.",
                 f"Incorrect dtype report entries={reported_dtype_mismatches}.", len(reported_dtype_mismatches), ok=not reported_dtype_mismatches)
        del repeated, repeated_flags, lookup_again, left
        gc.collect()

    def preservation_and_limits(self):
        manifest = json.loads((self.root / "data/DATASET_MANIFEST.json").read_text(encoding="utf-8"))
        for entry in manifest:
            path = self.root / "data/raw" / entry["filename"]
            ok = sha(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]
            self.add("preservation", f"raw_manifest_{entry['filename']}", "raw", "Raw file matches initialization SHA-256 and byte size.", f"Match={ok}.", int(not ok), ok=ok)
        changed = [name for name, before in self.protected.items() if not (self.root / name).is_file() or sha(self.root / name) != before]
        self.add("preservation", "audit_read_only_guarantee", "all", "Existing data, scripts, notebooks, tests, reports and documentation remain byte-identical throughout the audit.",
                 f"Protected files={len(self.protected)}; changed files={changed}.", len(changed), ok=not changed, evidence={"protected_sha256": self.protected})
        self.add("limits", "authoritative_geographic_accuracy", "geolocation_zip_lookup", "Verify representative locations against authoritative geographic ground truth.",
                 "NOT VERIFIED: no authoritative external ZIP/address boundary source is present; only local-source consistency, ranges and heuristic selection were verified.",
                 status="NOT VERIFIED", correction="Use authoritative geographic reference data if street-level or official ZIP geography is required.")
        self.add("limits", "original_timezone_provenance", "timestamps", "Establish the real-world source timezone of naive timestamps.",
                 "NOT VERIFIED: source timestamp strings contain no timezone metadata. Exact raw-to-clean equality and absence of shifts were independently verified.",
                 status="NOT VERIFIED", correction="Do not infer a timezone or convert timezones without a documented source convention.")

    def run(self):
        for method in [self.transformations, self.missing_values, self.duplicates_and_keys, self.money, self.timestamps,
                       self.independent_lookup, self.relationships, self.quality_flags, self.business_rules,
                       self.reports_and_schema, self.reproducibility, self.preservation_and_limits]:
            print(f"Independent audit: {method.__name__}", flush=True)
            method()
        return self

    def write_reports(self, pytest_scenarios):
        directory = self.root / "reports/audit"
        filenames = ["phase_2_audit_report.md", "phase_2_audit_results.csv", "phase_2_discrepancies.csv"]
        if any((directory / filename).exists() for filename in filenames):
            raise FileExistsError("Audit reports already exist; refusing to overwrite existing reports.")
        directory.mkdir(parents=True, exist_ok=True)
        results = pd.DataFrame(self.results)
        discrepancies = results.loc[results["status"] != "PASS"].copy()
        counts = results["status"].value_counts().reindex(["PASS", "WARN", "FAIL", "NOT VERIFIED"], fill_value=0)
        decision = "REQUIRES FIXES" if counts["FAIL"] else "APPROVED WITH WARNINGS" if counts["WARN"] or counts["NOT VERIFIED"] else "APPROVED"
        summary_counts = pd.DataFrame({"status": counts.index, "checks": counts.values})
        inventory = pd.DataFrame(self.inventory)
        nonpass = discrepancies[["test_name", "dataset", "status", "affected_records", "actual_behavior", "recommended_correction"]]
        report = "\n\n".join([
            "# Independent Phase 2 Data Cleaning Audit",
            f"**Decision: {decision}.** This is an audit-only result, not approval to begin Phase 3. No existing datasets, code, notebooks, tests, documentation or reports were modified.",
            "## Test accounting", f"The separate pytest suite contains {pytest_scenarios} category scenarios. This report contains {len(results)} individually recorded checks. WARN checks are verified source limitations or documented behavior requiring attention, not incorrect cleaning. NOT VERIFIED checks are not counted as passes.", table_md(summary_counts),
            "## Method and independence",
            "All nine raw CSVs and ten processed CSVs were read directly, preserving identifiers/ZIPs and literal text. Eight tables were matched by stable primary/composite business keys. Geographic observations were reconciled by their complete normalized ZIP/latitude/longitude/city/state signatures, not CSV row positions. Financial comparisons use exact Decimal values per key and exact totals, separately for price, freight and payments; payment totals were not required to equal merchandise totals.",
            "The existing implementation, both notebooks, all original tests, Phase 1/2 summaries and three Phase 2 CSV reports were inspected. Expected transformations, flag masks and representative geography were independently computed from source CSVs without calling cleaning helpers. A separate, explicitly labelled reproducibility control then ran the existing cleaner only in memory, compared all ten serialized outputs with saved bytes and checked reversed-order ZIP selection. It did not export or execute notebooks.",
            "## Raw versus processed inventory", table_md(pd.DataFrame(self.row_counts)),
            "## Financial integrity", table_md(pd.DataFrame(self.financial)),
            "Trailing-zero formatting differences are not monetary precision loss. Every non-geographic numerical source field was also checked by Decimal value. Geographic point fields were checked as their documented parsed numeric representation; lookup representative comparisons allow at most 1e-12 degrees of float serialization tolerance. No such tolerance is used for money.",
            "## Transformation inventory", "Affected counts refer to each rule's scope, not distinct changed records across the whole project. Type conversion counts include all populated fields targeted by the type rule. All source columns, the derived English category, every quality flag and every ZIP representative/statistic field are listed below.", table_md(inventory),
            "## Findings requiring attention or fixes", table_md(nonpass),
            "## Quality flag audit",
            "Every existing dq_* rule was independently recomputed from raw-derived values, not trusted from processed flags. Record ID sets were compared for false positives/negatives against both Boolean columns and the long report. The audit also checked duplicate flag rows, one-based parsed source-record ordinals, composite keys, observed-value JSON, Boolean serialization and all recorded per-rule counts. Counts can overlap across rules. Informational flags are not all defects.",
            "## Report verification",
            "Recomputed all 52 before/after missingness counts, denominators and percentages, every action count and structured key/FK/financial detail in cleaning_summary.csv, all original/derived column names and counts, and summary row/export inventory hashes. Saved notebook schema and sequential execution metadata were inspected without re-executing notebooks. All pass/fail details and evidence are in phase_2_audit_results.csv. phase_2_discrepancies.csv contains WARN, FAIL and NOT VERIFIED rows; warnings are not classified as cleaning failures.",
            "## EDA readiness and recommendations",
            "Use the unique ZIP lookup for joins and disclose unmatched entities, label ambiguity and approximate location semantics. Define order-status and delivery-date eligibility before reporting delivery performance. Late delivery is a performance outcome and is not itself a cleaning defect; choose calendar-day versus timestamp lateness explicitly. Keep optional missing review text distinct from rating availability. Preserve Unknown-category provenance and respect item/payment/review grains before combining summaries.",
            "## Limits",
            "This audit verifies the supplied local files, not the completeness or real-world accuracy of Olist's source system. The initialization manifest is local provenance evidence, not an authenticated publisher signature. Source timezone and authoritative geographic accuracy are not established. CSV has no persistent dtype metadata; runtime schema was reproduced in memory and serialized field validity was independently checked. Historical execution beyond saved metadata cannot be reconstructed. This report does not claim 100% correctness or authorize Phase 3 work.",
            "## Separate audit suite and rerun",
            "The independent suite is tests/test_phase_2_audit.py, supported by tests/phase_2_audit.py. Run `.venv/Scripts/python.exe -B -m pytest tests/test_phase_2_audit.py -q -s -p no:cacheprovider`. By default, reruns recompute checks without writing reports. The initial report-generation run used PHASE2_AUDIT_WRITE=1; report writing uses exclusive creation and refuses to overwrite existing reports. Existing tests were not modified.",
            "**Stop after the audit and wait for approval.**",
        ]) + "\n"
        for path, content in [(directory / filenames[0], report), (directory / filenames[1], results.to_csv(index=False, lineterminator="\n")), (directory / filenames[2], discrepancies.to_csv(index=False, lineterminator="\n"))]:
            with path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
        print(f"Audit decision: {decision}; checks={len(results)}; statuses={counts.to_dict()}", flush=True)
