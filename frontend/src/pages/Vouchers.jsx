import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  PrimaryButton,
  SecondaryButton,
  Input,
  Select,
  Field,
  EmptyState,
  NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, RefreshCw, Search, Pencil, Trash2, X } from "lucide-react";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const VOUCHER_TYPES = [
  { value: "RECEIPT", label: "Receipt Voucher (RV)", color: "text-green-400" },
  { value: "PAYMENT", label: "Payment Voucher (PV)", color: "text-red-400" },
  { value: "CONTRA", label: "Contra Voucher (CV)", color: "text-blue-400" },
  { value: "JOURNAL", label: "Journal Voucher (JV)", color: "text-yellow-400" },
  { value: "DEBIT_NOTE", label: "Debit Note (DN)", color: "text-orange-400" },
  { value: "CREDIT_NOTE", label: "Credit Note (CN)", color: "text-purple-400" },
  { value: "EXPENSE", label: "Expense Voucher (EV)", color: "text-pink-400" },
];

const TYPE_COLORS = {
  RECEIPT: "border-green-900 bg-green-950 text-green-400",
  PAYMENT: "border-red-900 bg-red-950 text-red-400",
  CONTRA: "border-blue-900 bg-blue-950 text-blue-400",
  JOURNAL: "border-yellow-900 bg-yellow-950 text-yellow-400",
  DEBIT_NOTE: "border-orange-900 bg-orange-950 text-orange-400",
  CREDIT_NOTE: "border-purple-900 bg-purple-950 text-purple-400",
  EXPENSE: "border-pink-900 bg-pink-950 text-pink-400",
};

const VOUCHER_TYPE_VALUES = new Set(VOUCHER_TYPES.map((t) => t.value));

export default function Vouchers() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [vouchers, setVouchers] = useState([]);
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [total, setTotal] = useState(0);
  const [customers, setCustomers] = useState([]);
  const [vendors, setVendors] = useState([]);

  const blankForm = () => ({
    voucher_type: "RECEIPT", date: new Date().toISOString().split("T")[0],
    narration: "", party_name: "", party_id: "",
    amount: "", payment_mode: "CASH", party_type: "CUSTOMER",
    reference_number: "", status: "DRAFT",
  });
  const [form, setForm] = useState(blankForm());
  const [editingId, setEditingId] = useState(null);

  const loadVouchers = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (typeFilter) params.voucher_type = typeFilter;
      if (statusFilter) params.status = statusFilter;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (search) params.search = search;
      const r = await api.get("/vouchers", { params });
      setVouchers(r.data.items || []);
      setTotal(r.data.total || 0);
    } finally { setLoading(false); }
  }, [typeFilter, statusFilter, fromDate, toDate, search]);

  const loadStats = useCallback(async () => {
    try {
      const r = await api.get("/vouchers/summary/stats");
      setStats(r.data.by_type || []);
    } catch {}
  }, []);

  const loadParties = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        api.get("/customers"),
        api.get("/suppliers"),
      ]);
      setCustomers(c.data || []);
      setVendors(s.data || []);
    } catch {}
  }, []);

  useEffect(() => {
    loadVouchers();
    loadStats();
    loadParties();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openNew = (presetType) => {
    setEditingId(null);
    setForm({ ...blankForm(), ...(presetType ? { voucher_type: presetType } : {}) });
    setShowModal(true);
  };

  // Global F5/F6/F7 (Payment/Receipt/Journal) shortcuts (see useKeyboardShortcuts)
  // navigate here with ?type=PAYMENT etc. so the new-voucher form opens
  // pre-set to the right type, matching Tally's F-key behaviour. Consumed
  // once and stripped from the URL so a later plain visit/refresh doesn't
  // keep reopening the modal.
  useEffect(() => {
    const type = searchParams.get("type");
    if (type && VOUCHER_TYPE_VALUES.has(type)) {
      openNew(type);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("type");
        return next;
      }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const openEdit = (v) => {
    setEditingId(v.id);
    setForm({
      voucher_type: v.voucher_type || "RECEIPT",
      date: v.date || new Date().toISOString().split("T")[0],
      narration: v.narration || "",
      party_name: v.party_name || "",
      party_id: v.party_id || "",
      amount: v.amount != null && v.amount !== 0 ? v.amount : "",
      payment_mode: v.payment_mode || "CASH",
      party_type: v.party_type || "CUSTOMER",
      reference_number: v.reference_number || "",
      status: v.status || "DRAFT",
    });
    setShowModal(true);
  };

  const saveVoucher = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...form, amount: parseFloat(form.amount) || 0 };
      if (editingId) {
        await api.patch(`/vouchers/${editingId}`, payload);
        toast.success("Voucher updated");
      } else {
        await api.post("/vouchers", payload);
        toast.success("Voucher created");
      }
      setShowModal(false);
      setEditingId(null);
      setForm(blankForm());
      loadVouchers();
      loadStats();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank voucher, Esc
  // cancels, first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: showModal,
    autoFocus: true,
    onSave: () => saveVoucher(new Event("submit", { cancelable: true })),
    onSaveAndNew: async () => {
      await saveVoucher(new Event("submit", { cancelable: true }));
      openNew();
    },
    onCancel: () => { setShowModal(false); setEditingId(null); },
  });

  useModuleShortcuts({
    onNew: () => { if (!showModal) openNew(); },
  });

  // DRAFT vouchers (never posted a journal entry) are hard-deleted by the
  // backend; anything already APPROVED is cancelled in place instead — it
  // already has a real journal_entries row, so hard-deleting it would orphan
  // the books. The confirm prompt and toast reflect whichever actually
  // happens rather than always claiming "deleted".
  const deleteVoucher = async (v) => {
    const isDraft = v.status === "DRAFT";
    const verb = isDraft ? "Delete" : "Cancel";
    if (!window.confirm(`${verb} voucher ${v.voucher_number}? This cannot be undone.`)) return;
    try {
      const { data } = await api.delete(`/vouchers/${v.id}`);
      toast.success(data.action === "deleted" ? "Voucher deleted" : "Voucher cancelled");
      loadVouchers();
      loadStats();
    } catch (err) {
      console.error("Voucher delete/cancel failure:", err);
      toast.error(formatApiErrorDetail(null, err));
    }
  };

  return (
    <div data-testid="vouchers-page">
      <PageHeader
        eyebrow="Finance"
        title="Vouchers"
        description="Receipt, Payment, Contra, Journal and other accounting vouchers."
        actions={
          <PrimaryButton icon={Plus} onClick={openNew} testid="add-voucher-btn">
            New Voucher
          </PrimaryButton>
        }
      />

      {/* Stats by type */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatTile label="Total Vouchers" value={total} />
        {stats.slice(0, 3).map(s => (
          <StatTile key={s._id} label={s._id} value={`₹${inr(s.total_amount)}`} sub={`${s.count} vouchers`} />
        ))}
      </div>

      {/* Voucher type summary cards */}
      {stats.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-px bg-zinc-800 border border-zinc-800 mb-6">
          {VOUCHER_TYPES.map(vt => {
            const s = stats.find(x => x._id === vt.value);
            return (
              <div key={vt.value} className="bg-zinc-950 p-3 text-center">
                <div className={`text-xs font-mono uppercase keep-caps font-bold ${vt.color}`}>{vt.value.replace("_", " ")}</div>
                <div className="font-display font-black text-xl text-white mt-1">{s?.count || 0}</div>
                <div className="text-[10px] text-zinc-500 font-mono">₹{inr(s?.total_amount || 0)}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search..." className="w-48" />
        <Select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="w-44">
          <option value="">All Types</option>
          {VOUCHER_TYPES.map(t => <option key={t.value} value={t.value}>{t.value}</option>)}
        </Select>
        <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="w-36">
          <option value="">All Status</option>
          {["DRAFT","APPROVED","CANCELLED"].map(s => <option key={s}>{s}</option>)}
        </Select>
        <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
        <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
        <SecondaryButton icon={Search} onClick={loadVouchers}>Filter</SecondaryButton>
      </div>

      {/* Vouchers table */}
      {loading ? (
        <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
      ) : vouchers.length === 0 ? (
        <EmptyState message="No vouchers" action={<PrimaryButton icon={Plus} onClick={openNew}>Create Voucher</PrimaryButton>} />
      ) : (
        <table className="w-full text-sm border border-zinc-800">
          <thead>
            <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
              <th className="text-left px-4 py-2">Voucher No</th>
              <th className="text-left px-4 py-2">Date</th>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Party</th>
              <th className="text-left px-4 py-2">Narration</th>
              <th className="text-right px-4 py-2">Amount</th>
              <th className="text-left px-4 py-2">Mode</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">By</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {vouchers.map((v, i) => (
              <tr key={v.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{v.voucher_number}</td>
                <td className="px-4 py-2 font-mono text-zinc-400 text-xs">{v.date}</td>
                <td className="px-4 py-2">
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${TYPE_COLORS[v.voucher_type] || "border-zinc-700 bg-zinc-800 text-zinc-400"}`}>
                    {v.voucher_type?.replace("_", " ")}
                  </span>
                </td>
                <td className="px-4 py-2 text-white text-xs">{v.party_name || "—"}</td>
                <td className="px-4 py-2 text-zinc-400 text-xs max-w-xs truncate">{v.narration}</td>
                <td className="px-4 py-2 text-right tabular font-semibold text-yellow-400">₹{inr(v.amount)}</td>
                <td className="px-4 py-2 text-xs text-zinc-400 font-mono">{v.payment_mode}</td>
                <td className="px-4 py-2">
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                    v.status === "APPROVED" ? "border-green-800 bg-green-950 text-green-400" :
                    v.status === "CANCELLED" ? "border-red-800 bg-red-950 text-red-400" :
                    "border-zinc-700 bg-zinc-800 text-zinc-400"
                  }`}>{v.status}</span>
                </td>
                <td className="px-4 py-2 text-xs text-zinc-500">{v.created_by_name || "—"}</td>
                <td className="px-4 py-2">
                  <div className="inline-flex gap-1">
                    {v.status !== "CANCELLED" && (
                      <button
                        onClick={() => openEdit(v)}
                        title="Edit"
                        className="w-7 h-7 border border-zinc-700 hover:border-primary hover:text-primary text-zinc-500 flex items-center justify-center transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {v.status !== "CANCELLED" && (
                      <button
                        onClick={() => deleteVoucher(v)}
                        title={v.status === "DRAFT" ? "Delete" : "Cancel — already posted, cannot be hard-deleted"}
                        className="w-7 h-7 border border-zinc-700 hover:border-red-500 hover:text-red-400 text-zinc-500 flex items-center justify-center transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Create / Edit Voucher Modal */}
      <Modal open={showModal} onClose={() => { setShowModal(false); setEditingId(null); }} title={editingId ? "Edit Voucher" : "New Voucher"}>
        <form ref={formRef} onSubmit={saveVoucher} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Voucher Type" required>
              <Select value={form.voucher_type} onChange={e => setForm(f => ({ ...f, voucher_type: e.target.value }))}>
                {VOUCHER_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </Select>
            </Field>
            <Field label="Date" required>
              <Input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} required />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Party Type" required>
              <Select
                value={form.party_type}
                onChange={e => setForm(f => ({ ...f, party_type: e.target.value, party_id: "", party_name: "" }))}
              >
                <option value="CUSTOMER">CUSTOMER</option>
                <option value="SUPPLIER">VENDOR</option>
              </Select>
            </Field>
            <Field label="Party" required>
              <Select
                value={form.party_id}
                onChange={e => {
                  const list = form.party_type === "SUPPLIER" ? vendors : customers;
                  const p = list.find(x => x.id === e.target.value);
                  const name = form.party_type === "SUPPLIER" ? (p?.company || p?.name || "") : (p?.name || "");
                  setForm(f => ({ ...f, party_id: e.target.value, party_name: name }));
                }}
              >
                <option value="">Select {form.party_type === "SUPPLIER" ? "vendor" : "customer"}…</option>
                {(form.party_type === "SUPPLIER" ? vendors : customers).map(p => (
                  <option key={p.id} value={p.id}>
                    {form.party_type === "SUPPLIER" ? (p.company || p.name) : p.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Narration" required>
            <Input value={form.narration} onChange={e => setForm(f => ({ ...f, narration: e.target.value }))} placeholder="Brief description" required />
          </Field>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Field label="Amount (₹)" required>
              <NumericInput value={form.amount} onChange={v => setForm(f => ({ ...f, amount: v }))} placeholder="0.00" align="left" />
            </Field>
            <Field label="Payment Mode">
              <Select value={form.payment_mode} onChange={e => setForm(f => ({ ...f, payment_mode: e.target.value }))}>
                {["CASH","CHEQUE","UPI","NEFT","RTGS","OTHER"].map(m => <option key={m}>{m}</option>)}
              </Select>
            </Field>
            <Field label="Reference No">
              <Input value={form.reference_number} onChange={e => setForm(f => ({ ...f, reference_number: e.target.value }))} placeholder="Cheque / UTR" />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                {["DRAFT","PENDING","APPROVED","CANCELLED"].map(s => <option key={s}>{s}</option>)}
              </Select>
            </Field>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => { setShowModal(false); setEditingId(null); }}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">{editingId ? "Save Changes" : "Create Voucher"}</PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
