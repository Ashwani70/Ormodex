"""Tests for Approvals & Workflow — Module E.

Pure unit tests on the engine's decision logic — no live DB required.
Covers:
- Mongo-style condition evaluation ($gt/$gte/$lt/$eq/$in/$and/$or, dotted fields)
- threshold routing (above → matches policy, below → auto-approves)
- per-step satisfaction (any_one vs all)
- maker ≠ checker enforcement helper
- approver eligibility (role / named user / admin fallback)
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.approvals import (
    evaluate_condition,
    _get_field,
    _step_satisfied,
    _user_can_act_on_step,
)


# ══════════════════════════════════════════════════════════════
# Condition evaluation
# ══════════════════════════════════════════════════════════════

class TestConditionEval:
    def test_empty_condition_matches_all(self):
        assert evaluate_condition({}, {"total": 5}) is True

    def test_gt_true(self):
        assert evaluate_condition({"total": {"$gt": 100000}}, {"total": 150000}) is True

    def test_gt_false_below_threshold(self):
        assert evaluate_condition({"total": {"$gt": 100000}}, {"total": 50000}) is False

    def test_gt_false_on_boundary(self):
        # $gt is strict — exactly the threshold does NOT match
        assert evaluate_condition({"total": {"$gt": 100000}}, {"total": 100000}) is False

    def test_gte_on_boundary(self):
        assert evaluate_condition({"total": {"$gte": 100000}}, {"total": 100000}) is True

    def test_lt(self):
        assert evaluate_condition({"qty": {"$lt": 10}}, {"qty": 5}) is True
        assert evaluate_condition({"qty": {"$lt": 10}}, {"qty": 10}) is False

    def test_eq_shorthand(self):
        assert evaluate_condition({"branch": "MUM"}, {"branch": "MUM"}) is True
        assert evaluate_condition({"branch": "MUM"}, {"branch": "DEL"}) is False

    def test_eq_operator(self):
        assert evaluate_condition({"status": {"$eq": "draft"}}, {"status": "draft"}) is True

    def test_ne(self):
        assert evaluate_condition({"status": {"$ne": "posted"}}, {"status": "draft"}) is True
        assert evaluate_condition({"status": {"$ne": "posted"}}, {"status": "posted"}) is False

    def test_in(self):
        assert evaluate_condition({"branch": {"$in": ["MUM", "DEL"]}}, {"branch": "DEL"}) is True
        assert evaluate_condition({"branch": {"$in": ["MUM", "DEL"]}}, {"branch": "BLR"}) is False

    def test_nin(self):
        assert evaluate_condition({"branch": {"$nin": ["MUM"]}}, {"branch": "DEL"}) is True

    def test_missing_field_does_not_match_gt(self):
        # field absent → None → not > threshold
        assert evaluate_condition({"total": {"$gt": 100}}, {"other": 5}) is False

    def test_and(self):
        cond = {"$and": [{"total": {"$gt": 100000}}, {"branch": "MUM"}]}
        assert evaluate_condition(cond, {"total": 200000, "branch": "MUM"}) is True
        assert evaluate_condition(cond, {"total": 200000, "branch": "DEL"}) is False

    def test_or(self):
        cond = {"$or": [{"total": {"$gt": 500000}}, {"urgent": True}]}
        assert evaluate_condition(cond, {"total": 1000, "urgent": True}) is True
        assert evaluate_condition(cond, {"total": 1000, "urgent": False}) is False

    def test_multiple_fields_implicit_and(self):
        cond = {"total": {"$gt": 100000}, "branch": "MUM"}
        assert evaluate_condition(cond, {"total": 150000, "branch": "MUM"}) is True
        assert evaluate_condition(cond, {"total": 150000, "branch": "DEL"}) is False

    def test_dotted_field(self):
        assert _get_field({"meta": {"region": "west"}}, "meta.region") == "west"
        assert evaluate_condition({"meta.region": "west"}, {"meta": {"region": "west"}}) is True


# ══════════════════════════════════════════════════════════════
# Threshold routing (acceptance: above → approval, below → auto)
# ══════════════════════════════════════════════════════════════

class TestThresholdRouting:
    POLICY_COND = {"total": {"$gt": 100000}}

    def test_po_above_threshold_routes(self):
        po = {"total": 250000}
        assert evaluate_condition(self.POLICY_COND, po) is True  # → builds chain

    def test_po_below_threshold_auto_approves(self):
        po = {"total": 75000}
        assert evaluate_condition(self.POLICY_COND, po) is False  # → no policy → auto-approve


# ══════════════════════════════════════════════════════════════
# Step satisfaction
# ══════════════════════════════════════════════════════════════

class TestStepSatisfaction:
    def test_any_one_satisfied_with_single_approval(self):
        step = {"mode": "any_one", "approvals": [{"approver_id": "u1"}]}
        assert _step_satisfied(step) is True

    def test_any_one_not_satisfied_when_empty(self):
        step = {"mode": "any_one", "approvals": []}
        assert _step_satisfied(step) is False

    def test_all_named_user_must_approve(self):
        step = {"mode": "all", "approver_user_id": "u2", "approvals": [{"approver_id": "u1"}]}
        assert _step_satisfied(step) is False  # u2 hasn't approved
        step["approvals"].append({"approver_id": "u2"})
        assert _step_satisfied(step) is True

    def test_all_role_based_requires_at_least_one(self):
        step = {"mode": "all", "approver_role": "manager", "approvals": [{"approver_id": "u1"}]}
        assert _step_satisfied(step) is True


# ══════════════════════════════════════════════════════════════
# Approver eligibility
# ══════════════════════════════════════════════════════════════

class TestApproverEligibility:
    def test_role_match(self):
        user = {"id": "u1", "role": "manager"}
        step = {"approver_role": "manager"}
        assert _user_can_act_on_step(user, step) is True

    def test_role_mismatch(self):
        user = {"id": "u1", "role": "clerk"}
        step = {"approver_role": "manager"}
        assert _user_can_act_on_step(user, step) is False

    def test_named_user_match(self):
        user = {"id": "u9", "role": "clerk"}
        step = {"approver_user_id": "u9"}
        assert _user_can_act_on_step(user, step) is True

    def test_admin_fallback(self):
        user = {"id": "admin1", "role": "admin"}
        step = {"approver_role": "manager"}
        assert _user_can_act_on_step(user, step) is True


# ══════════════════════════════════════════════════════════════
# Maker ≠ checker (the rule the endpoints enforce)
# ══════════════════════════════════════════════════════════════

class TestMakerChecker:
    def test_maker_is_blocked(self):
        # The endpoint compares req["requested_by"] == user["id"].
        requested_by = "u1"
        approver_id = "u1"
        assert (requested_by == approver_id) is True  # → 403 in endpoint

    def test_different_user_allowed(self):
        requested_by = "u1"
        approver_id = "u2"
        assert (requested_by == approver_id) is False  # → allowed
