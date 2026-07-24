import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Landmark, ArrowRightLeft, FileCheck2, ShieldCheck, Paperclip,
  CheckCircle2, RotateCcw, Sparkles, Info, AlertTriangle, Wand2,
} from "lucide-react";
import Modal from "@/components/Modal";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Field, Input, Select, NumericInput, Textarea, PrimaryButton, SecondaryButton,
  FormSection, SummaryCard, AttachmentsField, AuditTrail, StatusBadge,
} from "@/components/ui-kit";
import SearchableSelect from "@/components/SearchableSelect";
import PartySearch from "@/components/PartySearch";
import QuickCreateModal from "@/components/QuickCreateModal";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import api, { formatApiErrorDetail, API } from "@/lib/api";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Date().toISOString().split("T")[0];

// Transaction Type → voucher-engine parent_type + a sensible default Payment Mode.
const TXN_TYPES = [
  { value: "payment", label: "Payment (Money Out)" },
  { value: "receipt", label: "Receipt (Money In)" },
  { value: "contra", label: "Contra (Bank ↔ Cash / Bank ↔ Bank)" },
];
const PAYMENT_MODES = ["Cash", "Cheque", "NEFT", "RTGS", "IMPS", "UPI", "Card", "DD"];
const REF_FIELD_BY_MODE = {
  Cheque: { key: "cheque_number", label: "Cheque Number" },
  NEFT: { key: "utr_number", label: "UTR Number" },
  RTGS: { key: "utr_number", label: "UTR Number" },
  IMPS: { key: "utr_number", label: "UTR Number" },
  UPI: { key: "transaction_id", label: "Transaction / UPI ID" },
  Card: { key: "transaction_id", label: "Transaction ID" },
};

// One-click templates: pre-fill Transaction Type + Payment Mode + a narration
// starter. Pure frontend convenience — no backend support needed. Ledger
// selection is still left to the user since there's no AI ledger-suggestion
// engine in this app yet (see the PR notes — explicitly deferred).
const QUICK_TEMPLATES = [
  { label: "Salary", type: "payment", mode: "NEFT", narration: "Salary payment" },
  { label: "Vendor Payment", type: "payment", mode: "NEFT", narration: "Payment to vendor" },
  { label: "Customer Receipt", type: "receipt", mode: "NEFT", narration: "Receipt from customer" },
  { label: "Interest Received", type: "receipt", mode: "NEFT", narration: "Bank interest received" },
  { label: "Loan EMI", type: "payment", mode: "NEFT", narration: "Loan EMI payment" },
  { label: "GST Payment", type: "payment", mode: "NEFT", narration: "GST payment" },
  { label: "TDS Deposit", type: "payment", mode: "NEFT", narration: "TDS deposit" },
  { label: "Refund", type: "payment", mode: "NEFT", narration: "Refund issued" },
  { label: "Bank Charges", type: "payment", mode: "Cash", narration: "Bank charges" },
  { label: "Cash Deposit", type: "contra", mode: "Cash", narration: "Cash deposited into bank" },
  { label: "Cash Withdrawal", type: "contra", mode: "Cash", narration: "Cash withdrawn from bank" },
  { label: "UPI Collection", type: "receipt", mode: "UPI", narration: "UPI collection" },
];

const blank = () => ({
  bankAccountId: "", date: today(), valueDate: "", txnType: "receipt", paymentMode: "NEFT",
  amount: "", currency: "INR", referenceNumber: "", chequeNumber: "", utrNumber: "",
  transactionId: "", narration: "",
  partyId: "", partyType: "", partyName: "", partySummary: null,
  allocations: {}, // { [invoice_entry_id]: allocatedAmount }
  debitLedgerId: "", creditLedgerId: "", costCenterId: "",
  gstApplicable: false, gstRate: "", tdsRate: "", tcsRate: "", bankCharges: "", roundOff: "",
  attachments: [],
});

// Transaction Type → which party list applies (spec: Payment→Vendors,
// Receipt→Customers, Contra→bank accounts themselves, Journal→all ledgers —
// Contra/Journal don't have a "party" in the AR/AP sense, so no picker for them).
const PARTY_TYPE_BY_TXN = { payment: "vendor", receipt: "customer" };

/**
 * Premium "Record Bank Entry" screen — Basic Info / Accounting / Reconciliation
 * / Attachments / Audit tabs + a live Bank Summary sidebar, backed by the real
 * voucher engine (POST /voucher-engine, not the legacy thin /ledger/bank-entries
 * endpoint) so GST/TDS/TCS, attachments and maker-checker approval are real,
 * not decorative.
 *
 * Deliberately NOT included (called out in the UI instead of faked): AI
 * suggestions/duplicate-detection, OFX/QIF/MT940 import, OTP/signature
 * approval, offline draft save, auto-save. See the PR description for why.
 */
export default function BankEntryModal({ open, onClose, bankAccounts, ledgers, vendors, customers, onSaved }) {
  const [tab, setTab] = useState("basic");
  const [form, setForm] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [savedVoucher, setSavedVoucher] = useState(null); // set once created — unlocks Reconciliation/Audit
  const [summary, setSummary] = useState(null);
  const [costCenters, setCostCenters] = useState([]);
  const [auditEntries, setAuditEntries] = useState([]);
  const [auditDenied, setAuditDenied] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [quickCreate, setQuickCreate] = useState(null); // { type, seed } | null
  const [invoiceOutstanding, setInvoiceOutstanding] = useState([]);
  const [dupWarning, setDupWarning] = useState(null);
  const formRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setForm(blank());
    setSavedVoucher(null);
    setSummary(null);
    setAuditEntries([]);
    setAuditDenied(false);
    setInvoiceOutstanding([]);
    setDupWarning(null);
    setTab("basic");
    api.get("/budget/cost-centers").then((r) => setCostCenters(r.data || [])).catch(() => setCostCenters([]));
  }, [open]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  // Party list source, filtered by Transaction Type (spec: Payment→active
  // vendors, Receipt→active customers). PartySearch does its own local
  // name/gstin/phone/email search over whatever list it's given.
  const partyType = PARTY_TYPE_BY_TXN[form.txnType] || null;
  const partyOptions = useMemo(() => {
    const source = partyType === "vendor" ? vendors : partyType === "customer" ? customers : [];
    return (source || []).filter((p) => p.is_active !== false);
  }, [partyType, vendors, customers]);

  // Clear a selected party when Transaction Type changes to one with a
  // different (or no) party list — a vendor selected under Payment has no
  // meaning once switched to Receipt.
  useEffect(() => {
    if (form.partyId && form.partyType !== partyType) {
      set({ partyId: "", partyType: "", partyName: "", partySummary: null, allocations: {} });
      setInvoiceOutstanding([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partyType]);

  const selectedAccount = useMemo(
    () => bankAccounts.find((a) => a.id === form.bankAccountId) || null,
    [bankAccounts, form.bankAccountId]
  );

  const loadSummary = useCallback((accountId) => {
    if (!accountId) { setSummary(null); return; }
    api.get(`/ledger/bank-accounts/${accountId}/today-summary`)
      .then((r) => setSummary(r.data))
      .catch(() => setSummary(null));
  }, []);

  useEffect(() => { loadSummary(form.bankAccountId); }, [form.bankAccountId, loadSummary]);

  const loadAudit = useCallback((voucherId) => {
    if (!voucherId) return;
    api.get("/audit", { params: { entity_type: "vouchers_v2", entity_id: voucherId, limit: 50 } })
      .then((r) => { setAuditEntries(r.data?.items || []); setAuditDenied(false); })
      .catch((e) => {
        if (e.response?.status === 403) setAuditDenied(true);
        else setAuditEntries([]);
      });
  }, []);

  const ledgerOptions = useMemo(
    () => (ledgers || []).map((l) => ({ value: l.id, label: l.name, sublabel: l.coa_account_id })),
    [ledgers]
  );

  const applyTemplate = (tpl) => {
    set({ txnType: tpl.type, paymentMode: tpl.mode, narration: form.narration || tpl.narration });
    toast.success(`"${tpl.label}" template applied`);
  };

  const refField = REF_FIELD_BY_MODE[form.paymentMode];

  // Ledger side auto-suggestion: the selected bank account's own ledger fills
  // the Debit side for a Payment (money leaving the bank) or Credit side for
  // a Receipt (money entering) — the OTHER side is still the user's choice
  // (which expense/income/party ledger). This is a fixed rule, not an AI
  // suggestion — kept simple and deterministic.
  useEffect(() => {
    if (!selectedAccount?.ledger_id) return;
    if (form.txnType === "payment") set({ creditLedgerId: form.creditLedgerId || selectedAccount.ledger_id });
    else if (form.txnType === "receipt") set({ debitLedgerId: form.debitLedgerId || selectedAccount.ledger_id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccount, form.txnType]);

  // Party selected → autofill ledger/GST/PAN/contact/outstanding/credit-limit
  // from the real party-summary endpoint, and fill whichever ledger side the
  // bank-account effect above didn't already claim (the OTHER side of a
  // Payment/Receipt is the party's own ledger — Dr party on a Receipt inflow
  // isn't right; the party is the counter-party to the bank, so it takes the
  // side the bank ledger effect leaves open).
  const selectParty = async (id, party) => {
    if (!id || !party) {
      set({ partyId: "", partyType: "", partyName: "", partySummary: null, allocations: {} });
      setInvoiceOutstanding([]);
      return;
    }
    set({ partyId: id, partyType, partyName: party.name || party.company || "" });
    try {
      const { data } = await api.get("/debtors-creditors/party-summary", { params: { party_type: partyType, party_id: id } });
      set({ partySummary: data });
      if (data.ledger_id) {
        if (form.txnType === "payment") set({ debitLedgerId: data.ledger_id });
        else if (form.txnType === "receipt") set({ creditLedgerId: data.ledger_id });
      }
      if (data.outstanding_balance > 0) {
        const { data: rows } = await api.get("/debtors-creditors/invoice-outstanding", { params: { party_type: partyType, party_id: id } });
        setInvoiceOutstanding(rows?.items || rows || []);
      } else {
        setInvoiceOutstanding([]);
      }
    } catch {
      toast.error("Failed to load party details");
    }
  };

  const setAllocation = (invoiceId, value) =>
    set({ allocations: { ...form.allocations, [invoiceId]: value } });

  const totalAllocated = useMemo(
    () => Object.values(form.allocations).reduce((sum, v) => sum + (Number(v) || 0), 0),
    [form.allocations]
  );

  // Auto Allocation: fill oldest-first up to the entered Amount. Pure
  // client-side FIFO — no backend AI/suggestion involved.
  const autoAllocate = () => {
    let remaining = Number(form.amount) || 0;
    const next = {};
    const sorted = [...invoiceOutstanding].sort((a, b) => (a.entry_date || "").localeCompare(b.entry_date || ""));
    for (const inv of sorted) {
      if (remaining <= 0) break;
      const due = Number(inv.outstanding) || 0;
      const take = Math.min(due, remaining);
      if (take > 0) next[inv.id] = take;
      remaining -= take;
    }
    set({ allocations: next });
    toast.success("Auto-allocated oldest invoices first");
  };

  // Duplicate reference warning — checked on blur of whichever ref field is
  // active, non-blocking (banks do sometimes legitimately reuse references
  // across different instruments/accounts).
  const checkDuplicateReference = async () => {
    const value = form.referenceNumber || form.chequeNumber || form.utrNumber || form.transactionId;
    if (!value) { setDupWarning(null); return; }
    try {
      const { data } = await api.get("/ledger/check-duplicate-reference", {
        params: { value, exclude_voucher_id: savedVoucher?.id || undefined },
      });
      setDupWarning(data.duplicate ? data : null);
    } catch {
      setDupWarning(null);
    }
  };

  const buildStatutory = () => {
    const gst = form.gstApplicable && form.gstRate
      ? { gst_rate: Number(form.gstRate), taxable_value: Number(form.amount) || 0 }
      : null;
    const tds = form.tdsRate ? { rate: Number(form.tdsRate) } : null;
    const tcs = form.tcsRate ? { rate: Number(form.tcsRate) } : null;
    if (!gst && !tds && !tcs) return null;
    return { gst, tds, tcs };
  };

  const validate = () => {
    if (!form.bankAccountId) return "Select a bank account";
    if (!form.amount || Number(form.amount) <= 0) return "Enter an amount greater than zero";
    if (!form.debitLedgerId || !form.creditLedgerId) return "Select both the Debit and Credit ledger";
    if (form.debitLedgerId === form.creditLedgerId) return "Debit and Credit ledger must be different";
    if (partyType && !form.partyId) return `Select a ${partyType === "vendor" ? "Vendor" : "Customer"}`;
    if (totalAllocated > Number(form.amount) + 1e-6) return "Allocated amount exceeds the entry Amount";
    return null;
  };

  // Non-blocking warnings — spec says "Warn," not "Prevent," for these.
  const softWarnings = () => {
    const warnings = [];
    if (form.partySummary?.credit_limit > 0) {
      const projected = (form.partySummary.outstanding_balance || 0) + (form.txnType === "receipt" ? -Number(form.amount || 0) : Number(form.amount || 0));
      if (form.txnType === "payment" && projected > form.partySummary.credit_limit) {
        warnings.push(`Credit limit ₹${inr(form.partySummary.credit_limit)} exceeded — projected outstanding ₹${inr(projected)}`);
      }
    }
    if (form.partySummary && !form.partySummary.gstin && !form.partySummary.pan) {
      warnings.push(`${form.partyName} has no GSTIN or PAN on file`);
    }
    if (dupWarning) {
      warnings.push(`Reference already used on voucher ${dupWarning.voucher_no} (${dupWarning.date})`);
    }
    return warnings;
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    const error = validate();
    if (error) { toast.error(error); return; }
    for (const w of softWarnings()) toast.warning(w);
    if (saving) return;
    setSaving(true);
    try {
      const amount = Number(form.amount);
      const payload = {
        parent_type: form.txnType === "receipt" ? "receipt" : form.txnType === "contra" ? "contra" : "payment",
        date: form.date,
        effective_date: form.valueDate || null,
        narration: form.narration || null,
        reference_no: form.referenceNumber || form.chequeNumber || form.utrNumber || form.transactionId || null,
        party_id: form.partyId || null,
        accounting_lines: [
          { ledger_id: form.debitLedgerId, dr_cr: "Dr", amount, cost_center_id: form.costCenterId || null },
          { ledger_id: form.creditLedgerId, dr_cr: "Cr", amount, cost_center_id: form.costCenterId || null },
        ],
        statutory: buildStatutory(),
        attachments: form.attachments.map((f) => ({ name: f.name, path: f.path, content_type: f.content_type })),
      };
      const { data } = await api.post("/voucher-engine", payload);
      setSavedVoucher(data);
      toast.success(`${data.voucher_no || "Voucher"} recorded as Draft`);
      loadAudit(data.id);

      // Post to the party's AR/AP ledger + allocate against invoices, so
      // Vendor/Customer Ledger and Outstanding Report reflect this entry —
      // idempotent on the voucher id, safe to call even on a re-save.
      if (partyType && form.partyId) {
        try {
          const { data: dcEntry } = await api.post("/debtors-creditors/post-document", {
            doc_type: form.txnType === "payment" ? "PAYMENT" : "RECEIPT",
            doc_id: data.id, party_type: partyType, party_id: form.partyId,
            entry_date: form.date, amount, narration: form.narration || undefined,
          });
          const allocations = Object.entries(form.allocations)
            .filter(([, v]) => Number(v) > 0)
            .map(([invoice_entry_id, v]) => ({ invoice_entry_id, allocated_amount: Number(v) }));
          if (allocations.length > 0) {
            await api.post("/debtors-creditors/allocate-payment", {
              party_type: partyType, party_id: form.partyId,
              payment_entry_id: dcEntry.id, allocations,
            });
          }
        } catch (dcErr) {
          toast.error(formatApiErrorDetail(dcErr.response?.data?.detail) || "Voucher saved, but party ledger posting failed — check Debtors & Creditors");
        }
      }

      onSaved?.(data);
      return data;
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save bank entry");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const submitAndNew = async () => {
    const saved = await submit();
    if (saved) {
      setForm(blank());
      setSavedVoucher(null);
      setTab("basic");
    }
  };

  const uploadAttachment = async (fileList) => {
    const files = Array.from(fileList || []);
    for (const file of files) {
      const body = new FormData();
      body.append("file", file);
      try {
        const { data } = await api.post("/uploads/document", body, { headers: { "Content-Type": "multipart/form-data" } });
        set({ attachments: [...form.attachments, { name: file.name, path: data.path, content_type: data.content_type, size: file.size, url: `${API}/files/${data.path}` }] });
      } catch (err) {
        toast.error(formatApiErrorDetail(err.response?.data?.detail) || `Failed to upload ${file.name}`);
      }
    }
  };
  const removeAttachment = (idx) => set({ attachments: form.attachments.filter((_, i) => i !== idx) });

  const markCleared = async () => {
    if (!savedVoucher) return;
    setReconciling(true);
    try {
      const { data } = await api.post(`/voucher-engine/${savedVoucher.id}/reconcile`);
      setSavedVoucher(data);
      toast.success("Marked cleared / reconciled");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Reconcile failed");
    } finally {
      setReconciling(false);
    }
  };

  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(),
    onSaveAndNew: submitAndNew,
    onCancel: onClose,
    onQuickCreate: (type, fieldEl) => setQuickCreate({ type, seed: fieldEl.value }),
  });

  const handleQuickCreated = (record) => {
    const type = quickCreate?.type;
    setQuickCreate(null);
    if (type === "vendor" || type === "customer") {
      selectParty(record.id, record);
      set({ txnType: type === "vendor" ? "payment" : "receipt" });
    } else if (type === "ledger") {
      set({ debitLedgerId: form.debitLedgerId || record.id });
    }
  };

  // Alt+A / Alt+L quick-create hints only fire while this modal is open, and
  // don't intercept typing — they're modifier combos, not bare keys.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.ctrlKey && (e.key === "d" || e.key === "D")) {
        e.preventDefault();
        setForm((f) => ({ ...f, referenceNumber: "", chequeNumber: "", utrNumber: "", transactionId: "" }));
        toast.info("Reference numbers cleared for a duplicate entry — amounts and ledgers kept");
      } else if (e.ctrlKey && (e.key === "r" || e.key === "R") && savedVoucher) {
        e.preventDefault();
        markCleared();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, savedVoucher]);

  if (!open) return null;

  const statusUpper = (savedVoucher?.status || "draft").toUpperCase();

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title="Record Bank Entry"
      icon={Landmark}
      size="full"
      testid="bank-entry-modal"
      bodyClassName="p-0"
      headerExtra={savedVoucher && <StatusBadge status={statusUpper} />}
      footer={
        <>
          <SecondaryButton onClick={onClose}>Cancel (Esc)</SecondaryButton>
          <SecondaryButton onClick={submitAndNew} disabled={saving}>Save &amp; New (Ctrl+Shift+Enter)</SecondaryButton>
          <PrimaryButton onClick={submit} disabled={saving} loading={saving}>
            {savedVoucher ? "Update" : "Save"} (Ctrl+S)
          </PrimaryButton>
        </>
      }
    >
      <form ref={formRef} onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-0 h-full">
        {/* ── Main content ─────────────────────────────────────────── */}
        <div className="overflow-y-auto p-6 space-y-4">
          {/* Quick templates */}
          <div className="flex flex-wrap gap-2">
            {QUICK_TEMPLATES.map((tpl) => (
              <button
                key={tpl.label}
                type="button"
                onClick={() => applyTemplate(tpl)}
                className="px-3 py-1.5 text-xs font-medium border border-border rounded-full text-muted-foreground hover:border-primary hover:text-primary transition-colors"
              >
                {tpl.label}
              </button>
            ))}
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="basic">Basic Information</TabsTrigger>
              <TabsTrigger value="accounting">Accounting</TabsTrigger>
              <TabsTrigger value="reconciliation" disabled={!savedVoucher}>Reconciliation</TabsTrigger>
              <TabsTrigger value="attachments">Attachments</TabsTrigger>
              <TabsTrigger value="audit" onClick={() => savedVoucher && loadAudit(savedVoucher.id)}>Audit</TabsTrigger>
            </TabsList>

            {/* Tab 1 — Basic Information */}
            <TabsContent value="basic">
              <FormSection title="Bank & Transaction" icon={Landmark} cols={3}>
                <Field label="Bank Account" required>
                  <Select value={form.bankAccountId} onChange={(e) => set({ bankAccountId: e.target.value })} required>
                    <option value="">Select account…</option>
                    {bankAccounts.map((a) => <option key={a.id} value={a.id}>{a.name} — {a.bank_name}</option>)}
                  </Select>
                </Field>
                <Field label="Current Balance" hint="Live, as of last posted entry">
                  <Input readOnly value={selectedAccount ? `₹${inr(selectedAccount.current_balance)}` : "—"} />
                </Field>
                <Field label="Available Balance" hint="Overdraft/credit-limit tracking not yet built">
                  <Input readOnly value={selectedAccount ? `₹${inr(selectedAccount.current_balance)}` : "—"} />
                </Field>
                <Field label="Date" required>
                  <Input type="date" value={form.date} onChange={(e) => set({ date: e.target.value })} required />
                </Field>
                <Field label="Value Date" hint="Defaults to Date if left blank">
                  <Input type="date" value={form.valueDate} onChange={(e) => set({ valueDate: e.target.value })} />
                </Field>
                <Field label="Voucher Number">
                  <Input readOnly value={savedVoucher?.voucher_no || "Auto on save"} />
                </Field>
                <Field label="Transaction Type" required>
                  <Select value={form.txnType} onChange={(e) => set({ txnType: e.target.value })}>
                    {TXN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </Select>
                </Field>
                {partyType && (
                  <div className="md:col-span-3">
                    <Field label={partyType === "vendor" ? "Vendor" : "Customer"} required hint="Ctrl+Enter in the field also quick-creates">
                      <div className="flex items-center gap-2">
                        <div className="flex-1">
                          <PartySearch
                            parties={partyOptions}
                            value={form.partyId}
                            onChange={selectParty}
                            placeholder={`Search ${partyType === "vendor" ? "vendor" : "customer"} by name, GSTIN, mobile or email…`}
                            quickCreateType={partyType}
                            testid="bank-entry-party"
                          />
                        </div>
                        <SecondaryButton onClick={() => setQuickCreate({ type: partyType, seed: "" })}>
                          New {partyType === "vendor" ? "Vendor" : "Customer"}
                        </SecondaryButton>
                        <SecondaryButton onClick={() => setQuickCreate({ type: "ledger", seed: "" })}>
                          New Ledger
                        </SecondaryButton>
                      </div>
                    </Field>
                    {form.partySummary && (
                      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1.5 text-xs text-muted-foreground bg-muted/30 rounded-lg p-3">
                        <span><b className="text-foreground">GSTIN:</b> {form.partySummary.gstin || "—"}</span>
                        <span><b className="text-foreground">PAN:</b> {form.partySummary.pan || "—"}</span>
                        <span><b className="text-foreground">Contact:</b> {form.partySummary.contact_person || "—"} {form.partySummary.mobile && `· ${form.partySummary.mobile}`}</span>
                        <span><b className="text-foreground">Email:</b> {form.partySummary.email || "—"}</span>
                        <span className="md:col-span-2 truncate"><b className="text-foreground">Address:</b> {form.partySummary.address || "—"} {form.partySummary.state && `(${form.partySummary.state})`}</span>
                        <span><b className="text-foreground">Outstanding:</b> ₹{inr(form.partySummary.outstanding_balance)}</span>
                        <span><b className="text-foreground">Credit Limit:</b> {form.partySummary.credit_limit > 0 ? `₹${inr(form.partySummary.credit_limit)}` : "—"}</span>
                      </div>
                    )}
                  </div>
                )}
                <Field label="Payment Mode">
                  <Select value={form.paymentMode} onChange={(e) => set({ paymentMode: e.target.value })}>
                    {PAYMENT_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                  </Select>
                </Field>
                <Field label="Amount (₹)" required>
                  <NumericInput value={form.amount} onChange={(v) => set({ amount: v })} placeholder="0.00" align="left" />
                </Field>
                <Field label="Currency" hint="Multi-currency conversion not yet built">
                  <Select value={form.currency} onChange={(e) => set({ currency: e.target.value })}>
                    <option value="INR">INR</option>
                  </Select>
                </Field>
                <Field label="Reference Number">
                  <Input value={form.referenceNumber} onChange={(e) => set({ referenceNumber: e.target.value })} onBlur={checkDuplicateReference} />
                </Field>
                {refField && (
                  <Field label={refField.label}>
                    <Input
                      value={form[refField.key === "cheque_number" ? "chequeNumber" : refField.key === "utr_number" ? "utrNumber" : "transactionId"]}
                      onChange={(e) => set({ [refField.key === "cheque_number" ? "chequeNumber" : refField.key === "utr_number" ? "utrNumber" : "transactionId"]: e.target.value })}
                      onBlur={checkDuplicateReference}
                    />
                  </Field>
                )}
                {dupWarning && (
                  <div className="md:col-span-3 flex items-center gap-2 text-xs text-[var(--warning)] bg-[var(--warning)]/10 rounded-lg px-3 py-2">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                    This reference was already used on voucher {dupWarning.voucher_no} ({dupWarning.date}) — likely a duplicate entry.
                  </div>
                )}
                <div className="md:col-span-3">
                  <Field label="Narration">
                    <Textarea rows={2} value={form.narration} onChange={(e) => set({ narration: e.target.value })} />
                  </Field>
                </div>
              </FormSection>
            </TabsContent>

            {/* Tab 2 — Accounting */}
            <TabsContent value="accounting">
              <FormSection title="Ledger Posting" icon={ArrowRightLeft} cols={2}>
                <Field label="Debit Ledger" required hint="Alt+L to add a new ledger">
                  <SearchableSelect
                    options={ledgerOptions}
                    value={form.debitLedgerId}
                    onChange={(v) => set({ debitLedgerId: v })}
                    placeholder="Search ledger…"
                  />
                </Field>
                <Field label="Credit Ledger" required>
                  <SearchableSelect
                    options={ledgerOptions}
                    value={form.creditLedgerId}
                    onChange={(v) => set({ creditLedgerId: v })}
                    placeholder="Search ledger…"
                  />
                </Field>
                <Field label="Cost Center">
                  <Select value={form.costCenterId} onChange={(e) => set({ costCenterId: e.target.value })}>
                    <option value="">— None —</option>
                    {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </Select>
                </Field>
                <Field label="Project / Department / Employee" hint="Not yet available as ledger dimensions in this app">
                  <Input disabled placeholder="Coming soon" />
                </Field>
                <Field label="GST Applicable">
                  <label className="flex items-center gap-2 h-[46px] text-sm text-foreground">
                    <input type="checkbox" checked={form.gstApplicable} onChange={(e) => set({ gstApplicable: e.target.checked })} className="w-4 h-4" />
                    Apply GST to this entry
                  </label>
                </Field>
                {form.gstApplicable && (
                  <Field label="GST Rate %">
                    <NumericInput value={form.gstRate} onChange={(v) => set({ gstRate: v })} align="left" />
                  </Field>
                )}
                <Field label="TDS Rate %">
                  <NumericInput value={form.tdsRate} onChange={(v) => set({ tdsRate: v })} align="left" />
                </Field>
                <Field label="TCS Rate %">
                  <NumericInput value={form.tcsRate} onChange={(v) => set({ tcsRate: v })} align="left" />
                </Field>
                <Field label="Bank Charges (₹)" hint="Not auto-calculated — enter manually">
                  <NumericInput value={form.bankCharges} onChange={(v) => set({ bankCharges: v })} align="left" />
                </Field>
                <Field label="Round Off (₹)">
                  <NumericInput value={form.roundOff} onChange={(v) => set({ roundOff: v })} align="left" />
                </Field>
              </FormSection>
              <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                <Info className="w-3.5 h-3.5 flex-shrink-0" />
                Debit and Credit ledgers auto-balance to the Amount entered above — this is a simple two-line entry, not a multi-line journal grid.
                {form.partySummary?.tds_applicable && !form.tdsRate && " This party has TDS applicable — set a TDS Rate above if this payment attracts it."}
              </p>

              {form.partyId && invoiceOutstanding.length > 0 && (
                <FormSection
                  title="Bill-wise Adjustment"
                  icon={Wand2}
                  cols={1}
                  className="mt-4"
                  actions={<SecondaryButton onClick={autoAllocate}>Auto Allocation</SecondaryButton>}
                >
                  <div className="overflow-x-auto -mx-6 -mb-6">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-muted-foreground border-b border-border">
                          <th className="px-6 py-2">Invoice No.</th>
                          <th className="px-2 py-2">Date</th>
                          <th className="px-2 py-2">Due Date</th>
                          <th className="px-2 py-2 text-right">Outstanding</th>
                          <th className="px-6 py-2 text-right w-40">Allocate (₹)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invoiceOutstanding.map((inv) => (
                          <tr key={inv.id} className="border-b border-border/60">
                            <td className="px-6 py-2 font-medium text-foreground">{inv.voucher_no}</td>
                            <td className="px-2 py-2 text-muted-foreground">{inv.entry_date}</td>
                            <td className="px-2 py-2 text-muted-foreground">{inv.due_date || "—"}</td>
                            <td className="px-2 py-2 text-right font-mono tabular text-foreground">₹{inr(inv.outstanding)}</td>
                            <td className="px-6 py-2">
                              <NumericInput
                                value={form.allocations[inv.id] || ""}
                                onChange={(v) => setAllocation(inv.id, v)}
                                max={inv.outstanding}
                                align="right"
                                compact
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <td colSpan={4} className="px-6 py-2.5 text-right text-xs font-semibold text-foreground">Allocated / Amount</td>
                          <td className="px-6 py-2.5 text-right font-mono tabular font-semibold text-foreground">
                            ₹{inr(totalAllocated)} / ₹{inr(Number(form.amount) || 0)}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </FormSection>
              )}
            </TabsContent>

            {/* Tab 3 — Reconciliation */}
            <TabsContent value="reconciliation">
              {!savedVoucher ? (
                <p className="text-sm text-muted-foreground p-4">Save the entry first — reconciliation applies to a posted voucher.</p>
              ) : (
                <FormSection title="Reconciliation" icon={FileCheck2} cols={2}>
                  <Field label="Status">
                    <div className="h-[46px] flex items-center"><StatusBadge status={statusUpper} /></div>
                  </Field>
                  <Field label="Cleared / Statement Date">
                    <Input readOnly value={savedVoucher.status === "reconciled" ? (savedVoucher.updated_at || "").split("T")[0] : "Not yet cleared"} />
                  </Field>
                  <div className="md:col-span-2 flex flex-wrap gap-2 pt-2">
                    <SecondaryButton icon={CheckCircle2} onClick={markCleared} disabled={reconciling || savedVoucher.status === "reconciled" || savedVoucher.status !== "posted"} loading={reconciling}>
                      Mark Cleared (Ctrl+R)
                    </SecondaryButton>
                    <SecondaryButton icon={RotateCcw} disabled title="Coming soon — undo-reconcile endpoint not yet built">
                      Undo Reconciliation
                    </SecondaryButton>
                    <SecondaryButton icon={Sparkles} disabled title="Coming soon — no bank-statement matching engine wired to this modal yet">
                      Auto Match
                    </SecondaryButton>
                    <SecondaryButton disabled title="Coming soon">
                      Match Statement
                    </SecondaryButton>
                  </div>
                  {savedVoucher.status !== "posted" && savedVoucher.status !== "reconciled" && (
                    <p className="md:col-span-2 text-xs text-muted-foreground">
                      This entry is still in "{statusUpper}" status — it must be approved and posted before it can be reconciled.
                    </p>
                  )}
                </FormSection>
              )}
            </TabsContent>

            {/* Tab 4 — Attachments */}
            <TabsContent value="attachments">
              <FormSection title="Attachments" icon={Paperclip} cols={1}>
                <AttachmentsField
                  files={form.attachments}
                  onAdd={uploadAttachment}
                  onRemove={removeAttachment}
                  accept="image/*,application/pdf"
                />
              </FormSection>
            </TabsContent>

            {/* Tab 5 — Audit */}
            <TabsContent value="audit">
              <FormSection title="Audit Trail" icon={ShieldCheck} cols={1}>
                {!savedVoucher ? (
                  <p className="text-sm text-muted-foreground">Save the entry first to see its history.</p>
                ) : auditDenied ? (
                  <p className="text-sm text-muted-foreground">Audit history requires Auditor or Admin access.</p>
                ) : (
                  <AuditTrail
                    entries={auditEntries.map((e) => ({
                      actor: e.user_email || e.user_id,
                      action: e.action,
                      at: (e.created_at || "").replace("T", " ").slice(0, 19),
                      note: e.action === "CREATE" ? "Entry created as Draft" : undefined,
                    }))}
                  />
                )}
              </FormSection>
            </TabsContent>
          </Tabs>
        </div>

        {/* ── Right sidebar — Live Bank Summary ────────────────────── */}
        <div className="border-l border-border bg-muted/20 p-6 overflow-y-auto">
          <SummaryCard
            title="Live Bank Summary"
            sticky
            rows={[
              { label: "Current Balance", value: selectedAccount ? `₹${inr(selectedAccount.current_balance)}` : "—", strong: true },
              { label: "Today's Credits", value: summary ? `₹${inr(summary.today_credits)}` : "—", tone: "success" },
              { label: "Today's Debits", value: summary ? `₹${inr(summary.today_debits)}` : "—", tone: "danger", dividerBefore: true },
            ]}
            footer={
              !selectedAccount ? (
                <span className="text-xs text-muted-foreground">Select a bank account to see live figures.</span>
              ) : (
                <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5 flex-shrink-0" />
                  Credit limit, overdraft and cash-flow graph are not yet tracked per account.
                </span>
              )
            }
          />
        </div>
      </form>
    </Modal>

    <QuickCreateModal
      open={!!quickCreate}
      type={quickCreate?.type}
      seedName={quickCreate?.seed}
      onClose={() => setQuickCreate(null)}
      onCreated={handleQuickCreated}
    />
    </>
  );
}
