"""冷藏车管理接口：维护冷藏车辆，覆盖安排出车、回场登记、停用车辆等动作。

列表与明细都会带上按系统参数实时计算的「准用状态/准用说明」；
安排出车接口在服务端再次校验准用条件，前端禁用按钮之外仍有兜底。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload
from app.services.vehicle import VehicleService

router = APIRouter(prefix="/api/vehicle", tags=["冷藏车管理"])

service = VehicleService()

LIST_FIELDS = ["车牌号码", "车辆类型", "制冷机组型号", "车厢容积", "温区数量", "所属车队", "年检到期日"]
STATUSES = ["可用", "出车中", "维修中", "已停用"]


@router.get("", response_model=dict)
def list_entries(
    keyword: str | None = Query(default=None, description="按车牌号码检索"),
    status: str | None = Query(default=None, description="可用、出车中、维修中、已停用"),
    eligible: bool | None = Query(default=None, description="是否只看满足准用条件的车辆"),
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """按车牌号码、状态与准用条件过滤冷藏车管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total, eligible_total = service.list_entries(
        keyword=keyword, status=status, eligible=eligible, page=page, size=size
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "eligibleTotal": eligible_total,
        "rules": service.eligibility_rules(),
    }


@router.get("/rules")
def eligibility_rules() -> dict[str, Any]:
    """读取当前生效的冷藏车准用规则：机组白名单与各车型容积上下限。"""
    return service.eligibility_rules()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出冷藏车管理清单：返回当前过滤条件下的全量数据。"""
    items, total, _ = service.list_entries(page=1, size=10000)
    return {"module": "vehicle", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条冷藏车辆明细（含准用判定说明）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"冷藏车辆 {entry_id} 不存在或已归档")
    entry["rules"] = service.eligibility_rules()
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条冷藏车辆，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="冷藏车辆已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条冷藏车辆执行安排出车、回场登记、停用车辆；不满足准用条件会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
