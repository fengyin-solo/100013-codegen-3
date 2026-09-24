"""系统设置业务规则：状态流转、字段校验、筛选口径与参数值更新都收在这里。"""
from __future__ import annotations

import json
from typing import Any

from app.store import store

MODULE = "setting"
REQUIRED_FIELDS = ["参数编码", "参数名称", "参数值"]
STATUS_ORDER = ["已生效", "待生效", "已回滚"]
ACTION_RULES = {"修改参数": "待生效", "回滚参数": "已回滚", "生效参数": "已生效"}
NEGATIVE_ACTIONS = ["回滚参数"]

# 冷藏车准用规则参数：值必须是对应结构的 JSON，调整后立刻被车辆判定读取。
JSON_PARAM_SHAPES = {
    "VEHICLE_VOLUME_RULES": dict,
    "VEHICLE_UNIT_WHITELIST": list,
}


class SettingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("参数编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"系统参数 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于系统设置可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"系统参数已{action}"

    def update_value(self, entry_id: int, value: Any) -> tuple[dict[str, Any] | None, str]:
        """更新系统参数值。

        参数保存在内存仓库里，服务不重启就一直生效；冷藏车准用规则每次判定都
        实时读取，因此调整后刷新车辆列表即可看到新结果，无需重启。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"系统参数 {entry_id} 不存在或已归档"
        text = str(value if value is not None else "").strip()
        if not text:
            return None, "参数值不能为空"

        code = str(entry.get("参数编码") or "")
        expected_shape = JSON_PARAM_SHAPES.get(code)
        if expected_shape is not None:
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                return None, f"参数「{code}」的值必须是合法 JSON"
            if not isinstance(parsed, expected_shape):
                shape_name = "对象" if expected_shape is dict else "数组"
                return None, f"参数「{code}」的值必须是 JSON {shape_name}"

        entry["参数值"] = text
        return entry, f"系统参数「{entry.get('参数名称') or code}」已更新并生效"
