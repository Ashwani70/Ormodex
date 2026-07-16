import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";

// ── Shared primitives ────────────────────────────────────────────────────────
const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 rounded-xl p-4 ${className}`}>{children}</div>
);
const SectionHeader = ({ title, action }) => (
  <div className="flex items-center justify-between mb-4">
    <h2 className="text-lg font-semibold text-white">{title}</h2>
    {action}
  </div>
);
const Input = ({ label, ...props }) => (
  <div>
    {label && <label className="block text-xs text-zinc-400 mb-1">{label}</label>}
    <input className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400" {...props} />
  </div>
);
const Select = ({ label, children, ...props }) => (
  <div>
    {label && <label className="block text-xs text-zinc-400 mb-1">{label}</label>}
    <select className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400" {...props}>{children}</select>
  </div>
);
const Btn = ({ children, onClick, variant = "primary", disabled, className = "", type = "button" }) => {
  const v = {
    primary:   "bg-yellow-400 text-zinc-950 hover:bg-yellow-300",
    secondary: "bg-zinc-700 text-white hover:bg-zinc-600",
    danger:    "bg-red-800 text-white hover:bg-red-700",
    success:   "bg-emerald-700 text-white hover:bg-emerald-600",
    ghost:     "text-zinc-400 hover:text-white",
    info:      "bg-blue-700 text-white hover:bg-blue-600",
  };
  return (
    <button type={type} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${v[variant] ?? v.primary} ${className}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
};
const Badge = ({ status }) => {
  const map = {
    printed:   "bg-emerald-900 text-emerald-300",
    reprinted: "bg-blue-900 text-blue-300",
    pending:   "bg-zinc-700 text-zinc-300",
    cancelled: "bg-red-900 text-red-300",
    void:      "bg-orange-900 text-orange-300",
    cleared:   "bg-teal-900 text-teal-300",
    bounced:   "bg-yellow-900 text-yellow-300",
  };
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[status] ?? "bg-zinc-700 text-zinc-300"}`}>{status}</span>;
};
const fmtMoney  = (n) => `₹${Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const apiErr    = (e, fallback) => toast.error(formatApiErrorDetail(e?.response?.data?.detail) || fallback);

const FIELD_LABELS = {
  date:            "Date",
  payee_name:      "Payee Name",
  amount_words:    "Amount in Words",
  amount_figures:  "Amount in Figures",
  account_payee:   "A/C Payee Text",
  signature_marker:"Signature Marker",
};
const FONT_OPTIONS  = ["Helvetica", "Courier", "Times"];
const ALIGN_OPTIONS = ["left", "center", "right"];
const STATUS_OPTIONS = ["printed","reprinted","cancelled","void","cleared","bounced"];

const SOURCE_TYPES = [
  { value: "payment_voucher",  label: "Payment Voucher" },
  { value: "supplier_payment", label: "Supplier Payment" },
  { value: "customer_refund",  label: "Customer Refund" },
  { value: "expense_payment",  label: "Expense Payment" },
  { value: "bank_payment",     label: "Bank Payment Entry" },
];

// ════════════════════════════════════════════════════════════
// Voucher Picker modal
// ════════════════════════════════════════════════════════════
function VoucherPicker({ onSelect, onClose }) {
  const [sourceType, setSourceType] = useState("payment_voucher");
  const [vouchers, setVouchers]     = useState([]);
  const [loading, setLoading]       = useState(false);
  const [fromDate, setFromDate]     = useState("");
  const [toDate, setToDate]         = useState("");

  const search = useCallback(async () => {
    setLoading(true);
    try {
      const params = { source_type: sourceType };
      if (fromDate) params.from_date = fromDate;
      if (toDate)   params.to_date   = toDate;
      const { data } = await api.get("/cheque-printing/vouchers/payment", { params });
      setVouchers(data);
    } catch (e) { apiErr(e, "Failed to load vouchers"); }
    finally { setLoading(false); }
  }, [sourceType, fromDate, toDate]);

  useEffect(() => { search(); }, [sourceType]); // eslint-disable-line

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 w-[700px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">Select Payment Voucher</h3>
          <Btn variant="ghost" onClick={onClose}>✕</Btn>
        </div>
        <div className="flex gap-3 mb-3 flex-wrap">
          <div className="flex-1 min-w-[160px]">
            <Select label="Source type" value={sourceType} onChange={e => setSourceType(e.target.value)}>
              {SOURCE_TYPES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </Select>
          </div>
          <div><Input label="From" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} /></div>
          <div><Input label="To"   type="date" value={toDate}   onChange={e => setToDate(e.target.value)}   /></div>
          <div className="flex items-end"><Btn onClick={search} disabled={loading}>{loading ? "…" : "Search"}</Btn></div>
        </div>
        <div className="overflow-auto flex-1">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800 sticky top-0 bg-zinc-900">
              <th className="py-2">Voucher No</th><th>Party</th><th>Amount</th><th>Date</th><th></th>
            </tr></thead>
            <tbody>
              {vouchers.map(v => (
                <tr key={v.id} className="border-b border-zinc-900 hover:bg-zinc-800 cursor-pointer" onClick={() => onSelect(v)}>
                  <td className="py-2 text-yellow-400 font-mono text-xs">{v.voucher_number || "—"}</td>
                  <td className="text-zinc-200">{v.party_name || "—"}</td>
                  <td className="text-right font-mono text-zinc-200">{fmtMoney(v.amount)}</td>
                  <td className="text-zinc-400 text-xs">{v.date?.slice(0,10)}</td>
                  <td className="text-right"><Btn variant="primary" className="py-1 px-2 text-xs" onClick={() => onSelect(v)}>Select</Btn></td>
                </tr>
              ))}
              {vouchers.length === 0 && !loading && (
                <tr><td colSpan={5} className="py-8 text-center text-zinc-500">No vouchers found. Try a different source type or date range.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Cancel / Void modal
// ════════════════════════════════════════════════════════════
function ReasonModal({ title, actionLabel, variant = "danger", onConfirm, onClose }) {
  const [reason, setReason] = useState("");
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 w-96" onClick={e => e.stopPropagation()}>
        <h3 className="text-white font-semibold mb-3">{title}</h3>
        <Input label="Reason (required)" value={reason} onChange={e => setReason(e.target.value)} autoFocus />
        <div className="mt-4 flex gap-2 justify-end">
          <Btn variant="ghost" onClick={onClose}>Close</Btn>
          <Btn variant={variant} onClick={() => { if (reason.trim()) onConfirm(reason); else toast.error("Reason is required"); }}>{actionLabel}</Btn>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Status update modal (cleared / bounced)
// ════════════════════════════════════════════════════════════
function StatusModal({ cheque, onConfirm, onClose }) {
  const [status, setStatus]  = useState("cleared");
  const [date_, setDate]     = useState(new Date().toISOString().slice(0,10));
  const [reason, setReason]  = useState("");

  const submit = () => onConfirm({ status, cleared_date: status === "cleared" ? date_ : undefined, bounced_date: status === "bounced" ? date_ : undefined, bounced_reason: reason || undefined });

  // Enter-as-Tab across this small status-update form; Ctrl+Enter/Ctrl+S
  // confirms, Esc closes, first field auto-focuses.
  const statusFormRef = useRef(null);
  useEnterNavigation(statusFormRef, {
    enabled: true,
    autoFocus: true,
    onSave: submit,
    onCancel: onClose,
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div ref={statusFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 w-96" onClick={e => e.stopPropagation()}>
        <h3 className="text-white font-semibold mb-3">Update cheque {cheque.cheque_number}</h3>
        <div className="space-y-3">
          <Select label="New Status" value={status} onChange={e => setStatus(e.target.value)}>
            <option value="cleared">Cleared</option>
            <option value="bounced">Bounced</option>
          </Select>
          <Input label={status === "cleared" ? "Cleared Date" : "Bounced Date"} type="date" value={date_} onChange={e => setDate(e.target.value)} />
          {status === "bounced" && <Input label="Bounce Reason" value={reason} onChange={e => setReason(e.target.value)} />}
        </div>
        <div className="mt-4 flex gap-2 justify-end">
          <Btn variant="ghost" onClick={onClose}>Close</Btn>
          <Btn variant="primary" onClick={submit}>
            Update
          </Btn>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Cheque history modal
// ════════════════════════════════════════════════════════════
function HistoryModal({ cheque, onClose }) {
  const [logs, setLogs] = useState([]);
  useEffect(() => {
    api.get(`/cheque-printing/cheque-history/${cheque.id}`)
      .then(r => setLogs(r.data.logs || []))
      .catch(() => {});
  }, [cheque.id]);
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 w-[560px] max-h-[70vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">History — Cheque {cheque.cheque_number}</h3>
          <Btn variant="ghost" onClick={onClose}>✕</Btn>
        </div>
        <div className="overflow-auto flex-1">
          {logs.length === 0 && <p className="text-zinc-500 text-sm text-center py-4">No audit logs found.</p>}
          <div className="space-y-2">
            {logs.map((l, i) => (
              <div key={i} className="bg-zinc-800 rounded-lg p-3 text-sm">
                <div className="flex gap-2 items-center">
                  <span className="font-medium text-yellow-400">{l.action}</span>
                  <span className="text-zinc-500 text-xs">{l.created_at?.slice(0,19).replace("T"," ")}</span>
                </div>
                {l.new_values && <pre className="text-xs text-zinc-400 mt-1 overflow-auto">{JSON.stringify(l.new_values, null, 2)}</pre>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Print tab (single + voucher auto-fill)
// ════════════════════════════════════════════════════════════
function PrintTab() {
  const today = new Date().toISOString().slice(0,10);
  const blank = { bank_account_id: "", payee_name: "", amount: "", cheque_date: today, cheque_number: "", account_payee: true, printer: "", narration: "", company_name: "", source_type: "", source_id: "", voucher_number: "" };
  const [accounts, setAccounts]       = useState([]);
  const [cheques,  setCheques]        = useState([]);
  const [form,     setForm]           = useState(blank);
  const [preview,  setPreview]        = useState(null);
  const [busy,     setBusy]           = useState(false);
  const [showPicker, setShowPicker]   = useState(false);
  const [modal, setModal]             = useState(null); // { type: "cancel"|"void"|"status"|"history", cheque }
  const f = (patch) => setForm(p => ({ ...p, ...patch }));

  const load = useCallback(async () => {
    try {
      const [acc, chq] = await Promise.all([
        api.get("/cheque-printing/bank-accounts"),
        api.get("/cheque-printing/cheques"),
      ]);
      setAccounts(acc.data);
      setCheques(chq.data);
    } catch (e) { apiErr(e, "Failed to load"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const onVoucherSelect = (v) => {
    f({ payee_name: v.party_name || "", amount: v.amount || "", cheque_date: v.date?.slice(0,10) || today, source_type: v.source_type || "", source_id: v.id || "", voucher_number: v.voucher_number || "", narration: v.narration || "", bank_account_id: v.bank_account_id || form.bank_account_id });
    setShowPicker(false);
    setPreview(null);
  };

  const doPreview = async () => {
    if (!form.bank_account_id || !form.payee_name || !form.amount) return toast.error("Account, payee and amount required");
    try {
      const { data } = await api.post("/cheque-printing/cheques/preview", { ...form, amount: Number(form.amount) });
      setPreview(data);
    } catch (e) { apiErr(e, "Preview failed"); }
  };

  const doPrint = async (testPrint) => {
    if (!form.bank_account_id || !form.payee_name || !form.amount) return toast.error("Account, payee and amount required");
    if (!testPrint && !form.cheque_number) return toast.error("Cheque number is required to print");
    setBusy(true);
    try {
      const resp = await api.post("/cheque-printing/cheques/print",
        { ...form, amount: Number(form.amount), cheque_number: form.cheque_number || "TEST", test_print: testPrint },
        { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 15000);
      if (!testPrint) { toast.success("Cheque printed & saved"); setForm(blank); load(); }
    } catch (e) {
      let detail = e.response?.data;
      if (detail instanceof Blob) { try { detail = JSON.parse(await detail.text())?.detail; } catch { detail = null; } }
      else { detail = detail?.detail; }
      toast.error(formatApiErrorDetail(detail) || "Print failed");
    } finally { setBusy(false); }
  };

  const doReprint = async (cheque) => {
    setBusy(true);
    try {
      const resp = await api.post(`/cheque-printing/cheques/${cheque.id}/reprint`, {}, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 15000);
      toast.success("Reprinted"); load();
    } catch (e) { apiErr(e, "Reprint failed"); }
    finally { setBusy(false); }
  };

  const doCancel = async (cheque, reason) => {
    try { await api.post(`/cheque-printing/cheques/${cheque.id}/cancel`, { reason }); toast.success("Cheque cancelled"); setModal(null); load(); }
    catch (e) { apiErr(e, "Cancel failed"); }
  };
  const doVoid = async (cheque, reason) => {
    try { await api.post(`/cheque-printing/cheques/${cheque.id}/void`, { reason }); toast.success("Cheque voided"); setModal(null); load(); }
    catch (e) { apiErr(e, "Void failed"); }
  };
  const doStatusUpdate = async (cheque, payload) => {
    try { await api.post(`/cheque-printing/cheques/${cheque.id}/status`, payload); toast.success("Status updated"); setModal(null); load(); }
    catch (e) { apiErr(e, "Status update failed"); }
  };

  const canReprint = (c) => !["cancelled","void"].includes(c.status);
  const canCancel  = (c) => !["cancelled","void"].includes(c.status);
  const canVoid    = (c) => !c.is_void;
  const canStatus  = (c) => ["printed","reprinted"].includes(c.status);

  // Enter-as-Tab across the Print a Cheque form; Ctrl+Enter/Ctrl+S triggers
  // Print & Save (the real "save" action here — Preview/Test Print stay
  // mouse/click actions). Always-visible panel (not a modal), so no Esc
  // cancel is wired — there's nothing to dismiss. This is the page's
  // primary/default-tab action, so it also owns Ctrl+N to jump back to a
  // blank cheque.
  const printFormRef = useRef(null);
  useEnterNavigation(printFormRef, {
    enabled: true,
    autoFocus: true,
    onSave: () => doPrint(false),
  });
  useModuleShortcuts({
    onNew: () => setForm(blank),
  });

  return (
    <div className="space-y-4">
      {showPicker && <VoucherPicker onSelect={onVoucherSelect} onClose={() => setShowPicker(false)} />}
      {modal?.type === "cancel"  && <ReasonModal title={`Cancel cheque ${modal.cheque.cheque_number}`} actionLabel="Cancel Cheque" onConfirm={r => doCancel(modal.cheque, r)} onClose={() => setModal(null)} />}
      {modal?.type === "void"    && <ReasonModal title={`Void cheque ${modal.cheque.cheque_number}`}   actionLabel="Void Cheque"   variant="danger" onConfirm={r => doVoid(modal.cheque, r)} onClose={() => setModal(null)} />}
      {modal?.type === "status"  && <StatusModal cheque={modal.cheque} onConfirm={p => doStatusUpdate(modal.cheque, p)} onClose={() => setModal(null)} />}
      {modal?.type === "history" && <HistoryModal cheque={modal.cheque} onClose={() => setModal(null)} />}

      <SectionHeader title="Print a Cheque" action={<Btn variant="secondary" onClick={() => setShowPicker(true)}>↓ Auto-fill from Voucher</Btn>} />

      {form.voucher_number && (
        <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-zinc-300 flex items-center gap-2">
          <span className="text-yellow-400">Linked:</span>
          <span>{SOURCE_TYPES.find(s => s.value === form.source_type)?.label ?? form.source_type}</span>
          <span className="text-zinc-500">•</span>
          <span className="font-mono">{form.voucher_number}</span>
          <button className="ml-auto text-zinc-500 hover:text-white text-xs" onClick={() => f({ source_type:"", source_id:"", voucher_number:"" })}>✕ unlink</button>
        </div>
      )}

      <Card>
        <div ref={printFormRef}>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Select label="Bank Account" value={form.bank_account_id} onChange={e => { f({ bank_account_id: e.target.value }); setPreview(null); }}>
              <option value="">Select…</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.bank_name} — {a.account_holder_name} ({a.account_number})</option>)}
            </Select>
            <Input label="Payee Name"    value={form.payee_name}    onChange={e => f({ payee_name: e.target.value })} />
            <Input label="Amount (₹)"    type="text" inputMode="decimal" value={form.amount} onChange={e => f({ amount: e.target.value })} />
            <Input label="Cheque Date"   type="date" value={form.cheque_date}   onChange={e => f({ cheque_date: e.target.value })} />
            <Input label="Cheque Number" value={form.cheque_number}  onChange={e => f({ cheque_number: e.target.value })} />
            <Input label="Printer (optional)" value={form.printer}  onChange={e => f({ printer: e.target.value })} />
            <div className="col-span-2 md:col-span-3">
              <Input label="Narration" value={form.narration} onChange={e => f({ narration: e.target.value })} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-300 mt-3">
            <input type="checkbox" checked={form.account_payee} onChange={e => f({ account_payee: e.target.checked })} className="accent-yellow-400" />
            Print "A/C PAYEE ONLY"
          </label>
          <div className="mt-4 flex gap-2 flex-wrap">
            <Btn onClick={doPreview}>Preview</Btn>
            <Btn variant="secondary" disabled={busy} onClick={() => doPrint(true)}>Test Print</Btn>
            <Btn variant="success"   disabled={busy} onClick={() => doPrint(false)}>{busy ? "Printing…" : "Print & Save"}</Btn>
          </div>
        </div>
      </Card>

      {/* Preview panel */}
      {preview && (
        <Card>
          <p className="text-xs text-zinc-400 mb-2 font-medium">PREVIEW</p>
          <div className="bg-white rounded-lg p-2 overflow-auto max-w-full">
            <div className="relative bg-white mx-auto border border-zinc-200"
              style={{ width: preview.cheque_width_mm * 3.78, height: preview.cheque_height_mm * 3.78 }}>
              {preview.fields.map((fld, i) => (
                <div key={i} className="absolute text-black text-[11px] whitespace-nowrap"
                  style={{ left: fld.x_mm * 3.78, top: fld.y_mm * 3.78, fontSize: fld.font_size, fontFamily: fld.font_family, letterSpacing: fld.char_spacing }}>
                  {fld.value}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-2 text-xs text-zinc-400"><span className="text-zinc-300">Amount in words:</span> {preview.amount_words}</div>
        </Card>
      )}

      {/* Cheques table */}
      <Card>
        <p className="text-sm font-medium text-zinc-300 mb-3">Recent Cheques</p>
        <div className="overflow-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Cheque No</th><th>Bank</th><th>Payee</th><th>Amount</th>
              <th>Date</th><th>Voucher</th><th>Status</th><th>Prints</th><th></th>
            </tr></thead>
            <tbody>
              {cheques.map(c => (
                <tr key={c.id} className="border-b border-zinc-900 text-sm">
                  <td className="py-2 font-mono text-yellow-400 text-xs">{c.cheque_number}</td>
                  <td className="text-zinc-400 text-xs">{c.bank_name}</td>
                  <td className="text-zinc-300">{c.payee_name}</td>
                  <td className="text-right font-mono text-zinc-200">{fmtMoney(c.amount)}</td>
                  <td className="text-zinc-400 text-xs">{c.cheque_date?.slice(0,10)}</td>
                  <td className="text-zinc-500 text-xs">{c.voucher_number || "—"}</td>
                  <td><Badge status={c.status} /></td>
                  <td className="text-zinc-500 text-xs text-center">{(c.reprint_count || 0) > 0 ? `+${c.reprint_count}` : "1×"}</td>
                  <td className="text-right">
                    <div className="flex gap-1 justify-end flex-wrap">
                      {canReprint(c) && <Btn variant="ghost" onClick={() => doReprint(c)} disabled={busy}>Reprint</Btn>}
                      {canStatus(c)  && <Btn variant="ghost" onClick={() => setModal({ type:"status",  cheque: c })}>Status</Btn>}
                      {canCancel(c)  && <Btn variant="ghost" onClick={() => setModal({ type:"cancel",  cheque: c })}>Cancel</Btn>}
                      {canVoid(c)    && <Btn variant="ghost" onClick={() => setModal({ type:"void",    cheque: c })}>Void</Btn>}
                      <Btn variant="ghost" onClick={() => setModal({ type:"history", cheque: c })}>History</Btn>
                    </div>
                  </td>
                </tr>
              ))}
              {cheques.length === 0 && <tr><td colSpan={9} className="py-6 text-center text-zinc-500">No cheques printed yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Bulk Print tab
// ════════════════════════════════════════════════════════════
function BulkPrintTab() {
  const [accounts, setAccounts]  = useState([]);
  const [items,    setItems]     = useState([]);
  const [printer,  setPrinter]   = useState("");
  const [busy,     setBusy]      = useState(false);
  const today = new Date().toISOString().slice(0,10);
  const blankRow = () => ({ bank_account_id:"", payee_name:"", amount:"", cheque_date: today, cheque_number:"", account_payee: true, narration:"", voucher_number:"" });

  useEffect(() => {
    api.get("/cheque-printing/bank-accounts").then(r => setAccounts(r.data)).catch(() => {});
  }, []);

  const addRow = ()          => setItems(p => [...p, blankRow()]);
  const rmRow  = (i)         => setItems(p => p.filter((_,j) => j !== i));
  const editRow = (i, patch) => setItems(p => p.map((r,j) => j === i ? { ...r, ...patch } : r));

  const doBulk = async () => {
    if (items.length === 0) return toast.error("Add at least one cheque");
    const errs = items.flatMap((it, i) => {
      const msgs = [];
      if (!it.bank_account_id) msgs.push(`Row ${i+1}: bank account required`);
      if (!it.payee_name)      msgs.push(`Row ${i+1}: payee required`);
      if (!it.amount || Number(it.amount) <= 0) msgs.push(`Row ${i+1}: valid amount required`);
      if (!it.cheque_number)   msgs.push(`Row ${i+1}: cheque number required`);
      return msgs;
    });
    if (errs.length) { toast.error(errs[0]); return; }

    setBusy(true);
    try {
      const payload = { printer, items: items.map(it => ({ ...it, amount: Number(it.amount) })) };
      const resp = await api.post("/cheque-printing/cheques/bulk-print", payload, { responseType: "blob" });
      const url  = URL.createObjectURL(new Blob([resp.data], { type: "application/zip" }));
      const a    = document.createElement("a");
      a.href = url; a.download = "bulk-cheques.zip"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 15000);
      toast.success(`${items.length} cheques printed — ZIP downloaded`);
      setItems([]);
    } catch (e) {
      let detail = e.response?.data;
      if (detail instanceof Blob) { try { detail = JSON.parse(await detail.text())?.detail; } catch { detail = null; } }
      else { detail = detail?.detail; }
      toast.error(formatApiErrorDetail(detail) || "Bulk print failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Bulk Cheque Printing"
        action={
          <div className="flex gap-2 items-center">
            <div className="w-48"><Input placeholder="Printer (optional)" value={printer} onChange={e => setPrinter(e.target.value)} /></div>
            <Btn onClick={addRow} variant="secondary">+ Add Row</Btn>
            <Btn onClick={doBulk} disabled={busy || items.length === 0} variant="success">{busy ? "Printing…" : `Print ${items.length} Cheque${items.length !== 1 ? "s" : ""}`}</Btn>
          </div>
        }
      />
      {items.length === 0 ? (
        <Card><p className="text-zinc-500 text-sm text-center py-6">Click "Add Row" to add cheques to the bulk print queue. Maximum 50 cheques per batch.</p></Card>
      ) : (
        <Card className="p-2">
          <div className="overflow-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 px-2 w-[180px]">Bank Account</th>
                <th className="px-2">Payee Name</th>
                <th className="px-2 w-28">Amount</th>
                <th className="px-2 w-32">Cheque Date</th>
                <th className="px-2 w-32">Cheque No</th>
                <th className="px-2">Narration</th>
                <th className="px-2 w-8"></th>
              </tr></thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={i} className="border-b border-zinc-900">
                    <td className="py-1 px-2">
                      <select className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white" value={it.bank_account_id} onChange={e => editRow(i, { bank_account_id: e.target.value })}>
                        <option value="">Select…</option>
                        {accounts.map(a => <option key={a.id} value={a.id}>{a.bank_name} ({a.account_number?.slice(-4)})</option>)}
                      </select>
                    </td>
                    <td className="px-2"><input className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white" value={it.payee_name} onChange={e => editRow(i, { payee_name: e.target.value })} placeholder="Payee name" /></td>
                    <td className="px-2"><input className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white text-right" type="text" inputMode="decimal" value={it.amount} onChange={e => editRow(i, { amount: e.target.value })} placeholder="0.00" /></td>
                    <td className="px-2"><input className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white" type="date" value={it.cheque_date} onChange={e => editRow(i, { cheque_date: e.target.value })} /></td>
                    <td className="px-2"><input className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white font-mono" value={it.cheque_number} onChange={e => editRow(i, { cheque_number: e.target.value })} placeholder="000001" /></td>
                    <td className="px-2"><input className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-white" value={it.narration} onChange={e => editRow(i, { narration: e.target.value })} placeholder="Narration" /></td>
                    <td className="px-2 text-center"><button onClick={() => rmRow(i)} className="text-zinc-500 hover:text-red-400 text-sm">✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Issue Register tab
// ════════════════════════════════════════════════════════════
function RegisterTab() {
  const [rows,     setRows]     = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [filt,     setFilt]     = useState({ bank_account_id:"", status:"", from_date:"", to_date:"" });

  const load = useCallback(async () => {
    try {
      const params = {};
      if (filt.bank_account_id) params.bank_account_id = filt.bank_account_id;
      if (filt.status)          params.status           = filt.status;
      if (filt.from_date)       params.from_date        = filt.from_date;
      if (filt.to_date)         params.to_date          = filt.to_date;
      const { data } = await api.get("/cheque-printing/register", { params });
      setRows(data);
    } catch (e) { apiErr(e, "Failed to load register"); }
  }, [filt]);

  useEffect(() => {
    api.get("/cheque-printing/bank-accounts").then(r => setAccounts(r.data)).catch(() => {});
  }, []);

  const total = rows.reduce((s, r) => s + (["cancelled","void"].includes(r.status) ? 0 : Number(r.amount ?? 0)), 0);

  return (
    <div className="space-y-4">
      <SectionHeader title="Cheque Issue Register" action={<Btn onClick={load}>Refresh</Btn>} />
      <Card>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Select label="Bank Account" value={filt.bank_account_id} onChange={e => setFilt(p => ({ ...p, bank_account_id: e.target.value }))}>
            <option value="">All Banks</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.bank_name} ({a.account_number})</option>)}
          </Select>
          <Select label="Status" value={filt.status} onChange={e => setFilt(p => ({ ...p, status: e.target.value }))}>
            <option value="">All</option>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Input label="From Date" type="date" value={filt.from_date} onChange={e => setFilt(p => ({ ...p, from_date: e.target.value }))} />
          <Input label="To Date"   type="date" value={filt.to_date}   onChange={e => setFilt(p => ({ ...p, to_date: e.target.value }))}   />
        </div>
        <div className="mt-3"><Btn onClick={load}>Search</Btn></div>
      </Card>

      <div className="grid grid-cols-3 gap-3">
        <Card className="text-center"><div className="text-2xl font-bold text-white">{rows.length}</div><div className="text-xs text-zinc-500 mt-1">Total Entries</div></Card>
        <Card className="text-center"><div className="text-2xl font-bold text-emerald-400">{fmtMoney(total)}</div><div className="text-xs text-zinc-500 mt-1">Total Value</div></Card>
        <Card className="text-center"><div className="text-2xl font-bold text-yellow-400">{rows.filter(r => ["printed","reprinted"].includes(r.status)).length}</div><div className="text-xs text-zinc-500 mt-1">Outstanding</div></Card>
      </div>

      <Card>
        <div className="overflow-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Cheque No</th><th>Bank</th><th>Payee</th><th>Amount</th><th>Cheque Date</th><th>Issue Date</th><th>Voucher</th><th>Status</th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b border-zinc-900">
                  <td className="py-2 font-mono text-yellow-400 text-xs">{r.cheque_number}</td>
                  <td className="text-zinc-400 text-xs">{r.bank_name}</td>
                  <td className="text-zinc-300">{r.payee_name}</td>
                  <td className="text-right font-mono text-zinc-200">{fmtMoney(r.amount)}</td>
                  <td className="text-zinc-400 text-xs">{r.cheque_date?.slice(0,10)}</td>
                  <td className="text-zinc-400 text-xs">{r.issue_date?.slice(0,10)}</td>
                  <td className="text-zinc-500 text-xs">{r.voucher_number || "—"}</td>
                  <td><Badge status={r.status} /></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-zinc-500">No entries. Adjust filters and click Search.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Reports tab
// ════════════════════════════════════════════════════════════
function ReportsTab() {
  const [report,   setReport]   = useState("cheque-register");
  const [filt,     setFilt]     = useState({ from_date:"", to_date:"", bank_account_id:"", status:"" });
  const [data,     setData]     = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    api.get("/cheque-printing/bank-accounts").then(r => setAccounts(r.data)).catch(() => {});
  }, []);

  const run = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filt.from_date)       params.from_date        = filt.from_date;
      if (filt.to_date)         params.to_date          = filt.to_date;
      if (filt.bank_account_id) params.bank_account_id  = filt.bank_account_id;
      if (filt.status)          params.status           = filt.status;
      const { data: res } = await api.get(`/cheque-printing/reports/${report}`, { params });
      setData(res);
    } catch (e) { apiErr(e, "Report failed"); }
    finally { setLoading(false); }
  };

  const REPORTS = [
    { value: "cheque-register", label: "Cheque Register" },
    { value: "bank-wise",       label: "Bank-wise Summary" },
    { value: "party-wise",      label: "Party-wise Summary" },
    { value: "date-wise",       label: "Date-wise Summary" },
    { value: "outstanding",     label: "Outstanding Cheques" },
  ];

  return (
    <div className="space-y-4">
      <SectionHeader title="Cheque Reports" />
      <Card>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Select label="Report" value={report} onChange={e => { setReport(e.target.value); setData(null); }}>
            {REPORTS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </Select>
          <Select label="Bank Account" value={filt.bank_account_id} onChange={e => setFilt(p => ({ ...p, bank_account_id: e.target.value }))}>
            <option value="">All Banks</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.bank_name} ({a.account_number})</option>)}
          </Select>
          {report === "cheque-register" && (
            <Select label="Status" value={filt.status} onChange={e => setFilt(p => ({ ...p, status: e.target.value }))}>
              <option value="">All</option>
              {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </Select>
          )}
          <Input label="From Date" type="date" value={filt.from_date} onChange={e => setFilt(p => ({ ...p, from_date: e.target.value }))} />
          <Input label="To Date"   type="date" value={filt.to_date}   onChange={e => setFilt(p => ({ ...p, to_date: e.target.value }))}   />
        </div>
        <div className="mt-3"><Btn onClick={run} disabled={loading}>{loading ? "Running…" : "Run Report"}</Btn></div>
      </Card>

      {data && report === "cheque-register" && (
        <Card>
          <div className="flex gap-4 mb-3 text-sm">
            <span className="text-zinc-400">Total: <span className="text-white font-semibold">{data.total_count}</span></span>
            <span className="text-zinc-400">Value: <span className="text-emerald-400 font-semibold">{fmtMoney(data.total_amount)}</span></span>
          </div>
          <div className="overflow-auto"><table className="w-full text-sm min-w-[700px]">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Cheque No</th><th>Bank</th><th>Payee</th><th>Amount</th><th>Date</th><th>Voucher</th><th>Status</th><th>IP</th>
            </tr></thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.id} className="border-b border-zinc-900">
                  <td className="py-2 font-mono text-yellow-400 text-xs">{r.cheque_number}</td>
                  <td className="text-zinc-400 text-xs">{r.bank_name}</td>
                  <td className="text-zinc-300">{r.payee_name}</td>
                  <td className="text-right font-mono">{fmtMoney(r.amount)}</td>
                  <td className="text-zinc-400 text-xs">{r.cheque_date?.slice(0,10)}</td>
                  <td className="text-zinc-500 text-xs">{r.voucher_number || "—"}</td>
                  <td><Badge status={r.status} /></td>
                  <td className="text-zinc-600 text-xs font-mono">{r.print_ip || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}

      {data && report === "bank-wise" && (
        <Card>
          <div className="overflow-auto"><table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Bank</th><th>Total Cheques</th><th>Value</th><th>Printed</th><th>Cleared</th><th>Cancelled</th><th>Bounced</th><th>Void</th>
            </tr></thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-200 font-medium">{r.bank_name}</td>
                  <td className="text-zinc-400">{r.total_cheques}</td>
                  <td className="text-right font-mono text-emerald-400">{fmtMoney(r.total_amount)}</td>
                  <td className="text-zinc-400">{r.printed}</td>
                  <td className="text-teal-400">{r.cleared}</td>
                  <td className="text-red-400">{r.cancelled}</td>
                  <td className="text-yellow-400">{r.bounced}</td>
                  <td className="text-orange-400">{r.void}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </Card>
      )}

      {data && report === "party-wise" && (
        <div className="space-y-3">
          {data.rows.map((r, i) => (
            <Card key={i}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-white">{r.payee_name}</span>
                <div className="flex gap-4 text-sm">
                  <span className="text-zinc-400">{r.total_cheques} cheques</span>
                  <span className="text-emerald-400 font-semibold">{fmtMoney(r.total_amount)}</span>
                </div>
              </div>
              <div className="overflow-auto"><table className="w-full text-xs">
                <thead><tr className="text-zinc-500 text-left"><th className="py-1">Cheque No</th><th>Amount</th><th>Date</th><th>Status</th></tr></thead>
                <tbody>
                  {r.cheques.map((c, j) => (
                    <tr key={j} className="border-t border-zinc-800">
                      <td className="py-1 font-mono text-yellow-400">{c.cheque_number}</td>
                      <td className="text-right font-mono">{fmtMoney(c.amount)}</td>
                      <td className="text-zinc-400">{c.cheque_date?.slice(0,10)}</td>
                      <td><Badge status={c.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </Card>
          ))}
          {data.rows.length === 0 && <Card><p className="text-center text-zinc-500 py-4">No data.</p></Card>}
        </div>
      )}

      {data && report === "date-wise" && (
        <div className="space-y-3">
          {data.rows.map((r, i) => (
            <Card key={i}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-white">{r.date}</span>
                <div className="flex gap-4 text-sm">
                  <span className="text-zinc-400">{r.count} cheques</span>
                  <span className="text-emerald-400 font-semibold">{fmtMoney(r.total_amount)}</span>
                </div>
              </div>
              <div className="overflow-auto"><table className="w-full text-xs">
                <thead><tr className="text-zinc-500 text-left"><th className="py-1">Cheque No</th><th>Payee</th><th>Amount</th><th>Status</th></tr></thead>
                <tbody>
                  {r.cheques.map((c, j) => (
                    <tr key={j} className="border-t border-zinc-800">
                      <td className="py-1 font-mono text-yellow-400">{c.cheque_number}</td>
                      <td className="text-zinc-300">{c.payee_name}</td>
                      <td className="text-right font-mono">{fmtMoney(c.amount)}</td>
                      <td><Badge status={c.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </Card>
          ))}
          {data.rows.length === 0 && <Card><p className="text-center text-zinc-500 py-4">No data.</p></Card>}
        </div>
      )}

      {data && report === "outstanding" && (
        <Card>
          <div className="flex gap-4 mb-3 text-sm">
            <span className="text-zinc-400">Count: <span className="text-white font-semibold">{data.count}</span></span>
            <span className="text-zinc-400">Outstanding Value: <span className="text-yellow-400 font-semibold">{fmtMoney(data.total_outstanding)}</span></span>
          </div>
          <div className="overflow-auto"><table className="w-full text-sm min-w-[600px]">
            <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Cheque No</th><th>Bank</th><th>Payee</th><th>Amount</th><th>Cheque Date</th><th>Status</th><th>Prints</th>
            </tr></thead>
            <tbody>
              {data.rows.map(r => (
                <tr key={r.id} className="border-b border-zinc-900">
                  <td className="py-2 font-mono text-yellow-400 text-xs">{r.cheque_number}</td>
                  <td className="text-zinc-400 text-xs">{r.bank_name}</td>
                  <td className="text-zinc-300">{r.payee_name}</td>
                  <td className="text-right font-mono text-zinc-200">{fmtMoney(r.amount)}</td>
                  <td className="text-zinc-400 text-xs">{r.cheque_date?.slice(0,10)}</td>
                  <td><Badge status={r.status} /></td>
                  <td className="text-zinc-500 text-xs text-center">{(r.reprint_count || 0) > 0 ? `+${r.reprint_count}` : "1×"}</td>
                </tr>
              ))}
              {data.rows.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No outstanding cheques.</td></tr>}
            </tbody>
          </table></div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Bank Accounts tab
// ════════════════════════════════════════════════════════════
function BankAccountsTab({ templates }) {
  const [accounts, setAccounts] = useState([]);
  const [show,     setShow]     = useState(false);
  const [editing,  setEditing]  = useState(null);
  const blank = { bank_name:"", branch_name:"", account_holder_name:"", account_number:"", ifsc_code:"", cheque_type:"single", template_id:"" };
  const [form, setForm] = useState(blank);
  const f = (patch) => setForm(p => ({ ...p, ...patch }));

  const load = useCallback(async () => {
    try { setAccounts((await api.get("/cheque-printing/bank-accounts")).data); }
    catch (e) { apiErr(e, "Failed to load bank accounts"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.bank_name || !form.account_holder_name || !form.account_number || !form.ifsc_code)
      return toast.error("Bank, holder, account number and IFSC are required");
    try {
      const body = { ...form, template_id: form.template_id || null };
      if (editing) await api.put(`/cheque-printing/bank-accounts/${editing}`, body);
      else         await api.post("/cheque-printing/bank-accounts", body);
      toast.success(editing ? "Account updated" : "Account created");
      setShow(false); setEditing(null); setForm(blank); load();
    } catch (e) { apiErr(e, "Save failed"); }
  };

  // Enter-as-Tab across the Bank Account form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels, first field auto-focuses when the panel opens.
  const bankAccountFormRef = useRef(null);
  useEnterNavigation(bankAccountFormRef, {
    enabled: show,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => { setShow(false); setEditing(null); setForm(blank); },
  });

  return (
    <div className="space-y-4">
      <SectionHeader title="Bank Account Master" action={<Btn onClick={() => { setShow(v => !v); setEditing(null); setForm(blank); }}>{show ? "Cancel" : "+ New Account"}</Btn>} />
      {show && (
        <Card>
          <div ref={bankAccountFormRef} className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Input label="Bank Name" value={form.bank_name} onChange={e => f({ bank_name: e.target.value })} />
            <Input label="Branch" value={form.branch_name} onChange={e => f({ branch_name: e.target.value })} />
            <Input label="Account Holder" value={form.account_holder_name} onChange={e => f({ account_holder_name: e.target.value })} />
            <Input label="Account Number" value={form.account_number} onChange={e => f({ account_number: e.target.value })} />
            <Input label="IFSC" value={form.ifsc_code} onChange={e => f({ ifsc_code: e.target.value.toUpperCase() })} />
            <Select label="Cheque Type" value={form.cheque_type} onChange={e => f({ cheque_type: e.target.value })}>
              <option value="single">Single</option>
              <option value="top-stub">Top stub</option>
              <option value="side-stub">Side stub</option>
            </Select>
            <Select label="Linked Template" value={form.template_id} onChange={e => f({ template_id: e.target.value })}>
              <option value="">— none —</option>
              {templates.map(t => <option key={t.id} value={t.id}>{t.template_name} ({t.bank_name})</option>)}
            </Select>
          </div>
          <div className="mt-4"><Btn onClick={save}>{editing ? "Update" : "Create"}</Btn></div>
        </Card>
      )}
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Bank</th><th>Holder</th><th>Account</th><th>IFSC</th><th>Type</th><th>Template</th><th></th>
          </tr></thead>
          <tbody>
            {accounts.map(a => (
              <tr key={a.id} className="border-b border-zinc-900">
                <td className="py-2 text-zinc-200">{a.bank_name}<div className="text-xs text-zinc-500">{a.branch_name}</div></td>
                <td className="text-zinc-300">{a.account_holder_name}</td>
                <td className="text-zinc-400 font-mono text-xs">{a.account_number}</td>
                <td className="text-zinc-400 font-mono text-xs">{a.ifsc_code}</td>
                <td className="text-zinc-400 text-xs">{a.cheque_type}</td>
                <td className="text-zinc-400 text-xs">{templates.find(t => t.id === a.template_id)?.template_name || "—"}</td>
                <td className="text-right"><Btn variant="ghost" onClick={() => { setEditing(a.id); setForm({ bank_name: a.bank_name||"", branch_name: a.branch_name||"", account_holder_name: a.account_holder_name||"", account_number: a.account_number||"", ifsc_code: a.ifsc_code||"", cheque_type: a.cheque_type||"single", template_id: a.template_id||"" }); setShow(true); }}>Edit</Btn></td>
              </tr>
            ))}
            {accounts.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No bank accounts yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Template Editor (drag + arrow-key nudge + zoom)
// ════════════════════════════════════════════════════════════
const MM_TO_PX = 3.78;

function TemplateEditor({ template, onSaved, onClose }) {
  const [tpl,      setTpl]      = useState(template);
  const [zoom,     setZoom]     = useState(1);
  const [selected, setSelected] = useState(null);
  const [bgUrl,    setBgUrl]    = useState(null);
  const dragRef = useRef(null);

  useEffect(() => { setTpl(template); }, [template]);

  useEffect(() => {
    let revoke;
    if (template.background_image) {
      api.get(`/cheque-printing/templates/${template.id}/background`, { responseType: "blob" })
        .then(r => { revoke = URL.createObjectURL(r.data); setBgUrl(revoke); })
        .catch(() => setBgUrl(null));
    } else { setBgUrl(null); }
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [template.id, template.background_image]);

  const fields   = useMemo(() => tpl.field_positions || [], [tpl.field_positions]);
  const setField = (idx, patch) => setTpl(t => ({ ...t, field_positions: t.field_positions.map((f, i) => i === idx ? { ...f, ...patch } : f) }));

  const addField    = (key) => {
    if (fields.some(f => f.field === key)) return toast.error("Field already added");
    setTpl(t => ({ ...t, field_positions: [...(t.field_positions || []), { field: key, x_mm: 20, y_mm: 20, font_family: "Helvetica", font_size: 11, char_spacing: 0, align: "left", enabled: true }] }));
  };
  const removeField = (idx) => setTpl(t => ({ ...t, field_positions: t.field_positions.filter((_, i) => i !== idx) }));

  const onMouseDown = (idx, e) => {
    e.preventDefault(); setSelected(idx);
    dragRef.current = { idx, startX: e.clientX, startY: e.clientY, origX: fields[idx].x_mm, origY: fields[idx].y_mm };
  };
  useEffect(() => {
    const move = (e) => {
      if (!dragRef.current) return;
      const { idx, startX, startY, origX, origY } = dragRef.current;
      const dx = (e.clientX - startX) / (MM_TO_PX * zoom);
      const dy = (e.clientY - startY) / (MM_TO_PX * zoom);
      setField(idx, { x_mm: Math.max(0, Math.round((origX + dx) * 10) / 10), y_mm: Math.max(0, Math.round((origY + dy) * 10) / 10) });
    };
    const up = () => { dragRef.current = null; };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [zoom]); // eslint-disable-line

  useEffect(() => {
    const onKey = (e) => {
      if (selected == null) return;
      const step = e.shiftKey ? 2 : 0.5;
      const f = fields[selected]; if (!f) return;
      const map = { ArrowLeft: { x_mm: f.x_mm - step }, ArrowRight: { x_mm: f.x_mm + step }, ArrowUp: { y_mm: f.y_mm - step }, ArrowDown: { y_mm: f.y_mm + step } };
      if (map[e.key]) {
        e.preventDefault();
        const clamped = Object.fromEntries(Object.entries(map[e.key]).map(([k, v]) => [k, Math.max(0, Math.round(v * 10) / 10)]));
        setField(selected, clamped);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, fields]); // eslint-disable-line

  const save = async () => {
    try {
      await api.put(`/cheque-printing/templates/${tpl.id}`, {
        template_name: tpl.template_name, bank_name: tpl.bank_name,
        cheque_width_mm: Number(tpl.cheque_width_mm), cheque_height_mm: Number(tpl.cheque_height_mm),
        field_positions: tpl.field_positions, is_active: !!tpl.is_active,
      });
      toast.success("Template saved"); onSaved();
    } catch (e) { apiErr(e, "Save failed"); }
  };

  const uploadBg = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post(`/cheque-printing/templates/${tpl.id}/background`, fd);
      setTpl(t => ({ ...t, background_image: data.background_image }));
      toast.success("Background uploaded");
    } catch (e) { apiErr(e, "Upload failed"); }
  };

  const w = Number(tpl.cheque_width_mm) * MM_TO_PX * zoom;
  const h = Number(tpl.cheque_height_mm) * MM_TO_PX * zoom;
  const sel = selected != null ? fields[selected] : null;

  return (
    <div className="space-y-4">
      <SectionHeader title={`Editing: ${tpl.template_name}`} action={
        <div className="flex gap-2">
          <Btn variant="ghost" onClick={onClose}>← Back</Btn>
          <Btn variant="success" onClick={save}>Save Template</Btn>
        </div>
      } />
      <Card>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Input label="Template Name" value={tpl.template_name} onChange={e => setTpl(t => ({ ...t, template_name: e.target.value }))} />
          <Input label="Bank Name" value={tpl.bank_name} onChange={e => setTpl(t => ({ ...t, bank_name: e.target.value }))} />
          <Input label="Width (mm)" type="text" inputMode="decimal" value={tpl.cheque_width_mm} onChange={e => setTpl(t => ({ ...t, cheque_width_mm: e.target.value }))} />
          <Input label="Height (mm)" type="text" inputMode="decimal" value={tpl.cheque_height_mm} onChange={e => setTpl(t => ({ ...t, cheque_height_mm: e.target.value }))} />
        </div>
        <div className="flex items-center gap-3 mt-3 flex-wrap">
          <label className="text-xs text-zinc-400">Background:
            <input type="file" accept="image/*" className="ml-2 text-xs" onChange={e => uploadBg(e.target.files?.[0])} />
          </label>
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-zinc-400">Zoom</span>
            <Btn variant="secondary" onClick={() => setZoom(z => Math.max(0.4, z - 0.2))}>−</Btn>
            <span className="text-xs text-zinc-300 w-12 text-center">{Math.round(zoom * 100)}%</span>
            <Btn variant="secondary" onClick={() => setZoom(z => Math.min(3, z + 0.2))}>+</Btn>
          </div>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        {Object.keys(FIELD_LABELS).map(k => (
          <Btn key={k} variant="secondary" disabled={fields.some(f => f.field === k)} onClick={() => addField(k)}>+ {FIELD_LABELS[k]}</Btn>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2 overflow-auto">
          <p className="text-xs text-zinc-500 mb-2">Drag fields to position. Click a field then use arrow keys (Shift = larger step) to fine-tune.</p>
          <div className="relative mx-auto bg-white" style={{ width: w, height: h, backgroundImage: bgUrl ? `url(${bgUrl})` : undefined, backgroundSize: "100% 100%" }}>
            {fields.map((f, i) => (
              <div key={f.field} onMouseDown={(e) => onMouseDown(i, e)}
                className={`absolute cursor-move whitespace-nowrap select-none px-0.5 ${selected === i ? "outline outline-2 outline-yellow-500" : "outline-dotted outline-1 outline-zinc-400"} ${f.enabled ? "text-black" : "text-zinc-400 line-through"}`}
                style={{ left: f.x_mm * MM_TO_PX * zoom, top: f.y_mm * MM_TO_PX * zoom, fontSize: f.font_size * zoom, fontFamily: f.font_family, letterSpacing: (f.char_spacing || 0) * zoom }}
                title={FIELD_LABELS[f.field]}>
                {FIELD_LABELS[f.field]}
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-white mb-3">Field Properties</h3>
          {!sel && <p className="text-xs text-zinc-500">Select a field on the cheque to edit its position and font.</p>}
          {sel && (
            <div className="space-y-3">
              <div className="text-sm text-yellow-400">{FIELD_LABELS[sel.field]}</div>
              <div className="grid grid-cols-2 gap-2">
                <Input label="X (mm)" type="text" inputMode="decimal" value={sel.x_mm} onChange={e => setField(selected, { x_mm: Number(e.target.value) })} />
                <Input label="Y (mm)" type="text" inputMode="decimal" value={sel.y_mm} onChange={e => setField(selected, { y_mm: Number(e.target.value) })} />
                <Input label="Font size" type="text" inputMode="decimal" value={sel.font_size} onChange={e => setField(selected, { font_size: Number(e.target.value) })} />
                <Input label="Char spacing" type="text" inputMode="decimal" value={sel.char_spacing} onChange={e => setField(selected, { char_spacing: Number(e.target.value) })} />
                <Select label="Font" value={sel.font_family} onChange={e => setField(selected, { font_family: e.target.value })}>
                  {FONT_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                </Select>
                <Select label="Align" value={sel.align} onChange={e => setField(selected, { align: e.target.value })}>
                  {ALIGN_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                </Select>
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input type="checkbox" checked={sel.enabled} onChange={e => setField(selected, { enabled: e.target.checked })} className="accent-yellow-400" />
                Enabled (printed)
              </label>
              <Btn variant="danger" onClick={() => { removeField(selected); setSelected(null); }}>Remove Field</Btn>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Templates tab
// ════════════════════════════════════════════════════════════
function TemplatesTab({ onChange }) {
  const [templates, setTemplates] = useState([]);
  const [editing,   setEditing]   = useState(null);
  const [show,      setShow]      = useState(false);
  const [seeding,   setSeeding]   = useState(false);
  const [form,      setForm]      = useState({ template_name:"", bank_name:"", cheque_width_mm:203, cheque_height_mm:93 });

  const load = useCallback(async () => {
    try { setTemplates((await api.get("/cheque-printing/templates", { params: { include_archived: true } })).data); }
    catch (e) { apiErr(e, "Failed to load templates"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.template_name || !form.bank_name) return toast.error("Name and bank required");
    try {
      const { data } = await api.post("/cheque-printing/templates", { ...form, cheque_width_mm: Number(form.cheque_width_mm), cheque_height_mm: Number(form.cheque_height_mm), field_positions: [] });
      toast.success("Template created");
      setShow(false); setForm({ template_name:"", bank_name:"", cheque_width_mm:203, cheque_height_mm:93 });
      await load(); onChange?.(); setEditing(data);
    } catch (e) { apiErr(e, "Create failed"); }
  };

  const act = async (id, action) => {
    try { await api.post(`/cheque-printing/templates/${id}/${action}`); toast.success(`Template ${action}d`); load(); onChange?.(); }
    catch (e) { apiErr(e, `${action} failed`); }
  };

  const seedDefaults = async () => {
    setSeeding(true);
    try {
      const { data } = await api.post("/cheque-printing/templates/seed-defaults");
      toast.success(data.total > 0 ? `Seeded ${data.total} default templates (${data.created.join(", ")})` : "All default templates already exist");
      load(); onChange?.();
    } catch (e) { apiErr(e, "Seed failed"); }
    finally { setSeeding(false); }
  };

  // Enter-as-Tab across the New Template form; Ctrl+Enter/Ctrl+S creates,
  // Esc cancels. Declared before the `editing` early-return below so hook
  // order stays stable across renders (enabled=false whenever not shown).
  const templateFormRef = useRef(null);
  useEnterNavigation(templateFormRef, {
    enabled: show && !editing,
    autoFocus: true,
    onSave: () => create(),
    onCancel: () => setShow(false),
  });

  if (editing) return <TemplateEditor template={editing} onClose={() => setEditing(null)} onSaved={() => { load(); onChange?.(); }} />;

  return (
    <div className="space-y-4">
      <SectionHeader title="Cheque Template Manager" action={
        <div className="flex gap-2">
          <Btn variant="secondary" onClick={seedDefaults} disabled={seeding}>{seeding ? "Seeding…" : "Load Bank Defaults (SBI/HDFC/ICICI/PNB/Axis)"}</Btn>
          <Btn onClick={() => setShow(v => !v)}>{show ? "Cancel" : "+ New Template"}</Btn>
        </div>
      } />
      {show && (
        <Card>
          <div ref={templateFormRef} className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Input label="Template Name" value={form.template_name} onChange={e => setForm(f => ({ ...f, template_name: e.target.value }))} />
            <Input label="Bank Name" value={form.bank_name} onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))} />
            <Input label="Width (mm)" type="text" inputMode="decimal" value={form.cheque_width_mm} onChange={e => setForm(f => ({ ...f, cheque_width_mm: e.target.value }))} />
            <Input label="Height (mm)" type="text" inputMode="decimal" value={form.cheque_height_mm} onChange={e => setForm(f => ({ ...f, cheque_height_mm: e.target.value }))} />
          </div>
          <div className="mt-4"><Btn onClick={create}>Create & Edit</Btn></div>
        </Card>
      )}
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Template</th><th>Bank</th><th>Size (mm)</th><th>Fields</th><th>Status</th><th></th>
          </tr></thead>
          <tbody>
            {templates.map(t => (
              <tr key={t.id} className={`border-b border-zinc-900 ${t.archived ? "opacity-50" : ""}`}>
                <td className="py-2 text-zinc-200">{t.template_name}</td>
                <td className="text-zinc-400">{t.bank_name}</td>
                <td className="text-zinc-400 font-mono text-xs">{t.cheque_width_mm}×{t.cheque_height_mm}</td>
                <td className="text-zinc-400 text-xs">{(t.field_positions || []).length}</td>
                <td className="text-xs">
                  {t.archived ? <span className="text-zinc-500">archived</span> : t.is_active ? <span className="text-emerald-400">active</span> : <span className="text-zinc-400">draft</span>}
                </td>
                <td className="text-right space-x-1">
                  {!t.archived && <Btn variant="ghost" onClick={() => setEditing(t)}>Edit</Btn>}
                  <Btn variant="ghost" onClick={() => act(t.id, "duplicate")}>Duplicate</Btn>
                  {!t.archived && !t.is_active && <Btn variant="ghost" onClick={() => act(t.id, "activate")}>Activate</Btn>}
                  {!t.archived && <Btn variant="ghost" onClick={() => act(t.id, "archive")}>Archive</Btn>}
                </td>
              </tr>
            ))}
            {templates.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-zinc-500">No templates yet. Click "Load Bank Defaults" to add SBI, HDFC, ICICI, PNB, Axis templates.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════
// Shell
// ════════════════════════════════════════════════════════════
const TABS = [
  { id: "print",     label: "Print Cheque"    },
  { id: "bulk",      label: "Bulk Print"      },
  { id: "register",  label: "Issue Register"  },
  { id: "reports",   label: "Reports"         },
  { id: "accounts",  label: "Bank Accounts"   },
  { id: "templates", label: "Templates"       },
];

export default function ChequePrinting() {
  const [tab,       setTab]       = useState("print");
  const [templates, setTemplates] = useState([]);

  const loadTemplates = useCallback(async () => {
    try { setTemplates((await api.get("/cheque-printing/templates")).data); } catch { /* guarded view */ }
  }, []);
  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Cheque Printing</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Print on pre-printed CTS cheque leaves for any Indian bank. Auto-fill from payment vouchers.
        </p>
      </div>
      <div className="flex gap-1 border-b border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "print"     && <PrintTab />}
      {tab === "bulk"      && <BulkPrintTab />}
      {tab === "register"  && <RegisterTab />}
      {tab === "reports"   && <ReportsTab />}
      {tab === "accounts"  && <BankAccountsTab templates={templates} />}
      {tab === "templates" && <TemplatesTab onChange={loadTemplates} />}
    </div>
  );
}
