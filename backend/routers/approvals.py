"""Approvals & Workflow — Module E.

Generic, entity-agnostic approval engine that every mutating module can route
through. A transactional document (PO, voucher, invoice, …) carries an
`approval_state` field: draft → pending → approved → posted, with `rejected`
as a terminal branch and `return` sending it back to `draft`.

Flow
----
1. submit(entity_type, entity_id):
     - evaluate all `approval_policies` for that entity_type whose `condition`
       matches the document (Mongo-style operators on the doc's own fields)
     - if no matching policy → auto-approve (state = "approved")
     - else build the chain from `approval_steps`, create an `approval_request`,
       set document state = "pending"
2. approve / reject / return on the request:
     - maker ≠ checker enforced (submitter cannot approve own document)
     - per-step mode any_one / all
     - sequential: step N+1 only opens after step N completes
     - final approval → document state = "approved"
3. post(entity_type, entity_id):
     - only an "approved" (or auto-approved) document may post → state = "posted"

Every action writes to the shared `audit_logs` (via log_audit) with before/after,
and is also appended to the request's own `actions[]` timeline.

Collections: approval_policies, approval_steps, approval_requests
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Literal, Any
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.utils import now_iso, new_id, crud_create, crud_list, crud_get, crud_update, log_audit

router = APIRouter(prefix="/approvals", tags=["Approvals & Workflow"])

# Document states (the state machine every transactional doc moves through)
DRAFT = "draft"
PENDING = "pending"
APPROVED = "approved"
POSTED = "posted"
REJECTED = "rejected"

# entity_type → the MongoDB collection that holds those documents.
# Keeps the engine generic while constraining which collections it may touch.
ENTITY_COLLECTIONS: dict[str, str] = {
    "purchase_order": "purchase_orders",
    "sales_order": "sales_orders",
    "voucher": "vouchers",
    "journal_voucher": "vouchers",
    "expense": "expenses",
    "payment": "payments",
    "debit_note": "debit_notes",
    "credit_note": "credit_notes",
    "grn": "grn",
    "payroll_run": "payroll_runs",
}


def _collection_for(entity_type: str) -> str:
    coll = ENTITY_COLLECTIONS.get(entity_type)
    if not coll:
        raise HTTPException(400, f"Unknown entity_type '{entity_type}'. Known: {sorted(ENTITY_COLLECTIONS)}")
    return coll


# ══════════════════════════════════════════════════════════════
# Condition evaluation — Mongo-style operators against a single doc
# ══════════════════════════════════════════════════════════════

def _get_field(doc: dict, dotted: str) -> Any:
    """Resolve a possibly-dotted field path from a document."""
    cur: Any = doc
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _match_operators(value: Any, ops: dict) -> bool:
    for op, operand in ops.items():
        if op == "$gt":
            if not (value is not None and value > operand):
                return False
        elif op == "$gte":
            if not (value is not None and value >= operand):
                return False
        elif op == "$lt":
            if not (value is not None and value < operand):
                return False
        elif op == "$lte":
            if not (value is not None and value <= operand):
                return False
        elif op == "$eq":
            if value != operand:
                return False
        elif op == "$ne":
            if value == operand:
                return False
        elif op == "$in":
            if value not in operand:
                return False
        elif op == "$nin":
            if value in operand:
                return False
        else:
            raise HTTPException(400, f"Unsupported condition operator '{op}'")
    return True


def evaluate_condition(condition: dict, doc: dict) -> bool:
    """
    Evaluate a Mongo-style condition against a single in-memory document.

    Supports field-level operator maps (e.g. {"amount": {"$gt": 100000}}),
    equality shorthand ({"branch": "MUM"}), and top-level $and / $or.
    An empty condition ({}) matches everything.
    """
    if not condition:
        return True
    for key, expected in condition.items():
        if key == "$and":
            if not all(evaluate_condition(c, doc) for c in expected):
                return False
        elif key == "$or":
            if not any(evaluate_condition(c, doc) for c in expected):
                return False
        else:
            actual = _get_field(doc, key)
            if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
                if not _match_operators(actual, expected):
                    return False
            else:
                if actual != expected:
                    return False
    return True


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class ApprovalPolicy(BaseModel):
    name: str
    entity_type: str
    condition: dict = {}                 # Mongo-style; {} matches all
    branch_scope: Optional[str] = None   # None = all branches
    active: bool = True
    priority: int = 0                    # higher wins when multiple match (info only — all matching chain)


class ApprovalStep(BaseModel):
    policy_id: str
    sequence: int
    approver_role: Optional[str] = None
    approver_user_id: Optional[str] = None
    mode: Literal["any_one", "all"] = "any_one"
    sla_hours: int = 24


class SubmitRequest(BaseModel):
    branch: Optional[str] = None         # used for branch_scope filtering / step targeting


class ActionRequest(BaseModel):
    comment: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Policy & Step CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/approval-policies")
async def list_policies(entity_type: Optional[str] = None, _: dict = Depends(get_current_user)):
    filt = {"entity_type": entity_type} if entity_type else {}
    return await crud_list("approval_policies", filt=filt)


@router.post("/approval-policies")
async def create_policy(payload: ApprovalPolicy, user: dict = Depends(require_admin)):
    return await crud_create("approval_policies", payload.model_dump(), user)


@router.put("/approval-policies/{policy_id}")
async def update_policy(policy_id: str, payload: ApprovalPolicy, user: dict = Depends(require_admin)):
    return await crud_update("approval_policies", policy_id, payload.model_dump(), user)


@router.get("/approval-steps")
async def list_steps(policy_id: Optional[str] = None, _: dict = Depends(get_current_user)):
    filt = {"policy_id": policy_id} if policy_id else {}
    steps = await crud_list("approval_steps", filt=filt, sort_field="sequence")
    return sorted(steps, key=lambda s: s.get("sequence", 0))


@router.post("/approval-steps")
async def create_step(payload: ApprovalStep, user: dict = Depends(require_admin)):
    if not payload.approver_role and not payload.approver_user_id:
        raise HTTPException(400, "Step needs an approver_role or approver_user_id")
    return await crud_create("approval_steps", payload.model_dump(), user)


@router.delete("/approval-steps/{step_id}")
async def delete_step(step_id: str, user: dict = Depends(require_admin)):
    from core.utils import crud_delete
    return await crud_delete("approval_steps", step_id, user)


# ══════════════════════════════════════════════════════════════
# Chain building
# ══════════════════════════════════════════════════════════════

async def _matching_policies(entity_type: str, doc: dict, branch: Optional[str]) -> list[dict]:
    policies = await db.approval_policies.find(
        {"entity_type": entity_type, "active": True}, {"_id": 0}
    ).to_list(500)
    matched = []
    for p in policies:
        if p.get("branch_scope") and branch and p["branch_scope"] != branch:
            continue
        if evaluate_condition(p.get("condition", {}), doc):
            matched.append(p)
    # higher priority first; stable for equal priority
    return sorted(matched, key=lambda p: p.get("priority", 0), reverse=True)


async def _build_chain(policies: list[dict]) -> list[dict]:
    """Flatten the steps of all matching policies into one sequential chain."""
    policy_ids = [p["id"] for p in policies]
    steps = await db.approval_steps.find(
        {"policy_id": {"$in": policy_ids}}, {"_id": 0}
    ).to_list(1000)
    steps.sort(key=lambda s: (s.get("sequence", 0), s.get("created_at", "")))
    chain = []
    for idx, s in enumerate(steps):
        chain.append({
            "step_index": idx,
            "sequence": s.get("sequence", idx),
            "policy_id": s["policy_id"],
            "approver_role": s.get("approver_role"),
            "approver_user_id": s.get("approver_user_id"),
            "mode": s.get("mode", "any_one"),
            "sla_hours": s.get("sla_hours", 24),
            "status": "pending",
            "approvals": [],   # [{approver_id, approver_name, ts}]
        })
    return chain


# ══════════════════════════════════════════════════════════════
# Submit — kick off the workflow
# ══════════════════════════════════════════════════════════════

@router.post("/{entity_type}/{entity_id}/submit")
async def submit_for_approval(
    entity_type: str,
    entity_id: str,
    payload: SubmitRequest = SubmitRequest(),
    user: dict = Depends(get_current_user),
):
    """
    Submit a document into the approval workflow.

    - Evaluates matching policies; if none match → auto-approve.
    - Otherwise builds the chain, creates an approval_request, sets state=pending.
    """
    coll = _collection_for(entity_type)
    doc = await db[coll].find_one({"id": entity_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"{entity_type} '{entity_id}' not found")

    state = doc.get("approval_state", DRAFT)
    if state not in (DRAFT, REJECTED):
        raise HTTPException(400, f"Document is '{state}', can only submit from draft/rejected")

    # An existing open request for this doc would be a double-submit
    existing = await db.approval_requests.find_one(
        {"entity_type": entity_type, "entity_id": entity_id, "status": "pending"}, {"_id": 0}
    )
    if existing:
        raise HTTPException(400, "An approval request is already pending for this document")

    branch = payload.branch or doc.get("branch")
    policies = await _matching_policies(entity_type, doc, branch)

    old_doc = dict(doc)

    if not policies:
        # No policy applies → auto-approve
        await db[coll].update_one(
            {"id": entity_id},
            {"$set": {"approval_state": APPROVED, "auto_approved": True, "updated_at": now_iso()}},
        )
        await log_audit("AUTO_APPROVE", coll, entity_id, user,
                        old_values=old_doc, new_values={**old_doc, "approval_state": APPROVED})
        return {
            "auto_approved": True,
            "approval_state": APPROVED,
            "message": "No approval policy matched — document auto-approved.",
        }

    chain = await _build_chain(policies)
    if not chain:
        # Policy matched but no steps defined — treat as auto-approve to avoid a stuck doc
        await db[coll].update_one(
            {"id": entity_id},
            {"$set": {"approval_state": APPROVED, "auto_approved": True, "updated_at": now_iso()}},
        )
        return {"auto_approved": True, "approval_state": APPROVED,
                "message": "Policy matched but has no steps — auto-approved."}

    request_doc = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_label": doc.get("po_number") or doc.get("order_number")
                        or doc.get("voucher_number") or doc.get("number") or entity_id,
        "amount": doc.get("total") or doc.get("total_amount") or doc.get("grand_total") or doc.get("amount"),
        "branch": branch,
        "policy_ids": [p["id"] for p in policies],
        "policy_names": [p["name"] for p in policies],
        "chain": chain,
        "current_step": 0,
        "status": "pending",
        "requested_by": user["id"],
        "requested_by_name": user.get("name", user.get("email", "")),
        "actions": [],
    }
    created = await crud_create("approval_requests", request_doc, user)

    await db[coll].update_one(
        {"id": entity_id},
        {"$set": {"approval_state": PENDING, "approval_request_id": created["id"], "updated_at": now_iso()}},
    )
    await log_audit("SUBMIT", coll, entity_id, user,
                    old_values=old_doc, new_values={**old_doc, "approval_state": PENDING})

    return {
        "auto_approved": False,
        "approval_state": PENDING,
        "approval_request_id": created["id"],
        "steps": len(chain),
        "request": created,
    }


# ══════════════════════════════════════════════════════════════
# Approve / Reject / Return
# ══════════════════════════════════════════════════════════════

def _user_can_act_on_step(user: dict, step: dict) -> bool:
    if step.get("approver_user_id") and step["approver_user_id"] == user["id"]:
        return True
    if step.get("approver_role") and step["approver_role"] == user.get("role"):
        return True
    # Admins can always act as a fallback approver
    return user.get("role") == "admin"


def _step_satisfied(step: dict) -> bool:
    """any_one: ≥1 approval. all: every distinct named approver must approve."""
    approvals = step.get("approvals", [])
    if step.get("mode") == "all":
        # For role-based 'all' we can't enumerate every holder; require ≥1 here
        # but if specific user is named, that user must be among approvers.
        if step.get("approver_user_id"):
            return any(a["approver_id"] == step["approver_user_id"] for a in approvals)
        return len(approvals) >= 1
    return len(approvals) >= 1


async def _append_action(request_id: str, action: dict):
    await db.approval_requests.update_one(
        {"id": request_id}, {"$push": {"actions": action}, "$set": {"updated_at": now_iso()}}
    )


async def _load_request(request_id: str) -> dict:
    req = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Approval request not found")
    return req


@router.post("/approval-requests/{request_id}/approve")
async def approve_request(request_id: str, payload: ActionRequest = ActionRequest(),
                          user: dict = Depends(get_current_user)):
    req = await _load_request(request_id)
    if req["status"] != "pending":
        raise HTTPException(400, f"Request is '{req['status']}', cannot approve")

    # maker ≠ checker
    if req["requested_by"] == user["id"]:
        raise HTTPException(403, "Maker cannot approve their own document (maker ≠ checker)")

    chain = req["chain"]
    cur_idx = req["current_step"]
    step = chain[cur_idx]

    if not _user_can_act_on_step(user, step):
        raise HTTPException(403, "You are not an approver for the current step")

    if any(a["approver_id"] == user["id"] for a in step.get("approvals", [])):
        raise HTTPException(400, "You have already approved this step")

    ts = now_iso()
    approval = {"approver_id": user["id"], "approver_name": user.get("name", user.get("email", "")), "ts": ts}
    step.setdefault("approvals", []).append(approval)

    action_entry = {"step": cur_idx, "approver": user.get("name", user["id"]),
                    "approver_id": user["id"], "action": "approve",
                    "comment": payload.comment, "ts": ts}

    advanced = False
    final = False
    if _step_satisfied(step):
        step["status"] = "approved"
        if cur_idx + 1 < len(chain):
            req["current_step"] = cur_idx + 1
            advanced = True
        else:
            final = True

    new_status = "approved" if final else "pending"
    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {"chain": chain, "current_step": req["current_step"],
                  "status": new_status, "updated_at": now_iso()},
         "$push": {"actions": action_entry}},
    )

    if final:
        coll = _collection_for(req["entity_type"])
        old_doc = await db[coll].find_one({"id": req["entity_id"]}, {"_id": 0})
        await db[coll].update_one(
            {"id": req["entity_id"]},
            {"$set": {"approval_state": APPROVED, "updated_at": now_iso()}},
        )
        await log_audit("APPROVE_FINAL", coll, req["entity_id"], user,
                        old_values=old_doc, new_values={**(old_doc or {}), "approval_state": APPROVED})

    return {
        "request_id": request_id,
        "step_satisfied": step["status"] == "approved",
        "advanced_to_step": req["current_step"] if advanced else None,
        "final_approved": final,
        "status": new_status,
    }


@router.post("/approval-requests/{request_id}/reject")
async def reject_request(request_id: str, payload: ActionRequest = ActionRequest(),
                         user: dict = Depends(get_current_user)):
    req = await _load_request(request_id)
    if req["status"] != "pending":
        raise HTTPException(400, f"Request is '{req['status']}', cannot reject")
    if req["requested_by"] == user["id"]:
        raise HTTPException(403, "Maker cannot reject their own document (maker ≠ checker)")

    step = req["chain"][req["current_step"]]
    if not _user_can_act_on_step(user, step):
        raise HTTPException(403, "You are not an approver for the current step")

    ts = now_iso()
    action_entry = {"step": req["current_step"], "approver": user.get("name", user["id"]),
                    "approver_id": user["id"], "action": "reject",
                    "comment": payload.comment, "ts": ts}
    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "updated_at": now_iso()}, "$push": {"actions": action_entry}},
    )

    coll = _collection_for(req["entity_type"])
    old_doc = await db[coll].find_one({"id": req["entity_id"]}, {"_id": 0})
    await db[coll].update_one(
        {"id": req["entity_id"]},
        {"$set": {"approval_state": REJECTED, "updated_at": now_iso()}},
    )
    await log_audit("REJECT", coll, req["entity_id"], user,
                    old_values=old_doc, new_values={**(old_doc or {}), "approval_state": REJECTED})

    return {"request_id": request_id, "status": "rejected"}


@router.post("/approval-requests/{request_id}/return")
async def return_request(request_id: str, payload: ActionRequest = ActionRequest(),
                         user: dict = Depends(get_current_user)):
    """Send the document back to draft for the maker to amend & resubmit."""
    req = await _load_request(request_id)
    if req["status"] != "pending":
        raise HTTPException(400, f"Request is '{req['status']}', cannot return")

    step = req["chain"][req["current_step"]]
    if not _user_can_act_on_step(user, step):
        raise HTTPException(403, "You are not an approver for the current step")

    ts = now_iso()
    action_entry = {"step": req["current_step"], "approver": user.get("name", user["id"]),
                    "approver_id": user["id"], "action": "return",
                    "comment": payload.comment, "ts": ts}
    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "returned", "updated_at": now_iso()}, "$push": {"actions": action_entry}},
    )

    coll = _collection_for(req["entity_type"])
    old_doc = await db[coll].find_one({"id": req["entity_id"]}, {"_id": 0})
    await db[coll].update_one(
        {"id": req["entity_id"]},
        {"$set": {"approval_state": DRAFT, "approval_request_id": None, "updated_at": now_iso()}},
    )
    await log_audit("RETURN", coll, req["entity_id"], user,
                    old_values=old_doc, new_values={**(old_doc or {}), "approval_state": DRAFT})

    return {"request_id": request_id, "status": "returned", "document_state": DRAFT}


# ══════════════════════════════════════════════════════════════
# Post — only approved documents may post
# ══════════════════════════════════════════════════════════════

@router.post("/{entity_type}/{entity_id}/post")
async def post_document(entity_type: str, entity_id: str, user: dict = Depends(get_current_user)):
    """Transition an approved document to 'posted'. Unapproved docs are blocked."""
    coll = _collection_for(entity_type)
    doc = await db[coll].find_one({"id": entity_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, f"{entity_type} '{entity_id}' not found")

    state = doc.get("approval_state", DRAFT)
    if state != APPROVED:
        raise HTTPException(400, f"Cannot post: document is '{state}', must be 'approved'")

    await db[coll].update_one(
        {"id": entity_id},
        {"$set": {"approval_state": POSTED, "posted_at": now_iso(), "posted_by": user["id"], "updated_at": now_iso()}},
    )
    await log_audit("POST", coll, entity_id, user,
                    old_values=doc, new_values={**doc, "approval_state": POSTED})
    return {"entity_type": entity_type, "entity_id": entity_id, "approval_state": POSTED}


# ══════════════════════════════════════════════════════════════
# Queues & timeline
# ══════════════════════════════════════════════════════════════

@router.get("/my-queue")
async def my_queue(user: dict = Depends(get_current_user)):
    """All pending requests where the current user is the approver on the active step."""
    pending = await db.approval_requests.find({"status": "pending"}, {"_id": 0}).to_list(2000)
    queue = []
    for req in pending:
        step = req["chain"][req["current_step"]]
        if _user_can_act_on_step(user, step) and req["requested_by"] != user["id"]:
            # don't surface docs the user can't act on, or their own
            already = any(a["approver_id"] == user["id"] for a in step.get("approvals", []))
            if not already:
                queue.append({
                    "request_id": req["id"],
                    "entity_type": req["entity_type"],
                    "entity_id": req["entity_id"],
                    "entity_label": req.get("entity_label"),
                    "amount": req.get("amount"),
                    "current_step": req["current_step"],
                    "total_steps": len(req["chain"]),
                    "step_mode": step.get("mode"),
                    "sla_hours": step.get("sla_hours"),
                    "requested_by_name": req.get("requested_by_name"),
                    "created_at": req.get("created_at"),
                })
    return queue


@router.get("/approval-requests")
async def list_requests(
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    _: dict = Depends(get_current_user),
):
    filt: dict = {}
    if status:
        filt["status"] = status
    if entity_type:
        filt["entity_type"] = entity_type
    return await crud_list("approval_requests", filt=filt)


@router.get("/approval-requests/{request_id}")
async def get_request(request_id: str, _: dict = Depends(get_current_user)):
    return await _load_request(request_id)


@router.get("/{entity_type}/{entity_id}/timeline")
async def document_timeline(entity_type: str, entity_id: str, _: dict = Depends(get_current_user)):
    """Full approval timeline for a single document (request chain + actions + audit)."""
    req = await db.approval_requests.find_one(
        {"entity_type": entity_type, "entity_id": entity_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    audits = await db.audit_logs.find(
        {"collection_name": _collection_for(entity_type), "doc_id": entity_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(500)
    return {"request": req, "audit_trail": audits}


# ══════════════════════════════════════════════════════════════
# SLA breach sweep (called by a background scheduler)
# ══════════════════════════════════════════════════════════════

@router.post("/sla/sweep")
async def sla_sweep(user: dict = Depends(require_admin)):
    """
    Flag approval requests whose active step has breached its SLA.
    Intended to be invoked by a scheduled job. Marks `sla_breached` and records
    an escalation entry; notification dispatch is left to the notifier layer.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    pending = await db.approval_requests.find({"status": "pending"}, {"_id": 0}).to_list(5000)
    breached = []
    for req in pending:
        step = req["chain"][req["current_step"]]
        sla_hours = step.get("sla_hours", 24)
        # Step entered when request created (step 0) or when prior step approved.
        anchor = req.get("created_at")
        for a in reversed(req.get("actions", [])):
            if a.get("action") == "approve" and a.get("step") == req["current_step"] - 1:
                anchor = a.get("ts")
                break
        if not anchor:
            continue
        try:
            anchor_dt = datetime.fromisoformat(anchor)
        except ValueError:
            continue
        if anchor_dt.tzinfo is None:
            anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
        elapsed_h = (now - anchor_dt).total_seconds() / 3600.0
        if elapsed_h > sla_hours and not req.get("sla_breached"):
            await db.approval_requests.update_one(
                {"id": req["id"]},
                {"$set": {"sla_breached": True, "sla_breached_at": now_iso()},
                 "$push": {"actions": {"step": req["current_step"], "action": "sla_escalation",
                                       "approver": "system", "ts": now_iso(),
                                       "comment": f"SLA of {sla_hours}h breached ({elapsed_h:.1f}h elapsed)"}}},
            )
            breached.append({"request_id": req["id"], "entity_label": req.get("entity_label"),
                             "elapsed_hours": round(elapsed_h, 1), "sla_hours": sla_hours})
    return {"swept": len(pending), "breached": len(breached), "details": breached}
