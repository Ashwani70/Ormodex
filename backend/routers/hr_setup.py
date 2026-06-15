"""HR Setup: branches, departments, designations, shifts, holidays, leave types."""
from typing import Optional

from fastapi import APIRouter, Depends

from core.auth_utils import get_current_user, require_hr_or_admin
from core.hr_models import Branch, Department, Designation, Holiday, LeaveType, Shift
from core.utils import crud_create, crud_delete, crud_list, crud_update

router = APIRouter(prefix="/hr", tags=["hr-setup"])


# ------- Branches -------
@router.get("/branches")
async def list_branches(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("hr_branches", q, ["name", "location", "code"], sort_field="name")


@router.post("/branches")
async def create_branch(payload: Branch, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("hr_branches", payload.model_dump())


@router.put("/branches/{item_id}")
async def update_branch(item_id: str, payload: Branch, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("hr_branches", item_id, payload.model_dump())


@router.delete("/branches/{item_id}")
async def delete_branch(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("hr_branches", item_id)


# ------- Departments -------
@router.get("/departments")
async def list_departments(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("hr_departments", q, ["name"], sort_field="name")


@router.post("/departments")
async def create_department(payload: Department, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("hr_departments", payload.model_dump())


@router.put("/departments/{item_id}")
async def update_department(item_id: str, payload: Department, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("hr_departments", item_id, payload.model_dump())


@router.delete("/departments/{item_id}")
async def delete_department(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("hr_departments", item_id)


# ------- Designations -------
@router.get("/designations")
async def list_designations(_: dict = Depends(get_current_user)):
    return await crud_list("hr_designations", sort_field="name")


@router.post("/designations")
async def create_designation(payload: Designation, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("hr_designations", payload.model_dump())


@router.put("/designations/{item_id}")
async def update_designation(item_id: str, payload: Designation, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("hr_designations", item_id, payload.model_dump())


@router.delete("/designations/{item_id}")
async def delete_designation(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("hr_designations", item_id)


# ------- Shifts -------
@router.get("/shifts")
async def list_shifts(_: dict = Depends(get_current_user)):
    return await crud_list("shifts", sort_field="name")


@router.post("/shifts")
async def create_shift(payload: Shift, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("shifts", payload.model_dump())


@router.put("/shifts/{item_id}")
async def update_shift(item_id: str, payload: Shift, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("shifts", item_id, payload.model_dump())


@router.delete("/shifts/{item_id}")
async def delete_shift(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("shifts", item_id)


# ------- Holidays -------
@router.get("/holidays")
async def list_holidays(_: dict = Depends(get_current_user)):
    return await crud_list("holidays", sort_field="date")


@router.post("/holidays")
async def create_holiday(payload: Holiday, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("holidays", payload.model_dump())


@router.put("/holidays/{item_id}")
async def update_holiday(item_id: str, payload: Holiday, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("holidays", item_id, payload.model_dump())


@router.delete("/holidays/{item_id}")
async def delete_holiday(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("holidays", item_id)


# ------- Leave Types -------
@router.get("/leave-types")
async def list_leave_types(_: dict = Depends(get_current_user)):
    return await crud_list("leave_types", sort_field="name")


@router.post("/leave-types")
async def create_leave_type(payload: LeaveType, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("leave_types", payload.model_dump())


@router.put("/leave-types/{item_id}")
async def update_leave_type(item_id: str, payload: LeaveType, _: dict = Depends(require_hr_or_admin)):
    return await crud_update("leave_types", item_id, payload.model_dump())


@router.delete("/leave-types/{item_id}")
async def delete_leave_type(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("leave_types", item_id)
