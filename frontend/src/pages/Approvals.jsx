import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

// ── Reusable inline UI (matches the codebase's dark-theme pattern) ──
const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 ${className}`} style={{ borderRadius: "var(--radius)" }}>
    {children}
  </div>
);

const SectionHeader = ({ title, subtitle, right }) => (
  <div className="flex items-start justify-between mb-4">
    <div>
      <h2 className="font-display font-black text-zinc-50 text-lg tracking-tight">{title}</h2>
      {subtitle && <p className="text-zinc-500 text-sm mt-0.5">{subtitle}</p>}
    </div>
    {right}
  </div>
);

const STATE_STYLES = {
  draft: "bg-zinc-700/30 text-zinc-300 border-zinc-600",
  pending: "bg-amber-500/15 text-amber-400 border-amber-600",
  approved: "bg-emerald-500/15 text-emerald-400 border-emerald-600",
  posted: "bg-blue-500/15 text-blue-400 border-blue-600",
  rejected: "bg-red-500/15 text-red-400 border-red-600",
  returned: "bg-orange-500/15 text-orange-400 border-orange-600",
};

const StatusBadge = ({ status }) => (
  <span className={`inline-block px-2 py-0.5 text-[11px] font-mono uppercase tracking-wider border ${STATE_STYLES[status] || STATE_STYLES.draft}`}>
    {status}
  </span>
);

const Btn = ({ children, onClick, variant = "primary", disabled, className = "", type = "button" }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
    danger: "border border-red-700 text-red-400 hover:bg-red-500/10",
    success: "border border-emerald-700 text-emerald-400 hover:bg-emerald-500/10",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2 text-sm font-mono uppercase tracking-wider transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
      style={{ borderRadius: "var(--radius)" }}
    >
      {children}
    </button>
  );
};

const Input = ({ label, ...props }) => (
  <label className="block">
    {label && <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-1">{label}</span>}
    <input
      {...props}
      className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
      style={{ borderRadius: "var(--radius)" }}
    />
  </label>
);

const Select = ({ label, children, ...props }) => (
  <label className="block">
    {label && <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-1">{label}</span>}
    <select
      {...props}
      className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
      style={{ borderRadius: "var(--radius)" }}
    >
      {children}
    </select>
  </label>
);

const ENTITY_TYPES = [
  "purchase_order", "sales_order", "voucher", "expense",
  "payment", "debit_note", "credit_note", "grn", "payroll_run",
];

const OPERATORS = [
  { value: "$gt", label: "greater than (>)" },
  { value: "$gte", label: "greater or equal (≥)" },
  { value: "$lt", label: "less than (<)" },
  { value: "$lte", label: "less or equal (≤)" },
  { value: "$eq", label: "equals (=)" },
  { value: "$ne", label: "not equals (≠)" },
];

const fmtMoney = (v) =>
  v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN", { minimumFractionDigits: 0 });

// ══════════════════════════════════════════════════════════════
// Tab: My Approval Inbox
// ══════════════════════════════════════════════════════════════
function InboxTab() {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null); // request being acted on
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/approvals/my-queue");
      setQueue(data);
    } catch (e) {
      toast.error("Failed to load approval queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (requestId, action) => {
    try {
      await api.post(`/approvals/approval-requests/${requestId}/${action}`, { comment });
      toast.success(`Request ${action}d`);
      setActive(null);
      setComment("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Failed to ${action}`);
    }
  };

  if (loading) return <p className="text-zinc-500 text-sm">Loading queue…</p>;

  return (
    <div>
      <SectionHeader
        title="My Approval Inbox"
        subtitle="Documents awaiting your action on the current step"
        right={<Btn variant="ghost" onClick={load}>Refresh</Btn>}
      />
      {queue.length === 0 ? (
        <Card className="p-8 text-center text-zinc-500 text-sm">Your inbox is empty 🎉</Card>
      ) : (
        <div className="space-y-3">
          {queue.map((q) => (
            <Card key={q.request_id} className="p-4">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs uppercase tracking-wider text-zinc-500">
                      {q.entity_type.replace(/_/g, " ")}
                    </span>
                    <span className="text-zinc-100 font-semibold">{q.entity_label}</span>
                    <span className="text-yellow-400 font-mono">{fmtMoney(q.amount)}</span>
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    Step {q.current_step + 1}/{q.total_steps} · mode {q.step_mode} · SLA {q.sla_hours}h ·
                    raised by {q.requested_by_name}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Btn variant="success" onClick={() => setActive({ ...q, action: "approve" })}>Approve</Btn>
                  <Btn variant="ghost" onClick={() => setActive({ ...q, action: "return" })}>Return</Btn>
                  <Btn variant="danger" onClick={() => setActive({ ...q, action: "reject" })}>Reject</Btn>
                </div>
              </div>

              {active?.request_id === q.request_id && (
                <div className="mt-4 pt-4 border-t border-zinc-800 space-y-3">
                  <Input
                    label={`Comment (${active.action})`}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Optional remarks…"
                  />
                  <div className="flex gap-2">
                    <Btn
                      variant={active.action === "reject" ? "danger" : active.action === "return" ? "ghost" : "success"}
                      onClick={() => act(q.request_id, active.action)}
                    >
                      Confirm {active.action}
                    </Btn>
                    <Btn variant="ghost" onClick={() => { setActive(null); setComment(""); }}>Cancel</Btn>
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Tab: Policy Designer
// ══════════════════════════════════════════════════════════════
function PolicyTab() {
  const [policies, setPolicies] = useState([]);
  const [steps, setSteps] = useState({}); // policy_id → steps[]
  const [showNew, setShowNew] = useState(false);

  const [pol, setPol] = useState({
    name: "", entity_type: "purchase_order", field: "total", op: "$gt", value: "100000", branch_scope: "",
  });
  const [stepForm, setStepForm] = useState({}); // policy_id → {approver_role, mode, sla_hours}

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/approvals/approval-policies");
      setPolicies(data);
      const stepMap = {};
      await Promise.all(
        data.map(async (p) => {
          const { data: s } = await api.get("/approvals/approval-steps", { params: { policy_id: p.id } });
          stepMap[p.id] = s;
        })
      );
      setSteps(stepMap);
    } catch (e) {
      toast.error("Failed to load policies");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createPolicy = async () => {
    if (!pol.name) return toast.error("Policy needs a name");
    const condition = pol.value === ""
      ? {}
      : { [pol.field]: { [pol.op]: isNaN(Number(pol.value)) ? pol.value : Number(pol.value) } };
    try {
      await api.post("/approvals/approval-policies", {
        name: pol.name,
        entity_type: pol.entity_type,
        condition,
        branch_scope: pol.branch_scope || null,
        active: true,
        priority: 0,
      });
      toast.success("Policy created");
      setShowNew(false);
      setPol({ name: "", entity_type: "purchase_order", field: "total", op: "$gt", value: "100000", branch_scope: "" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create policy");
    }
  };

  const addStep = async (policyId) => {
    const f = stepForm[policyId] || {};
    if (!f.approver_role) return toast.error("Choose an approver role");
    const seq = (steps[policyId]?.length || 0) + 1;
    try {
      await api.post("/approvals/approval-steps", {
        policy_id: policyId,
        sequence: seq,
        approver_role: f.approver_role,
        mode: f.mode || "any_one",
        sla_hours: Number(f.sla_hours || 24),
      });
      toast.success(`Step ${seq} added`);
      setStepForm((s) => ({ ...s, [policyId]: {} }));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add step");
    }
  };

  const delStep = async (stepId) => {
    try {
      await api.delete(`/approvals/approval-steps/${stepId}`);
      load();
    } catch (e) {
      toast.error("Failed to delete step");
    }
  };

  const condText = (c) => {
    if (!c || Object.keys(c).length === 0) return "matches all documents";
    const [field, spec] = Object.entries(c)[0];
    if (typeof spec === "object") {
      const [op, val] = Object.entries(spec)[0];
      const opLabel = OPERATORS.find((o) => o.value === op)?.label || op;
      return `${field} ${opLabel} ${val}`;
    }
    return `${field} = ${spec}`;
  };

  return (
    <div>
      <SectionHeader
        title="Approval Policies"
        subtitle="Condition → step ladder. Empty condition matches everything."
        right={<Btn onClick={() => setShowNew((v) => !v)}>{showNew ? "Cancel" : "+ New Policy"}</Btn>}
      />

      {showNew && (
        <Card className="p-5 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input label="Policy Name" value={pol.name} onChange={(e) => setPol({ ...pol, name: e.target.value })} placeholder="PO above ₹1L needs manager" />
            <Select label="Entity Type" value={pol.entity_type} onChange={(e) => setPol({ ...pol, entity_type: e.target.value })}>
              {ENTITY_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </Select>
          </div>
          <div className="mt-4">
            <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-2">Condition (leave value blank to match all)</span>
            <div className="grid grid-cols-3 gap-3">
              <Input value={pol.field} onChange={(e) => setPol({ ...pol, field: e.target.value })} placeholder="field e.g. total" />
              <Select value={pol.op} onChange={(e) => setPol({ ...pol, op: e.target.value })}>
                {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Input value={pol.value} onChange={(e) => setPol({ ...pol, value: e.target.value })} placeholder="100000" />
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input label="Branch Scope (optional)" value={pol.branch_scope} onChange={(e) => setPol({ ...pol, branch_scope: e.target.value })} placeholder="blank = all branches" />
          </div>
          <div className="mt-4">
            <Btn onClick={createPolicy}>Create Policy</Btn>
          </div>
        </Card>
      )}

      <div className="space-y-4">
        {policies.map((p) => (
          <Card key={p.id} className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-display font-bold text-zinc-50">{p.name}</h3>
                <div className="text-xs text-zinc-500 mt-1 font-mono">
                  {p.entity_type.replace(/_/g, " ")} · <span className="text-yellow-400">{condText(p.condition)}</span>
                  {p.branch_scope && ` · branch ${p.branch_scope}`}
                </div>
              </div>
              <StatusBadge status={p.active ? "approved" : "draft"} />
            </div>

            {/* Step ladder */}
            <div className="mt-4 space-y-2">
              {(steps[p.id] || []).map((s) => (
                <div key={s.id} className="flex items-center gap-3 bg-zinc-950 px-3 py-2 border border-zinc-800" style={{ borderRadius: "var(--radius)" }}>
                  <span className="w-6 h-6 bg-yellow-400 text-black font-display font-black text-sm flex items-center justify-center">{s.sequence}</span>
                  <span className="text-zinc-200 text-sm flex-1">
                    Approver role <b className="text-yellow-400">{s.approver_role || s.approver_user_id}</b> · mode {s.mode} · SLA {s.sla_hours}h
                  </span>
                  <button onClick={() => delStep(s.id)} className="text-red-400 hover:text-red-300 text-xs font-mono">remove</button>
                </div>
              ))}
            </div>

            {/* Add step */}
            <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
              <Input
                label="Approver Role"
                value={stepForm[p.id]?.approver_role || ""}
                onChange={(e) => setStepForm((s) => ({ ...s, [p.id]: { ...s[p.id], approver_role: e.target.value } }))}
                placeholder="manager"
              />
              <Select
                label="Mode"
                value={stepForm[p.id]?.mode || "any_one"}
                onChange={(e) => setStepForm((s) => ({ ...s, [p.id]: { ...s[p.id], mode: e.target.value } }))}
              >
                <option value="any_one">any one</option>
                <option value="all">all</option>
              </Select>
              <Input
                label="SLA hours"
                type="number"
                value={stepForm[p.id]?.sla_hours || ""}
                onChange={(e) => setStepForm((s) => ({ ...s, [p.id]: { ...s[p.id], sla_hours: e.target.value } }))}
                placeholder="24"
              />
              <Btn variant="ghost" onClick={() => addStep(p.id)}>+ Add Step</Btn>
            </div>
          </Card>
        ))}
        {policies.length === 0 && (
          <Card className="p-8 text-center text-zinc-500 text-sm">No policies yet. Create one above.</Card>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Tab: All Requests + timeline
// ══════════════════════════════════════════════════════════════
function RequestsTab() {
  const [requests, setRequests] = useState([]);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/approvals/approval-requests", { params: { status: filter || undefined } });
      setRequests(data);
    } catch (e) {
      toast.error("Failed to load requests");
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <SectionHeader
        title="Approval Requests"
        subtitle="Every routed document and its timeline"
        right={
          <Select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="returned">Returned</option>
          </Select>
        }
      />
      <div className="space-y-2">
        {requests.map((r) => (
          <Card key={r.id} className="p-4">
            <div className="flex items-center justify-between cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <div>
                <span className="text-zinc-100 font-semibold">{r.entity_label}</span>
                <span className="text-xs text-zinc-500 ml-2 font-mono">{r.entity_type.replace(/_/g, " ")}</span>
                <span className="text-yellow-400 font-mono ml-2">{fmtMoney(r.amount)}</span>
              </div>
              <div className="flex items-center gap-3">
                {r.sla_breached && <span className="text-[11px] font-mono text-red-400 uppercase">SLA breached</span>}
                <span className="text-xs text-zinc-500">step {r.current_step + 1}/{r.chain?.length}</span>
                <StatusBadge status={r.status} />
              </div>
            </div>

            {open === r.id && (
              <div className="mt-4 pt-4 border-t border-zinc-800">
                <div className="text-xs font-mono uppercase tracking-wider text-zinc-500 mb-2">Timeline</div>
                <ol className="space-y-2">
                  <li className="text-sm text-zinc-400">
                    ▸ Raised by <b className="text-zinc-200">{r.requested_by_name}</b> · {r.created_at?.slice(0, 16).replace("T", " ")}
                  </li>
                  {(r.actions || []).map((a, i) => (
                    <li key={i} className="text-sm text-zinc-400">
                      ▸ Step {a.step + 1} · <b className="text-zinc-200">{a.approver}</b> ·{" "}
                      <span className={
                        a.action === "approve" ? "text-emerald-400" :
                        a.action === "reject" ? "text-red-400" :
                        a.action === "return" ? "text-orange-400" : "text-amber-400"
                      }>{a.action}</span>
                      {a.comment && <span className="text-zinc-500"> — “{a.comment}”</span>}
                      <span className="text-zinc-600 ml-2 text-xs">{a.ts?.slice(0, 16).replace("T", " ")}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>
        ))}
        {requests.length === 0 && (
          <Card className="p-8 text-center text-zinc-500 text-sm">No requests match.</Card>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Page shell
// ══════════════════════════════════════════════════════════════
const TABS = [
  { id: "inbox", label: "My Inbox" },
  { id: "policies", label: "Policy Designer" },
  { id: "requests", label: "All Requests" },
];

export default function Approvals() {
  const [tab, setTab] = useState("inbox");

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Approvals & Workflow</h1>
        <p className="text-zinc-500 text-sm mt-1">Configurable approval chains, maker-checker, and the draft→approved→posted state machine.</p>
      </div>

      <div className="flex gap-1 border-b border-zinc-800 mb-6">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-mono uppercase tracking-wider transition-colors border-b-2 -mb-px ${
              tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "inbox" && <InboxTab />}
      {tab === "policies" && <PolicyTab />}
      {tab === "requests" && <RequestsTab />}
    </div>
  );
}
