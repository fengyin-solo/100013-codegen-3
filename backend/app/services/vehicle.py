"""冷藏车管理业务规则：状态流转、字段校验、筛选口径与出车准用条件都收在这里。

准用条件由系统参数（setting 模块）驱动，每次判定都实时读取：

- ``VEHICLE_VOLUME_RULES``：按车辆类型配置车厢容积下限/上限（JSON），
  例如 ``{"中型冷藏车": {"min": 15, "max": 40}}``；
- ``VEHICLE_UNIT_WHITELIST``：允许出车的制冷机组型号白名单（JSON 数组）。

参数只在「已生效」状态下参与判定；缺省或解析失败时对应一条规则不生效，
调整参数并刷新列表后立即按新口径重新判定。
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.store import store

MODULE = "vehicle"
SETTING_MODULE = "setting"
REQUIRED_FIELDS = ["车牌号码", "车辆类型", "制冷机组型号"]
STATUS_ORDER = ["可用", "出车中", "维修中", "已停用"]
DISABLED_STATUS = STATUS_ORDER[-1]
ACTION_RULES = {"安排出车": "出车中", "回场登记": "可用", "停用车辆": "已停用"}
NEGATIVE_ACTIONS = ["停用车辆"]

VOLUME_RULE_CODE = "VEHICLE_VOLUME_RULES"
UNIT_WHITELIST_CODE = "VEHICLE_UNIT_WHITELIST"
ACTIVE_SETTING_STATUS = "已生效"

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_number(value: Any) -> float | None:
    """把「28」「28m³」这类容积值解析成数字；解析不出来返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER_RE.search(str(value or ""))
    return float(match.group()) if match else None


def _active_param(code: str) -> Any:
    """读取一条已生效的系统参数原始值；找不到或未生效时返回 None。"""
    for row in store.rows(SETTING_MODULE):
        if row.get("参数编码") == code and row.get("status") == ACTIVE_SETTING_STATUS:
            return row.get("参数值")
    return None


def load_dispatch_rules() -> dict[str, Any]:
    """解析出车准用规则；非法 JSON 视为该规则未配置，保证不拖垮列表。"""
    rules: dict[str, Any] = {"volume": {}, "unit_whitelist": []}

    raw_volume = _active_param(VOLUME_RULE_CODE)
    if raw_volume is not None:
        try:
            parsed = json.loads(str(raw_volume))
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            rules["volume"] = parsed

    raw_whitelist = _active_param(UNIT_WHITELIST_CODE)
    if raw_whitelist is not None:
        try:
            parsed = json.loads(str(raw_whitelist))
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            rules["unit_whitelist"] = [str(item).strip() for item in parsed if str(item).strip()]

    return rules


def evaluate_dispatch(entry: dict[str, Any], rules: dict[str, Any] | None = None) -> list[str]:
    """返回车辆不满足出车准用条件的原因列表；空列表表示可以安排出车。

    已停用车辆的判断与参数规则合在一起，任一条件不满足都会列出原因。
    """
    reasons: list[str] = []
    if entry.get("status") == DISABLED_STATUS:
        reasons.append("车辆已停用，不允许安排出车")

    if rules is None:
        rules = load_dispatch_rules()

    vehicle_type = str(entry.get("车辆类型") or "").strip()
    volume = _to_number(entry.get("车厢容积"))
    range_rule = rules.get("volume", {}).get(vehicle_type)
    if isinstance(range_rule, dict):
        lower = _to_number(range_rule.get("min"))
        upper = _to_number(range_rule.get("max"))
        lower_text = f"{lower:g}" if lower is not None else "不限"
        upper_text = f"{upper:g}" if upper is not None else "不限"
        if volume is None:
            reasons.append(
                f"车厢容积未登记，{vehicle_type}要求在{lower_text}~{upper_text}立方米之间"
            )
        else:
            if lower is not None and volume < lower:
                reasons.append(f"车厢容积{volume:g}立方米，低于{vehicle_type}准用下限{lower_text}立方米")
            if upper is not None and volume > upper:
                reasons.append(f"车厢容积{volume:g}立方米，高于{vehicle_type}准用上限{upper_text}立方米")

    whitelist = rules.get("unit_whitelist", [])
    unit_model = str(entry.get("制冷机组型号") or "").strip()
    if whitelist and unit_model not in whitelist:
        reasons.append(f"制冷机组型号「{unit_model or '未登记'}」不在准用白名单内")

    return reasons


def annotate_entry(entry: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """给车辆记录附带上出车准用判定结果，列表页与详情页共用同一份口径。"""
    reasons = evaluate_dispatch(entry, rules)
    annotated = dict(entry)
    annotated["准用状态"] = "可出车" if not reasons else "限制出车"
    annotated["准用说明"] = "符合出车准用条件" if not reasons else "；".join(reasons)
    return annotated


class VehicleService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        dispatchable: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("车牌号码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]

        rules = load_dispatch_rules()
        annotated = [annotate_entry(row, rules) for row in rows]
        if dispatchable in ("true", "false"):
            expected = dispatchable == "true"
            annotated = [row for row in annotated if (row["准用状态"] == "可出车") is expected]

        total = len(annotated)
        start = max(page - 1, 0) * size
        return annotated[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return annotate_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 准用条件还要校验车厢容积，登记时一并落库，缺省时由判定逻辑给出说明。
        if values.get("车厢容积") is not None:
            entry["车厢容积"] = values.get("车厢容积")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return annotate_entry(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"冷藏车辆 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于冷藏车管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == "安排出车":
            reasons = evaluate_dispatch(entry)
            if reasons:
                return None, "不允许安排出车：" + "；".join(reasons)
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return annotate_entry(entry), f"冷藏车辆已{action}"
