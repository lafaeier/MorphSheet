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

    # --- 查找被删除的行 ---
    # id_col 返回 (orig_col, trans_col) 元组，或 None
    id_cols = _find_id_column(orig_idx, trans_idx)
    removed_rows = []

    if id_cols and len(trans_idx) < len(orig_idx):
        orig_id, trans_id = id_cols
        src_ids = set(orig_idx[orig_id].dropna().astype(str))
        res_ids = set(trans_idx[trans_id].dropna().astype(str))
        deleted_ids = src_ids - res_ids
        for i in range(len(orig_idx)):
            if str(orig_idx.iloc[i][orig_id]) in deleted_ids:
                removed_rows.append(i)
    elif len(trans_idx) < len(orig_idx):
        # 无ID列时：标记尾部多出行（保守策略，不标记中间删除）
        removed_rows = list(range(len(trans_idx), len(orig_idx)))

    result["removed_rows"] = removed_rows

    # --- 逐行比较修改的单元格 ---
    removed_set = set(result["removed_rows"])
    modified_cells = []
    unchanged = 0

    # Build ID lookup for result rows
    res_id_map = {}
    if id_cols:
        orig_id, trans_id = id_cols
        for ri in range(len(trans_idx)):
            rid = str(trans_idx.iloc[ri][trans_id])
            res_id_map[rid] = ri

    for oi in range(len(orig_idx)):
        if oi in removed_set:
            continue

        # Find corresponding result row
        if id_cols:
            orig_id, trans_id = id_cols
            oid = str(orig_idx.iloc[oi][orig_id])
            ri = res_id_map.get(oid, -1)
            if ri < 0:
                continue
        else:
            ri = oi
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


def _find_id_column(orig: pd.DataFrame, trans: pd.DataFrame) -> tuple | None:
    """查找可用于行匹配的ID列，返回 (orig_col, trans_col) 或 None。"""
    common = set(orig.columns) & set(trans.columns)
    id_patterns = ['id', 'ID', '编号', '序号', 'code', 'Code', 'CUST', 'EMP',
                   '员工', '客户', '学号', '工号', 'no', 'NO', 'No', 'key', 'Key']
    # 1. 公共列中按模式匹配
    for col in common:
        col_lower = col.lower()
        for pat in id_patterns:
            if pat.lower() in col_lower:
                if orig[col].nunique() == len(orig):
                    return (col, col)
    # 2. 公共列中第一列为全唯一值
    common_list = [c for c in orig.columns if c in common]
    if common_list:
        first_col = common_list[0]
        if orig[first_col].nunique() == len(orig):
            return (first_col, first_col)
    # 3. 列名被重命名 — 按位置匹配第一列值集合
    if len(orig.columns) > 0 and len(trans.columns) > 0:
        ocol = orig.columns[0]
        tcol = trans.columns[0]
        if orig[ocol].nunique() == len(orig):
            ov = set(orig[ocol].dropna().astype(str))
            tv = set(trans[tcol].dropna().astype(str))
            if ov and tv and len(ov & tv) > len(orig) * 0.8:
                return (ocol, tcol)
    return None
