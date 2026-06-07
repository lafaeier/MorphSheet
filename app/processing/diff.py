import pandas as pd
import numpy as np


def compute(original: pd.DataFrame, transformed: pd.DataFrame) -> dict:
    """计算两个 DataFrame 之间的差异。"""
    result = {
        "row_counts": {"original": len(original), "transformed": len(transformed)},
        "added_columns": [],
        "removed_columns": [],
        "renamed_columns": {},
        "added_rows": [],
        "removed_rows": [],
        "modified_cells": [],
        "unchanged_row_count": 0,
    }

    orig_cols = set(original.columns)
    trans_cols = set(transformed.columns)

    result["added_columns"] = list(trans_cols - orig_cols)
    result["removed_columns"] = list(orig_cols - trans_cols)
    common_cols = list(orig_cols & trans_cols)

    orig_indexed = original.reset_index(drop=True)
    trans_indexed = transformed.reset_index(drop=True)

    if len(trans_indexed) < len(orig_indexed):
        removed_rows, modified_cells, unchanged = _row_diff(orig_indexed, trans_indexed, common_cols)
        result["removed_rows"] = removed_rows
        result["modified_cells"] = modified_cells
        result["unchanged_row_count"] = unchanged
    elif len(trans_indexed) > len(orig_indexed):
        removed_rows, modified_cells, unchanged = _row_diff(orig_indexed, trans_indexed, common_cols)
        result["removed_rows"] = removed_rows
        result["modified_cells"] = modified_cells
        result["unchanged_row_count"] = unchanged
        result["added_rows"] = list(range(len(orig_indexed), len(trans_indexed)))
    else:
        removed_rows, modified_cells, unchanged = _row_diff(orig_indexed, trans_indexed, common_cols)
        result["removed_rows"] = removed_rows
        result["modified_cells"] = modified_cells
        result["unchanged_row_count"] = unchanged

    return result


def _row_diff(orig: pd.DataFrame, trans: pd.DataFrame, cols: list[str]):
    removed_rows = []
    modified_cells = []
    unchanged = 0

    min_len = min(len(orig), len(trans))

    for i in range(min_len):
        row_changed = False
        for col in cols:
            if col not in orig.columns or col not in trans.columns:
                continue
            old_val = orig.at[i, col] if col in orig.columns else None
            new_val = trans.at[i, col] if col in trans.columns else None
            if pd.isna(old_val) and pd.isna(new_val):
                continue
            if str(old_val) != str(new_val):
                modified_cells.append({
                    "row": i,
                    "col": col,
                    "old": None if pd.isna(old_val) else old_val,
                    "new": None if pd.isna(new_val) else new_val,
                })
                row_changed = True
        if not row_changed:
            unchanged += 1

    if len(orig) > len(trans):
        removed_rows = list(range(min_len, len(orig)))

    return removed_rows, modified_cells, unchanged
