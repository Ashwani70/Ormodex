import { useState, useEffect, useCallback, useRef } from "react";
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
  NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, RefreshCw, Landmark, ArrowUpDown, GitMerge, BookCopy, CheckCircle2 } from "lucide-react";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const TABS = [
  { id: "bank-accounts", label: "Bank Accounts" },
  { id: "bank-entries", label: "Bank Entries" },
  { id: "party-ledger", label: "Party Ledger" },
  { id: "outstanding", label: "Outstanding" },
  { id: "ageing", label: "Ageing Report" },
  { id: "reconciliation", label: "Bank Reconciliation" },
  { id: "cheques", label: "Cheque Register" },
];

export default function Ledger() {
  const [tab, setTab] = useState("bank-accounts");
  const [bankAccounts, setBankAccounts] = useState([]);
  const [bankEntries, setBankEntries] = useState([]);
  const [partyLedger, setPartyLedger] = useState(null);
  const [outstanding, setOutstanding] = useState([]);
  const [ageing, setAgeing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showBankModal, setShowBankModal] = useState(false);
  const [showEntryModal, setShowEntryModal] = useState(false);
  const [partyType, setPartyType] = useState("CUSTOMER");
  const [selectedBank, setSelectedBank] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const [bankForm, setBankForm] = useState({
    name: "", bank_name: "", account_number: "", ifsc: "",
    account_type: "CURRENT", opening_balance: "", currency: "INR",
  });
  const [chequeForm, setChequeForm] = useState({
    cheque_number: "", bank_account_code: "", cheque_type: "ISSUED",
    party_name: "", amount: "", cheque_date: new Date().toISOString().split("T")[0],
    status: "PENDING", remarks: "",
  });
  const [entryForm, setEntryForm] = useState({
    bank_account_id: "", date: new Date().toISOString().split("T")[0],
    entry_type: "CREDIT", amount: "", description: "", reference: "",
  });
  const [stmtForm, setStmtForm] = useState({
    bank_account_code: "", transaction_date: new Date().toISOString().split("T")[0],
    description: "", debit: "", credit: "", ref_number: "",
  });
  const [cheques, setCheques] = useState([]);
  const [stmts, setStmts] = useState([]);
  const [reconReport, setReconReport] = useState(null);
  const [reconAccCode, setReconAccCode] = useState("");
  const [reconAsOf, setReconAsOf] = useState(new Date().toISOString().split("T")[0]);
  const [coa, setCoa] = useState([]);
  const [showStmtForm, setShowStmtForm] = useState(false);
  const [showChequeForm, setShowChequeForm] = useState(false);



  const loadBankAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/ledger/bank-accounts");
      setBankAccounts(r.data);
    } finally { setLoading(false); }
  }, []);

  const loadBankEntries = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (selectedBank) params.bank_account_id = selectedBank;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/ledger/bank-entries", { params });
      setBankEntries(r.data.items || []);
    } finally { setLoading(false); }
  }, [selectedBank, fromDate, toDate]);

  const loadPartyLedger = useCallback(async () => {
    setLoading(true);
    try {
      const params = { party_type: partyType };
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/ledger/party-ledger", { params });
      setPartyLedger(r.data);
    } finally { setLoading(false); }
  }, [partyType, fromDate, toDate]);

  const loadOutstanding = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/ledger/party-outstanding", { params: { party_type: partyType } });
      setOutstanding(r.data);
    } finally { setLoading(false); }
  }, [partyType]);

  const loadAgeing = useCallback(async () => {
    setLoading(true);
    try {
      const params = { party_type: partyType };
      if (toDate) params.as_of_date = toDate;
      const r = await api.get("/ledger/ageing-report", { params });
      setAgeing(r.data);
    } finally { setLoading(false); }
  }, [partyType, toDate]);

  useEffect(() => {
    if (tab === "bank-accounts") loadBankAccounts();
    if (tab === "bank-entries") { loadBankAccounts(); loadBankEntries(); }
    if (tab === "party-ledger") loadPartyLedger();
    if (tab === "outstanding") loadOutstanding();
    if (tab === "ageing") loadAgeing();
    if (tab === "reconciliation") {
      api.get("/accounting/chart-of-accounts")
        .then(r => setCoa(r.data || []))
        .catch(() => toast.error("Failed to load chart of accounts"));
      api.get("/banking/statements")
        .then(r => setStmts(r.data?.items || []))
        .catch(() => toast.error("Failed to load banking statements"));
    }
    if (tab === "cheques") {
      api.get("/banking/cheques")
        .then(r => setCheques(r.data?.items || []))
        .catch(e => toast.error(e.response?.data?.detail || "Failed to load cheques"));
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps


  const createBankAccount = async (e) => {
    e.preventDefault();
    try {
      await api.post("/ledger/bank-accounts", { ...bankForm, opening_balance: parseFloat(bankForm.opening_balance) });
      toast.success("Bank account created");
      setShowBankModal(false);
      setBankForm({ name: "", bank_name: "", account_number: "", ifsc: "", account_type: "CURRENT", opening_balance: "", currency: "INR" });
      loadBankAccounts();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  // Enter-as-Tab across the Add Bank Account form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels, first field auto-focuses when the modal opens. This is the
  // page's primary create action, so it also owns the Ctrl+N shortcut.
  const bankFormRef = useRef(null);
  useEnterNavigation(bankFormRef, {
    enabled: showBankModal,
    autoFocus: true,
    onSave: () => createBankAccount(new Event("submit", { cancelable: true })),
    onCancel: () => setShowBankModal(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!showBankModal) setShowBankModal(true); },
  });

  const createBankEntry = async (e) => {
    e.preventDefault();
    try {
      await api.post("/ledger/bank-entries", { ...entryForm, amount: parseFloat(entryForm.amount) });
      toast.success("Bank entry recorded");
      setShowEntryModal(false);
      loadBankEntries();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  // Secondary form (Add Entry) — Enter-as-Tab + Ctrl+Enter/Ctrl+S save + Esc
  // cancel, no Ctrl+N wiring here (owned by the bank-account form above).
  const entryFormRef = useRef(null);
  useEnterNavigation(entryFormRef, {
    enabled: showEntryModal,
    autoFocus: true,
    onSave: () => createBankEntry(new Event("submit", { cancelable: true })),
    onCancel: () => setShowEntryModal(false),
  });

  const createStmt = async () => {
    try {
      await api.post("/banking/statements", { ...stmtForm, debit: parseFloat(stmtForm.debit), credit: parseFloat(stmtForm.credit) });
      toast.success("Statement line added");
      setShowStmtForm(false);
      const r = await api.get("/banking/statements");
      setStmts(r.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const autoMatch = async () => {
    if (!reconAccCode) { toast.error("Select a bank account code first"); return; }
    try {
      const res = await api.post(`/banking/reconcile/auto-match?bank_account_code=${reconAccCode}`);
      toast.success(res.data.message);
    } catch (e) { toast.error("Auto-match failed"); }
  };

  const loadReconReport = async () => {
    if (!reconAccCode) { toast.error("Select a bank account code"); return; }
    try {
      const res = await api.get(`/banking/reconcile/report?bank_account_code=${reconAccCode}&as_of_date=${reconAsOf}`);
      setReconReport(res.data);
    } catch (e) { toast.error("Failed to load reconciliation report"); }
  };

  const createCheque = async () => {
    try {
      await api.post("/banking/cheques", { ...chequeForm, amount: parseFloat(chequeForm.amount) });
      toast.success("Cheque logged");
      setShowChequeForm(false);
      const r = await api.get("/banking/cheques");
      setCheques(r.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const updateChequeStatus = async (id, status) => {
    await api.patch(`/banking/cheques/${id}`, { status });
    toast.success(`Cheque marked ${status}`);
    const r = await api.get("/banking/cheques");
    setCheques(r.data?.items || []);
  };


  const totalBalance = bankAccounts.reduce((s, a) => s + (a.current_balance || 0), 0);

  return (
    <div data-testid="ledger-page">
      <PageHeader
        eyebrow="Finance"
        title="Ledger & Bank"
        description="Bank accounts, cash & bank entries, party ledger and ageing analysis."
        actions={
          <>
            {tab === "bank-accounts" && (
              <PrimaryButton icon={Plus} onClick={() => setShowBankModal(true)} testid="add-bank-account-btn">
                Add Bank Account
              </PrimaryButton>
            )}
            {tab === "bank-entries" && (
              <PrimaryButton icon={Plus} onClick={() => setShowEntryModal(true)} testid="add-bank-entry-btn">
                Add Entry
              </PrimaryButton>
            )}
          </>
        }
      />

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-yellow-400 text-black font-bold" : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Party type switcher (for party tabs) */}
      {["party-ledger", "outstanding", "ageing"].includes(tab) && (
        <div className="flex gap-2 mb-4">
          <span className="label-overline self-center">Party Type:</span>
          {[["CUSTOMER", "Customer"], ["SUPPLIER", "Vendor"]].map(([val, label]) => (
            <button key={val} onClick={() => { setPartyType(val); }} className={`px-3 py-1.5 text-xs font-mono uppercase border transition-colors ${partyType === val ? "border-yellow-400 bg-yellow-400 text-black" : "border-zinc-700 text-zinc-400 hover:border-yellow-400"}`}>{label}</button>
          ))}
          <SecondaryButton icon={RefreshCw} onClick={() => {
            if (tab === "party-ledger") loadPartyLedger();
            if (tab === "outstanding") loadOutstanding();
            if (tab === "ageing") loadAgeing();
          }}>Refresh</SecondaryButton>
        </div>
      )}

      {loading && <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>}

      {/* Bank Accounts */}
      {!loading && tab === "bank-accounts" && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
            <StatTile label="Total Accounts" value={bankAccounts.length} />
            <StatTile label="Total Balance" value={`₹${inr(totalBalance)}`} accent />
          </div>
          {bankAccounts.length === 0 ? (
            <EmptyState message="No bank accounts" action={<PrimaryButton icon={Plus} onClick={() => setShowBankModal(true)}>Add Account</PrimaryButton>} />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bankAccounts.map(acc => (
                <div key={acc.id} className="border border-zinc-800 bg-zinc-900 p-4 hover:border-yellow-400 transition-colors">
                  <div className="flex items-start gap-3 mb-3">
                    <div className="w-10 h-10 bg-yellow-400 flex items-center justify-center">
                      <Landmark className="w-5 h-5 text-black" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-white">{acc.name}</div>
                      <div className="text-xs text-zinc-500 font-mono">{acc.bank_name}</div>
                    </div>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between"><span className="text-zinc-500">Account No</span><span className="font-mono text-zinc-300">{acc.account_number}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">IFSC</span><span className="font-mono text-zinc-300">{acc.ifsc || acc.ifsc_code}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">Type</span><span className="text-zinc-300">{acc.account_type}</span></div>
                  </div>
                  <div className="mt-3 pt-3 border-t border-zinc-800">
                    <div className="flex justify-between items-center">
                      <span className="text-xs label-overline">Current Balance</span>
                      <span className={`font-display font-black text-xl ${(acc.current_balance || 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        ₹{inr(acc.current_balance)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Bank Entries */}
      {!loading && tab === "bank-entries" && (
        <>
          <div className="flex gap-2 mb-4">
            <Select value={selectedBank} onChange={e => setSelectedBank(e.target.value)} className="w-48">
              <option value="">All Accounts</option>
              {bankAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
            <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
            <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
            <SecondaryButton icon={RefreshCw} onClick={loadBankEntries}>Filter</SecondaryButton>
          </div>
          {bankEntries.length === 0 ? (
            <EmptyState message="No bank entries" />
          ) : (
            <table className="w-full text-sm border border-zinc-800">
              <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-left px-4 py-2">Description</th>
                <th className="text-left px-4 py-2">Reference</th>
                <th className="text-left px-4 py-2">Type</th>
                <th className="text-right px-4 py-2">Amount</th>
                <th className="text-left px-4 py-2">Reconciled</th>
              </tr></thead>
              <tbody>
                {bankEntries.map((e, i) => (
                  <tr key={e.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-zinc-400 text-xs">{e.date}</td>
                    <td className="px-4 py-2 text-white text-xs">{e.description}</td>
                    <td className="px-4 py-2 font-mono text-xs text-zinc-400">{e.reference || e.reference_number || "—"}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${e.entry_type === "CREDIT" ? "border-green-800 bg-green-950 text-green-400" : "border-red-800 bg-red-950 text-red-400"}`}>{e.entry_type}</span>
                    </td>
                    <td className={`px-4 py-2 text-right tabular font-semibold ${e.entry_type === "CREDIT" ? "text-green-400" : "text-red-400"}`}>
                      {e.entry_type === "CREDIT" ? "+" : "-"}₹{inr(e.amount)}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] ${e.is_reconciled ? "text-green-400" : "text-zinc-500"}`}>{e.is_reconciled ? "✓ Yes" : "—"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {/* Outstanding */}
      {!loading && tab === "outstanding" && (
        <table className="w-full text-sm border border-zinc-800">
          <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
            <th className="text-left px-4 py-2">Party</th>
            <th className="text-right px-4 py-2">Total Amount</th>
            <th className="text-right px-4 py-2">Paid</th>
            <th className="text-right px-4 py-2">Outstanding</th>
            <th className="text-right px-4 py-2">Count</th>
          </tr></thead>
          <tbody>
            {outstanding.map((r, i) => (
              <tr key={r._id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                <td className="px-4 py-2 text-white">{r.party_name || "—"}</td>
                <td className="px-4 py-2 text-right tabular">₹{inr(r.total_amount)}</td>
                <td className="px-4 py-2 text-right tabular text-green-400">₹{inr(r.paid_amount)}</td>
                <td className="px-4 py-2 text-right tabular font-bold text-red-400">₹{inr(r.outstanding)}</td>
                <td className="px-4 py-2 text-right text-zinc-400">{r.count}</td>
              </tr>
            ))}
            {outstanding.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-zinc-500 font-mono text-xs">No outstanding amounts</td></tr>
            )}
          </tbody>
        </table>
      )}

      {/* Ageing Report */}
      {!loading && tab === "ageing" && ageing && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-3 mb-4">
            {Object.entries(ageing.totals).map(([bucket, total]) => (
              <StatTile key={bucket} label={`${bucket} days`} value={`₹${inr(total)}`} accent={bucket === "90+"} />
            ))}
          </div>
          {Object.entries(ageing.buckets).map(([bucket, items]) => (
            items.length > 0 && (
              <div key={bucket}>
                <SectionTitle>
                  <span className={bucket === "90+" ? "text-red-400" : bucket === "61-90" ? "text-yellow-400" : "text-white"}>
                    {bucket} Days — {items.length} items
                  </span>
                </SectionTitle>
                <table className="w-full text-xs border border-zinc-800 mb-4">
                  <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                    <th className="text-left px-3 py-2">Party</th>
                    <th className="text-left px-3 py-2">Invoice/PO</th>
                    <th className="text-left px-3 py-2">Date</th>
                    <th className="text-right px-3 py-2">Age (days)</th>
                    <th className="text-right px-3 py-2">Outstanding</th>
                  </tr></thead>
                  <tbody>
                    {items.map(item => (
                      <tr key={item.id} className="border-b border-zinc-900 hover:bg-zinc-900">
                        <td className="px-3 py-2 text-white">{item.party_name}</td>
                        <td className="px-3 py-2 font-mono text-yellow-400">{item.invoice_no}</td>
                        <td className="px-3 py-2 text-zinc-400">{item.date}</td>
                        <td className="px-3 py-2 text-right tabular text-orange-400">{item.age_days}</td>
                        <td className="px-3 py-2 text-right tabular font-semibold text-red-400">₹{inr(item.outstanding)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ))}
        </div>
      )}

      {/* Bank Reconciliation Tab */}
      {tab === "reconciliation" && (
        <div className="space-y-5">
          {/* Controls */}
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <span className="label-overline block mb-1">Bank Account (CoA Code)</span>
              <select value={reconAccCode} onChange={e => setReconAccCode(e.target.value)}
                className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400 w-52">
                <option value="">Select account...</option>
                {coa.filter(a => a.account_type === "ASSET").map(a => (
                  <option key={a.code} value={a.code}>{a.code} — {a.name}</option>
                ))}
              </select>
            </div>
            <div>
              <span className="label-overline block mb-1">As of Date</span>
              <input type="date" value={reconAsOf} onChange={e => setReconAsOf(e.target.value)}
                className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <button onClick={loadReconReport}
              className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2">
              <BookCopy className="w-3.5 h-3.5" /> Generate Report
            </button>
            <button onClick={autoMatch}
              className="flex items-center gap-2 border border-blue-700 text-blue-400 hover:bg-blue-950 text-xs font-mono uppercase px-3 py-2">
              <GitMerge className="w-3.5 h-3.5" /> Auto Match
            </button>
            <button onClick={() => setShowStmtForm(!showStmtForm)}
              className="flex items-center gap-2 border border-zinc-700 text-zinc-400 hover:text-zinc-200 text-xs font-mono uppercase px-3 py-2">
              <Plus className="w-3.5 h-3.5" /> Add Statement Line
            </button>
          </div>

          {showStmtForm && (
            <div className="bg-zinc-950 border border-zinc-800 p-5 space-y-3">
              <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2">New Bank Statement Line</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div>
                  <span className="label-overline block mb-1">Account Code</span>
                  <input value={stmtForm.bank_account_code} onChange={e => setStmtForm(f => ({ ...f, bank_account_code: e.target.value }))}
                    placeholder="e.g. 1002" className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">Date</span>
                  <input type="date" value={stmtForm.transaction_date} onChange={e => setStmtForm(f => ({ ...f, transaction_date: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">Reference</span>
                  <input value={stmtForm.ref_number} onChange={e => setStmtForm(f => ({ ...f, ref_number: e.target.value }))}
                    placeholder="UTR / Cheque No" className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div className="sm:col-span-2">
                  <span className="label-overline block mb-1">Description</span>
                  <input value={stmtForm.description} onChange={e => setStmtForm(f => ({ ...f, description: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="label-overline block mb-1">Debit ₹ (Out)</span>
                    <NumericInput value={stmtForm.debit} onChange={v => setStmtForm(f => ({ ...f, debit: v }))} placeholder="0.00" />
                  </div>
                  <div>
                    <span className="label-overline block mb-1">Credit ₹ (In)</span>
                    <NumericInput value={stmtForm.credit} onChange={v => setStmtForm(f => ({ ...f, credit: v }))} placeholder="0.00" />
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={createStmt} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Add Line</button>
                <button onClick={() => setShowStmtForm(false)} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
              </div>
            </div>
          )}

          {/* Reconciliation Report */}
          {reconReport && (
            <div className="bg-zinc-950 border border-zinc-800 p-5 space-y-4">
              <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2">Reconciliation Statement — as of {reconReport.as_of_date}</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Bank Balance", value: `₹${inr(reconReport.bank_balance)}`, color: "text-blue-300" },
                  { label: "Book Balance", value: `₹${inr(reconReport.book_balance)}`, color: "text-zinc-300" },
                  { label: "Difference", value: `₹${inr(Math.abs(reconReport.difference))}`, color: reconReport.difference === 0 ? "text-green-400" : "text-red-400" },
                  { label: "Unreconciled", value: reconReport.unreconciled_count, color: reconReport.unreconciled_count === 0 ? "text-green-400" : "text-yellow-400" },
                ].map(k => (
                  <div key={k.label} className="bg-zinc-900/50 border border-zinc-800 p-3">
                    <div className={`font-display font-black text-xl ${k.color}`}>{k.value}</div>
                    <div className="font-mono text-[10px] uppercase text-zinc-500 mt-1">{k.label}</div>
                  </div>
                ))}
              </div>
              {reconReport.is_reconciled ? (
                <div className="flex items-center gap-2 text-green-400 font-mono text-sm"><CheckCircle2 className="w-4 h-4" /> Account is fully reconciled</div>
              ) : (
                <div>
                  <div className="label-overline mb-2">Unreconciled Items</div>
                  <table className="w-full text-xs border border-zinc-800">
                    <thead><tr><th className="text-left px-3 py-2">Date</th><th className="text-left px-3 py-2">Description</th><th className="text-left px-3 py-2">Ref</th><th className="text-right px-3 py-2">Debit</th><th className="text-right px-3 py-2">Credit</th></tr></thead>
                    <tbody>
                      {(reconReport.unreconciled_items || []).map((item, i) => (
                        <tr key={i} className="border-b border-zinc-900 hover:bg-zinc-900">
                          <td className="px-3 py-2 font-mono text-zinc-400">{item.transaction_date}</td>
                          <td className="px-3 py-2 text-zinc-200">{item.description}</td>
                          <td className="px-3 py-2 font-mono text-zinc-500">{item.ref_number || "—"}</td>
                          <td className="px-3 py-2 text-right text-red-400">{item.debit > 0 ? `₹${inr(item.debit)}` : "—"}</td>
                          <td className="px-3 py-2 text-right text-green-400">{item.credit > 0 ? `₹${inr(item.credit)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Statement Lines List */}
          <div className="bg-zinc-950 border border-zinc-800">
            <div className="border-b border-zinc-800 px-5 py-3 font-mono text-[10px] uppercase tracking-widest text-zinc-400">Bank Statement Lines ({stmts.length})</div>
            <table className="w-full text-xs">
              <thead><tr><th className="text-left px-4 py-2">Date</th><th className="text-left px-4 py-2">Description</th><th className="text-left px-4 py-2">Ref</th><th className="text-right px-4 py-2">Debit</th><th className="text-right px-4 py-2">Credit</th><th className="text-left px-4 py-2">Reconciled</th></tr></thead>
              <tbody>
                {stmts.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">No statement lines entered yet</td></tr>}
                {stmts.map((s, i) => (
                  <tr key={s.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-zinc-400">{s.transaction_date}</td>
                    <td className="px-4 py-2 text-zinc-200">{s.description}</td>
                    <td className="px-4 py-2 font-mono text-zinc-500">{s.ref_number || "—"}</td>
                    <td className="px-4 py-2 text-right text-red-400">{s.debit > 0 ? `₹${inr(s.debit)}` : "—"}</td>
                    <td className="px-4 py-2 text-right text-green-400">{s.credit > 0 ? `₹${inr(s.credit)}` : "—"}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono ${s.is_reconciled ? "text-green-400" : "text-zinc-500"}`}>
                        {s.is_reconciled ? "✓ Matched" : "Pending"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cheque Register Tab */}
      {tab === "cheques" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <span className="font-mono text-xs text-zinc-500 uppercase">{cheques.length} Cheques</span>
            <button onClick={() => setShowChequeForm(!showChequeForm)}
              className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2">
              <Plus className="w-3.5 h-3.5" /> Log Cheque
            </button>
          </div>

          {showChequeForm && (
            <div className="bg-zinc-950 border border-zinc-800 p-5 space-y-3">
              <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2">Log Cheque</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: "Cheque Number", field: "cheque_number", type: "text" },
                  { label: "Bank Account Code", field: "bank_account_code", type: "text", placeholder: "e.g. 1002" },
                  { label: "Party Name", field: "party_name", type: "text" },
                  { label: "Amount ₹", field: "amount", type: "number" },
                  { label: "Cheque Date", field: "cheque_date", type: "date" },
                ].map(f => (
                  <div key={f.field}>
                    <span className="label-overline block mb-1">{f.label}</span>
                    <input type={f.type} value={chequeForm[f.field] || ""}
                      onChange={e => setChequeForm(cf => ({ ...cf, [f.field]: e.target.value }))}
                      placeholder={f.placeholder || ""}
                      className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                  </div>
                ))}
                <div>
                  <span className="label-overline block mb-1">Type</span>
                  <select value={chequeForm.cheque_type} onChange={e => setChequeForm(cf => ({ ...cf, cheque_type: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                    <option value="ISSUED">Issued (Payment)</option>
                    <option value="RECEIVED">Received (Receipt)</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={createCheque} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Log</button>
                <button onClick={() => setShowChequeForm(false)} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
              </div>
            </div>
          )}

          <div className="bg-zinc-950 border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr>
                <th className="text-left px-4 py-2">Cheque No</th>
                <th className="text-left px-4 py-2">Party</th>
                <th className="text-left px-4 py-2">Type</th>
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-right px-4 py-2">Amount</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Actions</th>
              </tr></thead>
              <tbody>
                {cheques.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">No cheques logged yet</td></tr>}
                {cheques.map((ch, i) => (
                  <tr key={ch.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-yellow-400">{ch.cheque_number}</td>
                    <td className="px-4 py-2 text-zinc-200">{ch.party_name}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        ch.cheque_type === "ISSUED" ? "bg-red-950" : "bg-green-950"
                      }`}>{ch.cheque_type}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-zinc-400">{ch.cheque_date}</td>
                    <td className="px-4 py-2 text-right font-semibold text-zinc-200">₹{inr(ch.amount)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        ch.status === "CLEARED" ? "bg-green-950" :
                        ch.status === "BOUNCED" ? "bg-red-950" :
                        ch.status === "CANCELLED" ? "border-zinc-700 text-zinc-500" :
                        "bg-yellow-950"
                      }`}>{ch.status}</span>
                    </td>
                    <td className="px-4 py-2">
                      {ch.status === "PENDING" && (
                        <div className="flex gap-1">
                          <button onClick={() => updateChequeStatus(ch.id, "CLEARED")}
                            className="text-[9px] font-mono uppercase px-1.5 py-0.5 border border-green-200 text-green-700 bg-green-50 hover:bg-green-100 dark:border-green-800 dark:text-green-400 dark:bg-green-950/20 dark:hover:bg-green-950/40">
                            Clear
                          </button>
                          <button onClick={() => updateChequeStatus(ch.id, "BOUNCED")}
                            className="text-[9px] font-mono uppercase px-1.5 py-0.5 border border-red-200 text-red-700 bg-red-50 hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:bg-red-950/20 dark:hover:bg-red-950/40">
                            Bounce
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal open={showBankModal} onClose={() => setShowBankModal(false)} title="Add Bank Account">
        <form ref={bankFormRef} onSubmit={createBankAccount} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Account Label" required><Input value={bankForm.name} onChange={e => setBankForm(f => ({ ...f, name: e.target.value }))} placeholder="Primary Current Account" required /></Field>
            <Field label="Bank Name" required><Input value={bankForm.bank_name} onChange={e => setBankForm(f => ({ ...f, bank_name: e.target.value }))} placeholder="HDFC Bank" required /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Account Number" required><Input value={bankForm.account_number} onChange={e => setBankForm(f => ({ ...f, account_number: e.target.value }))} required /></Field>
            <Field label="IFSC Code"><Input value={bankForm.ifsc} onChange={e => setBankForm(f => ({ ...f, ifsc: e.target.value }))} placeholder="HDFC0001234" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Account Type">
              <Select value={bankForm.account_type} onChange={e => setBankForm(f => ({ ...f, account_type: e.target.value }))}>
                {["CURRENT","SAVINGS","OD","CC"].map(t => <option key={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Opening Balance (₹)"><NumericInput value={bankForm.opening_balance} onChange={v => setBankForm(f => ({ ...f, opening_balance: v }))} placeholder="0.00" align="left" /></Field>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowBankModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Create</PrimaryButton>
          </div>
        </form>
      </Modal>

      {/* Add Bank Entry Modal */}
      <Modal open={showEntryModal} onClose={() => setShowEntryModal(false)} title="Record Bank Entry">
        <form ref={entryFormRef} onSubmit={createBankEntry} className="space-y-4">
          <Field label="Bank Account" required>
            <Select value={entryForm.bank_account_id} onChange={e => setEntryForm(f => ({ ...f, bank_account_id: e.target.value }))} required>
              <option value="">Select account...</option>
              {bankAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Date" required><Input type="date" value={entryForm.date} onChange={e => setEntryForm(f => ({ ...f, date: e.target.value }))} required /></Field>
            <Field label="Entry Type">
              <Select value={entryForm.entry_type} onChange={e => setEntryForm(f => ({ ...f, entry_type: e.target.value }))}>
                <option value="CREDIT">CREDIT (Money In)</option>
                <option value="DEBIT">DEBIT (Money Out)</option>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Amount (₹)" required><NumericInput value={entryForm.amount} onChange={v => setEntryForm(f => ({ ...f, amount: v }))} placeholder="0.00" align="left" /></Field>
            <Field label="Reference No"><Input value={entryForm.reference} onChange={e => setEntryForm(f => ({ ...f, reference: e.target.value }))} placeholder="Cheque / UTR number" /></Field>
          </div>
          <Field label="Description"><Input value={entryForm.description} onChange={e => setEntryForm(f => ({ ...f, description: e.target.value }))} /></Field>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowEntryModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Record</PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
