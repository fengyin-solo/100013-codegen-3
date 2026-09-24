"""冷藏车准用规则引擎。

规则的判定口径集中在这里：
1. 已停用车辆一律不允许安排出车；
2. 制冷机组型号必须在系统参数维护的准用白名单内；
3. 按车辆类型设定车厢容积的下限与上限，超出范围不予准用。

所有阈值都从系统参数表（setting）实时读取，只取「已生效」的参数值；
系统参数调整并生效后，下一次判定（刷新列表/详情）就按新口径执行。
参数缺省或无法解析时回退到代码内默认值，并在规则摘要里给出告警说明。
"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "setting"
PARAM_EFFECTIVE = "已生效"

# 制冷机组白名单参数编码
CODE_UNIT_WHITELIST = "VEHICLE_UNIT_WHITELIST"
# 车厢容积范围参数编码前缀，完整编码为 前缀:车辆类型
CODE_VOLUME_RANGE_PREFIX = "VEHICLE_VOLUME_RANGE:"

DEFAULT_UNIT_WHITELIST = ["CoolMax-500", "FrostKing-800", "ThermoStar-T1000", "IcePower-300"]
DEFAULT_VOLUME_RANGES: dict[str, tuple[float, float]] = {
    "小型冷藏车": (5.0, 15.0),
    "中型冷藏车": (15.0, 30.0),
    "大型冷藏车": (30.0, 60.0),
}

STOPPED_STATUS = "已停用"

_SPLIT_PATTERN = re.compile(r"[，,、；;\n\r\t]+")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _effective_param(code: str) -> str | None:
    """读取已生效的系统参数值；参数不存在或不是生效态时返回 None。"""
    for row in store.rows(MODULE):
        if row.get("参数编码") == code and row.get("status") == PARAM_EFFECTIVE:
            value = row.get("参数值")
            return "" if value is None else str(value)
    return None


def _parse_whitelist(raw: str) -> list[str]:
    return [item.strip() for item in _SPLIT_PATTERN.split(raw) if item.strip()]


def _parse_range(raw: str) -> tuple[float, float] | None:
    """解析「下限-上限」格式，容忍 ~ ～ 至 逗号以及 m³/立方米 等前后缀。"""
    numbers = _NUMBER_PATTERN.findall(raw)
    if len(numbers) < 2:
        return None
    low, high = float(numbers[0]), float(numbers[1])
    if low > high:
        low, high = high, low
    return low, high


def _parse_volume(raw: Any) -> float | None:
    """从「12.5m³」「12 立方米」等填写值里取出容积数值。"""
    if raw is None:
        return None
    match = _NUMBER_PATTERN.search(str(raw))
    return float(match.group()) if match else None


def load_rules() -> dict[str, Any]:
    """组装当前生效的准用规则；无法解析的参数回退默认值并记录告警。"""
    warnings: list[str] = []

    raw_whitelist = _effective_param(CODE_UNIT_WHITELIST)
    if raw_whitelist is None:
        whitelist = list(DEFAULT_UNIT_WHITELIST)
    else:
        whitelist = _parse_whitelist(raw_whitelist)
        if not whitelist:
            warnings.append(
                f"系统参数 {CODE_UNIT_WHITELIST} 的值无法解析出任何机组型号，已回退默认白名单"
            )
            whitelist = list(DEFAULT_UNIT_WHITELIST)

    volume_ranges: dict[str, tuple[float, float]] = {}
    for vehicle_type, default_range in DEFAULT_VOLUME_RANGES.items():
        code = f"{CODE_VOLUME_RANGE_PREFIX}{vehicle_type}"
        raw_range = _effective_param(code)
        if raw_range is None:
            volume_ranges[vehicle_type] = default_range
            continue
        parsed = _parse_range(raw_range)
        if parsed is None:
            warnings.append(
                f"系统参数 {code} 的值「{raw_range}」无法解析为下限-上限，已回退默认范围"
                f" {default_range[0]:g}~{default_range[1]:g}m³"
            )
            volume_ranges[vehicle_type] = default_range
        else:
            volume_ranges[vehicle_type] = parsed

    return {"whitelist": whitelist, "volume_ranges": volume_ranges, "warnings": warnings}


def rules_summary() -> dict[str, Any]:
    """给列表页/详情页展示当前生效口径：白名单、各车型容积上下限与参数告警。"""
    rules = load_rules()
    return {
        "unitWhitelist": rules["whitelist"],
        "volumeRanges": [
            {"vehicleType": vehicle_type, "min": low, "max": high}
            for vehicle_type, (low, high) in rules["volume_ranges"].items()
        ],
        "whitelistParamCode": CODE_UNIT_WHITELIST,
        "volumeRangeParamPrefix": CODE_VOLUME_RANGE_PREFIX,
        "warnings": rules["warnings"],
    }


def evaluate(entry: dict[str, Any]) -> dict[str, Any]:
    """判定单台冷藏车是否满足准用条件，返回准用状态与全部命中的限制原因。"""
    rules = load_rules()
    reasons: list[str] = []

    if entry.get("status") == STOPPED_STATUS:
        reasons.append("车辆已停用，不可安排出车")

    unit = str(entry.get("制冷机组型号") or "").strip()
    if unit not in rules["whitelist"]:
        joined = "、".join(rules["whitelist"])
        reasons.append(f"制冷机组型号「{unit or '未登记'}」不在准用白名单（{joined}）内")

    vehicle_type = str(entry.get("车辆类型") or "").strip()
    allowed_range = rules["volume_ranges"].get(vehicle_type)
    if allowed_range is not None:
        low, high = allowed_range
        volume = _parse_volume(entry.get("车厢容积"))
        if volume is None:
            reasons.append(
                f"车厢容积未登记有效数值，{vehicle_type}要求在 {low:g}~{high:g}m³ 之间"
            )
        elif volume < low:
            reasons.append(
                f"车厢容积 {volume:g}m³ 低于{vehicle_type}下限 {low:g}m³，不允许安排出车"
            )
        elif volume > high:
            reasons.append(
                f"车厢容积 {volume:g}m³ 高于{vehicle_type}上限 {high:g}m³，不允许安排出车"
            )

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "message": "；".join(reasons),
    }


def annotate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """给列表行/明细补充准用状态与说明，原记录字段保持不动。"""
    verdict = evaluate(entry)
    entry["准用状态"] = "准予出车" if verdict["eligible"] else "限制出车"
    entry["准用说明"] = "符合准用条件，可安排出车" if verdict["eligible"] else verdict["message"]
    entry["准用原因"] = verdict["reasons"]
    return entry
