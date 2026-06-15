import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
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
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import { Plus, RefreshCw, Search } from "lucide-react";

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

export default function Vouchers() {
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
  const [suppliers, setSuppliers] = useState([]);

  const [form, setForm] = useState({
    voucher_type: "RECEIPT", date: new Date().toISOString().split("T")[0],
    narration: "", party_name: "", party_id: "",
    amount: 0, payment_mode: "CASH", party_type: "CUSTOMER",
    reference_number: "", status: "DRAFT",
  });

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
      setSuppliers(s.data || []);
    } catch {}
  }, []);

  useEffect(() => {
    loadVouchers();
    loadStats();
    loadParties();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createVoucher = async (e) => {
    e.preventDefault();
    try {
      await api.post("/vouchers", { ...form, amount: parseFloat(form.amount) });
      toast.success("Voucher created");
      setShowModal(false);
      setForm({ voucher_type: "RECEIPT", date: new Date().toISOString().split("T")[0], narration: "", party_name: "", party_id: "", amount: 0, payment_mode: "CASH", party_type: "CUSTOMER", reference_number: "", status: "DRAFT" });
      loadVouchers();
      loadStats();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const cancelVoucher = async (id) => {
    if (!window.confirm("Cancel this voucher?")) return;
    try {
      await api.delete(`/vouchers/${id}`);
      toast.success("Voucher cancelled");
      loadVouchers();
    } catch (e) {
      toast.error("Failed");
    }
  };

  return (
    <div data-testid="vouchers-page">
      <PageHeader
        eyebrow="Finance"
        title="Vouchers"
        description="Receipt, Payment, Contra, Journal and other accounting vouchers."
        actions={
          <PrimaryButton icon={Plus} onClick={() => setShowModal(true)} testid="add-voucher-btn">
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
                <div className={`text-xs font-mono uppercase font-bold ${vt.color}`}>{vt.value.replace("_", " ")}</div>
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
        <EmptyState message="No vouchers" action={<PrimaryButton icon={Plus} onClick={() => setShowModal(true)}>Create Voucher</PrimaryButton>} />
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
                  {v.status !== "CANCELLED" && (
                    <button onClick={() => cancelVoucher(v.id)} className="text-xs text-red-500 hover:text-red-300 font-mono">Cancel</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Create Voucher Modal */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="New Voucher">
        <form onSubmit={createVoucher} className="space-y-4">
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
                <option value="SUPPLIER">SUPPLIER</option>
              </Select>
            </Field>
            <Field label="Party" required>
              <Select
                value={form.party_id}
                onChange={e => {
                  const list = form.party_type === "SUPPLIER" ? suppliers : customers;
                  const p = list.find(x => x.id === e.target.value);
                  setForm(f => ({ ...f, party_id: e.target.value, party_name: p?.name || "" }));
                }}
              >
                <option value="">Select {form.party_type === "SUPPLIER" ? "supplier" : "customer"}…</option>
                {(form.party_type === "SUPPLIER" ? suppliers : customers).map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Narration" required>
            <Input value={form.narration} onChange={e => setForm(f => ({ ...f, narration: e.target.value }))} placeholder="Brief description" required />
          </Field>
          <div className="grid grid-cols-3 gap-4">
            <Field label="Amount (₹)" required>
              <Input type="number" step="0.01" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} required />
            </Field>
            <Field label="Payment Mode">
              <Select value={form.payment_mode} onChange={e => setForm(f => ({ ...f, payment_mode: e.target.value }))}>
                {["CASH","BANK","CHEQUE","UPI","NEFT","RTGS"].map(m => <option key={m}>{m}</option>)}
              </Select>
            </Field>
            <Field label="Reference No">
              <Input value={form.reference_number} onChange={e => setForm(f => ({ ...f, reference_number: e.target.value }))} placeholder="Cheque / UTR" />
            </Field>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Create Voucher</PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
