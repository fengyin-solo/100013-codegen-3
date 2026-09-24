"""系统设置业务规则：参数登记、修改、生效与回滚的口径都收在这里。

冷藏车准用规则等业务模块只读取「已生效」的系统参数；参数修改后先进入
「待生效」，执行生效参数才真正参与判定，回滚参数则作废本次修改。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "setting"
REQUIRED_FIELDS = ["参数编码", "参数名称", "参数值"]
STATUS_ORDER = ["已生效", "待生效", "已回滚"]
ACTION_RULES = {"修改参数": "待生效", "回滚参数": "已回滚", "生效参数": "已生效"}
NEGATIVE_ACTIONS = ["回滚参数"]
EFFECTIVE_STATUS = "已生效"


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
        entry["status"] = EFFECTIVE_STATUS
        # 已生效参数不需要再出现在待处理口径里
        entry["pending"] = False
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"系统参数 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于系统设置可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        values = values or {}

        if action == "修改参数":
            new_value = str(values.get("参数值") or "").strip()
            if not new_value:
                return None, "修改参数时必须填写新的参数值"
            # 保存当前生效值以便回滚，再写入待生效的新值
            if entry.get("status") != "待生效":
                entry["回滚参数值"] = entry.get("参数值")
            entry["参数值"] = new_value
            if str(values.get("参数名称") or "").strip():
                entry["参数名称"] = str(values.get("参数名称")).strip()
            entry["status"] = "待生效"
            entry["pending"] = True
            entry["abnormal"] = False
            return entry, "系统参数已修改，待生效后参与业务判定"

        if action == "生效参数":
            entry["status"] = EFFECTIVE_STATUS
            entry["pending"] = False
            entry["abnormal"] = False
            entry.pop("回滚参数值", None)
            return entry, "系统参数已生效，相关准用规则按新口径执行"

        # 回滚参数：作废待生效修改，恢复最近一次生效前保存的参数值并回到已生效态
        if "回滚参数值" not in entry:
            return None, "该参数没有待回滚的修改，仅待生效参数可以回滚"
        entry["参数值"] = entry.pop("回滚参数值")
        entry["status"] = EFFECTIVE_STATUS
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, "系统参数已回滚，恢复为上一次生效的参数值并继续按该值判定"
