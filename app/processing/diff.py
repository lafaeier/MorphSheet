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

    orig_idx = original.reset_index(drop=True)
    trans_idx = transformed.reset_index(drop=True)

    # --- 查找被删除的行 (通过ID列或位置) ---
    id_col = _find_id_column(orig_idx, trans_idx)

    if id_col and len(trans_idx) < len(orig_idx):
        # ID-based matching: find source rows whose ID is missing in result
        src_ids = set(orig_idx[id_col].dropna().astype(str))
        res_ids = set(trans_idx[id_col].dropna().astype(str))
        deleted_ids = src_ids - res_ids
        removed_rows = []
        for i in range(len(orig_idx)):
            if str(orig_idx.iloc[i][id_col]) in deleted_ids:
                removed_rows.append(i)
        result["removed_rows"] = removed_rows
    else:
        # Position-based fallback
        if len(trans_idx) < len(orig_idx):
            result["removed_rows"] = list(range(len(trans_idx), len(orig_idx)))

    # --- 逐行比较修改的单元格 ---
    removed_set = set(result["removed_rows"])
    modified_cells = []
    unchanged = 0

    # Build ID lookup for result rows (if ID column available)
    res_id_map = {}
    if id_col:
        for ri in range(len(trans_idx)):
            rid = str(trans_idx.iloc[ri][id_col])
            res_id_map[rid] = ri

    for oi in range(len(orig_idx)):
        if oi in removed_set:
            continue  # Skip deleted rows

        # Find corresponding result row
        if id_col and id_col in orig_idx.columns:
            oid = str(orig_idx.iloc[oi][id_col])
            ri = res_id_map.get(oid, -1)
            if ri < 0:
                continue  # No match
        else:
            ri = oi  # Same position
            if ri >= len(trans_idx):
                continue

        row_changed = False
        for col in common_cols:
            if col not in orig_idx.columns or col not in trans_idx.columns:
                continue
            old_val = orig_idx.iloc[oi][col]
            new_val = trans_idx.iloc[ri][col]
            if pd.isna(old_val) and pd.isna(new_val):
                continue
            if str(old_val) != str(new_val):
                modified_cells.append({
                    "row": oi,
                    "col": col,
                    "old": None if pd.isna(old_val) else old_val,
                    "new": None if pd.isna(new_val) else new_val,
                })
                row_changed = True
        if not row_changed and oi not in removed_set:
            unchanged += 1

    result["modified_cells"] = modified_cells
    result["unchanged_row_count"] = unchanged

    return result


def _find_id_column(orig: pd.DataFrame, trans: pd.DataFrame) -> str | None:
    """查找可用于行匹配的ID列。"""
    common = set(orig.columns) & set(trans.columns)
    id_patterns = ['id', 'ID', '编号', '序号', 'code', 'Code']
    for col in common:
        col_lower = col.lower()
        for pat in id_patterns:
            if pat.lower() in col_lower:
                return col
    # 如果第一列是唯一值，用它
    if len(common) > 0:
        first_col = list(common)[0]
        if orig[first_col].nunique() == len(orig):
            return first_col
    return None
