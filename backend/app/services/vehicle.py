"""冷藏车管理业务规则：状态流转、字段校验、准用判定与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store
from app.services.vehicle_rules import annotate_entry, evaluate, rules_summary

MODULE = "vehicle"
REQUIRED_FIELDS = ["车牌号码", "车辆类型", "制冷机组型号"]
STATUS_ORDER = ["可用", "出车中", "维修中", "已停用"]
ACTION_RULES = {"安排出车": "出车中", "回场登记": "可用", "停用车辆": "已停用"}
NEGATIVE_ACTIONS = ["停用车辆"]
DISPATCH_ACTION = "安排出车"


class VehicleService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        eligible: bool | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("车牌号码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 先按系统参数判定准用条件，再支持「只看准予出车车辆」的筛选
        rows = [annotate_entry(dict(row)) for row in rows]
        if eligible is not None:
            rows = [
                row
                for row in rows
                if (row["准用状态"] == "准予出车") == eligible
            ]
        eligible_total = sum(1 for row in rows if row["准用状态"] == "准予出车")
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total, eligible_total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return annotate_entry(dict(entry))

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
            return None, f"冷藏车辆 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于冷藏车管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        # 安排出车必须同时通过停用状态、机组白名单与容积范围三组准用条件
        if action == DISPATCH_ACTION:
            verdict = evaluate(entry)
            if not verdict["eligible"]:
                return None, f"不满足车辆准用条件，无法安排出车：{verdict['message']}"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return annotate_entry(dict(entry)), f"冷藏车辆已{action}"

    def eligibility_rules(self) -> dict[str, Any]:
        """返回当前生效的准用规则摘要，供列表页和详情页展示判定口径。"""
        return rules_summary()
