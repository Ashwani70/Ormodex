import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  StatusBadge,
  PrimaryButton,
  SecondaryButton,
  Input,
  Select,
  Field,
  EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import {
  BookOpen,
  Plus,
  ChevronRight,
  CheckCircle,
  Scale,
  RefreshCw,
  TrendingUp,
  DollarSign,
  FileText,
  Landmark,
} from "lucide-react";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const TABS = [
  { id: "coa", label: "Chart of Accounts" },
  { id: "journal", label: "Journal Entries" },
  { id: "trial", label: "Trial Balance" },
  { id: "pl", label: "P&L Statement" },
  { id: "bs", label: "Balance Sheet" },
  { id: "daybook", label: "Day Book" },
  { id: "cashflow", label: "Cash Flow" },
  { id: "interest", label: "Interest Outstanding" },
];

const ACCOUNT_TYPES = ["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"];

export default function Accounting() {
  const [tab, setTab] = useState("coa");
  const [accounts, setAccounts] = useState([]);
  const [journalEntries, setJournalEntries] = useState([]);
  const [trialBalance, setTrialBalance] = useState(null);
  const [pl, setPl] = useState(null);
  const [bs, setBs] = useState(null);
  const [dayBook, setDayBook] = useState(null);
  const [cashFlow, setCashFlow] = useState(null);
  const [interest, setInterest] = useState(null);
  const [interestRate, setInterestRate] = useState(18.0);
  const [loading, setLoading] = useState(false);
  const [showCoaModal, setShowCoaModal] = useState(false);
  const [showJeModal, setShowJeModal] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  // COA form
  const [coaForm, setCoaForm] = useState({ code: "", name: "", account_type: "ASSET", opening_balance: 0, currency: "INR" });
  // JE form
  const [jeForm, setJeForm] = useState({ date: new Date().toISOString().split("T")[0], narration: "", lines: [{ account_code: "", account_name: "", debit: 0, credit: 0 }] });

  const loadAccounts = useCallback(async () => {
    const r = await api.get("/accounting/chart-of-accounts");
    setAccounts(r.data);
  }, []);

  const loadJournalEntries = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/journal-entries", { params });
      setJournalEntries(r.data.items || []);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadTrialBalance = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/trial-balance", { params });
      setTrialBalance(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadPL = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/profit-loss", { params });
      setPl(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadBS = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (toDate) params.as_of_date = toDate;
      const r = await api.get("/accounting/balance-sheet", { params });
      setBs(r.data);
    } finally { setLoading(false); }
  }, [toDate]);

  const loadDayBook = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/day-book", { params });
      setDayBook(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadCashFlow = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/cash-flow", { params });
      setCashFlow(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadInterest = useCallback(async () => {
    setLoading(true);
    try {
      const params = { annual_rate: interestRate };
      if (toDate) params.as_of_date = toDate;
      const r = await api.get("/accounting/interest-on-outstanding", { params });
      setInterest(r.data);
    } finally { setLoading(false); }
  }, [interestRate, toDate]);

  useEffect(() => {
    if (tab === "coa") loadAccounts();
    if (tab === "journal") loadJournalEntries();
    if (tab === "trial") loadTrialBalance();
    if (tab === "pl") loadPL();
    if (tab === "bs") loadBS();
    if (tab === "daybook") loadDayBook();
    if (tab === "cashflow") loadCashFlow();
    if (tab === "interest") loadInterest();
  }, [tab, loadAccounts, loadJournalEntries, loadTrialBalance, loadPL, loadBS, loadDayBook, loadCashFlow, loadInterest]);

  const seedCoa = async () => {
    try {
      const r = await api.post("/accounting/seed-coa");
      toast.success(r.data.message);
      loadAccounts();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to seed CoA");
    }
  };

  const createAccount = async (e) => {
    e.preventDefault();
    try {
      await api.post("/accounting/chart-of-accounts", { ...coaForm, opening_balance: parseFloat(coaForm.opening_balance), is_active: true, tags: [] });
      toast.success("Account created");
      setShowCoaModal(false);
      setCoaForm({ code: "", name: "", account_type: "ASSET", opening_balance: 0, currency: "INR" });
      loadAccounts();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const addJeLine = () => setJeForm(f => ({ ...f, lines: [...f.lines, { account_code: "", account_name: "", debit: 0, credit: 0 }] }));
  const removeJeLine = (i) => setJeForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));
  const updateJeLine = (i, key, val) => setJeForm(f => {
    const lines = [...f.lines];
    lines[i] = { ...lines[i], [key]: key === "debit" || key === "credit" ? parseFloat(val) || 0 : val };
    return { ...f, lines };
  });

  const createJe = async (e) => {
    e.preventDefault();
    try {
      await api.post("/accounting/journal-entries", { ...jeForm, status: "DRAFT" });
      toast.success("Journal entry created");
      setShowJeModal(false);
      setJeForm({ date: new Date().toISOString().split("T")[0], narration: "", lines: [{ account_code: "", account_name: "", debit: 0, credit: 0 }] });
      loadJournalEntries();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const totalDebit = jeForm.lines.reduce((s, l) => s + (l.debit || 0), 0);
  const totalCredit = jeForm.lines.reduce((s, l) => s + (l.credit || 0), 0);

  const accountsByType = ACCOUNT_TYPES.reduce((acc, t) => {
    acc[t] = accounts.filter(a => a.account_type === t);
    return acc;
  }, {});

  const typeColors = {
    ASSET: "text-blue-400 border-blue-900 bg-blue-950",
    LIABILITY: "text-red-400 border-red-900 bg-red-950",
    EQUITY: "text-purple-400 border-purple-900 bg-purple-950",
    INCOME: "text-green-400 border-green-900 bg-green-950",
    EXPENSE: "text-yellow-400 border-yellow-900 bg-yellow-950",
  };

  return (
    <div data-testid="accounting-page">
      <PageHeader
        eyebrow="Finance"
        title="Accounting"
        description="Double-entry bookkeeping, journal entries, financial statements."
        actions={
          <>
            {tab === "coa" && (
              <>
                <SecondaryButton icon={RefreshCw} onClick={seedCoa} testid="seed-coa-btn">
                  Seed Default CoA
                </SecondaryButton>
                <PrimaryButton icon={Plus} onClick={() => setShowCoaModal(true)} testid="add-account-btn">
                  Add Account
                </PrimaryButton>
              </>
            )}
            {tab === "journal" && (
              <PrimaryButton icon={Plus} onClick={() => setShowJeModal(true)} testid="add-je-btn">
                New Journal Entry
              </PrimaryButton>
            )}
          </>
        }
      />

      {/* Date filter bar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="label-overline">From</span>
          <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex items-center gap-2">
          <span className="label-overline">To</span>
          <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
        </div>
        <SecondaryButton icon={RefreshCw} onClick={() => {
          if (tab === "journal") loadJournalEntries();
          if (tab === "trial") loadTrialBalance();
          if (tab === "pl") loadPL();
          if (tab === "bs") loadBS();
          if (tab === "daybook") loadDayBook();
          if (tab === "cashflow") loadCashFlow();
          if (tab === "interest") loadInterest();
        }}>Apply</SecondaryButton>
      </div>

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id
                ? "bg-yellow-400 text-black font-bold"
                : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* COA Tab */}
      {tab === "coa" && (
        <div className="space-y-6">
          {ACCOUNT_TYPES.map(type => (
            <div key={type}>
              <SectionTitle>
                <span className={`text-xs font-mono px-2 py-0.5 border ${typeColors[type]}`}>{type}</span>
                <span className="ml-2 text-zinc-400 text-sm">({accountsByType[type].length})</span>
              </SectionTitle>
              {accountsByType[type].length > 0 ? (
                <table className="w-full text-sm border border-zinc-800">
                  <thead>
                    <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                      <th className="text-left px-4 py-2">Code</th>
                      <th className="text-left px-4 py-2">Account Name</th>
                      <th className="text-right px-4 py-2">Opening Balance</th>
                      <th className="text-left px-4 py-2">Currency</th>
                      <th className="text-left px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accountsByType[type].map((a, i) => (
                      <tr key={a.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                        <td className="px-4 py-2 font-mono text-yellow-400">{a.code}</td>
                        <td className="px-4 py-2 text-white">{a.name}</td>
                        <td className="px-4 py-2 text-right tabular text-zinc-300">₹{inr(a.opening_balance)}</td>
                        <td className="px-4 py-2 font-mono text-zinc-400">{a.currency}</td>
                        <td className="px-4 py-2">
                          <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${a.is_active ? "border-green-900 bg-green-950 text-green-400" : "border-zinc-700 bg-zinc-800 text-zinc-500"}`}>
                            {a.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-xs text-zinc-600 font-mono uppercase border border-dashed border-zinc-800 px-4 py-3">
                  No {type.toLowerCase()} accounts
                </div>
              )}
            </div>
          ))}
          {accounts.length === 0 && (
            <EmptyState
              message="No Chart of Accounts found"
              action={<SecondaryButton onClick={seedCoa}>Seed Default Chart of Accounts</SecondaryButton>}
            />
          )}
        </div>
      )}

      {/* Journal Entries Tab */}
      {tab === "journal" && (
        <div>
          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : journalEntries.length === 0 ? (
            <EmptyState message="No journal entries" action={<PrimaryButton icon={Plus} onClick={() => setShowJeModal(true)}>Create Entry</PrimaryButton>} />
          ) : (
            <table className="w-full text-sm border border-zinc-800">
              <thead>
                <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                  <th className="text-left px-4 py-2">Entry No</th>
                  <th className="text-left px-4 py-2">Date</th>
                  <th className="text-left px-4 py-2">Narration</th>
                  <th className="text-right px-4 py-2">Debit</th>
                  <th className="text-right px-4 py-2">Credit</th>
                  <th className="text-left px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {journalEntries.map((je, i) => (
                  <tr key={je.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{je.entry_number}</td>
                    <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{je.date}</td>
                    <td className="px-4 py-2 text-white max-w-xs truncate">{je.narration}</td>
                    <td className="px-4 py-2 text-right tabular text-zinc-300">₹{inr(je.total_debit)}</td>
                    <td className="px-4 py-2 text-right tabular text-zinc-300">₹{inr(je.total_credit)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${
                        je.status === "POSTED" ? "border-green-900 bg-green-950 text-green-400" :
                        je.status === "DRAFT" ? "border-zinc-700 bg-zinc-800 text-zinc-400" :
                        "border-yellow-700 bg-yellow-950 text-yellow-400"
                      }`}>{je.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Trial Balance Tab */}
      {tab === "trial" && (
        <div>
          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : trialBalance ? (
            <>
              <div className="grid grid-cols-3 gap-3 mb-6">
                <StatTile label="Total Debit" value={`₹${inr(trialBalance.total_debit)}`} />
                <StatTile label="Total Credit" value={`₹${inr(trialBalance.total_credit)}`} />
                <StatTile label="Balanced" value={trialBalance.is_balanced ? "✓ YES" : "✗ NO"} accent={trialBalance.is_balanced} />
              </div>
              <table className="w-full text-sm border border-zinc-800">
                <thead>
                  <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                    <th className="text-left px-4 py-2">Account Code</th>
                    <th className="text-left px-4 py-2">Account Name</th>
                    <th className="text-right px-4 py-2">Debit (₹)</th>
                    <th className="text-right px-4 py-2">Credit (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {trialBalance.rows.map((r, i) => (
                    <tr key={r.account_code} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                      <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{r.account_code}</td>
                      <td className="px-4 py-2 text-white">{r.account_name}</td>
                      <td className="px-4 py-2 text-right tabular">{r.debit ? `₹${inr(r.debit)}` : "—"}</td>
                      <td className="px-4 py-2 text-right tabular">{r.credit ? `₹${inr(r.credit)}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="border-t-2 border-zinc-700 bg-zinc-900">
                  <tr>
                    <td colSpan={2} className="px-4 py-3 font-bold text-white uppercase tracking-wider text-xs">TOTAL</td>
                    <td className="px-4 py-3 text-right tabular font-bold text-yellow-400">₹{inr(trialBalance.total_debit)}</td>
                    <td className="px-4 py-3 text-right tabular font-bold text-yellow-400">₹{inr(trialBalance.total_credit)}</td>
                  </tr>
                </tfoot>
              </table>
            </>
          ) : (
            <EmptyState message="No trial balance data" />
          )}
        </div>
      )}

      {/* P&L Tab */}
      {tab === "pl" && pl && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <SectionTitle>Income</SectionTitle>
            <table className="w-full text-sm border border-zinc-800">
              <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900"><th className="text-left px-4 py-2">Account</th><th className="text-right px-4 py-2">Amount</th></tr></thead>
              <tbody>
                {(pl.income || []).map(r => (
                  <tr key={r.code} className="border-b border-zinc-900 hover:bg-zinc-900">
                    <td className="px-4 py-2 text-white">{r.name} <span className="text-zinc-500 font-mono text-xs">{r.code}</span></td>
                    <td className="px-4 py-2 text-right tabular text-green-400">₹{inr(r.amount)}</td>
                  </tr>
                ))}
                <tr className="border-t border-zinc-700 bg-zinc-900">
                  <td className="px-4 py-3 font-bold text-white">Total Income</td>
                  <td className="px-4 py-3 text-right tabular font-bold text-green-400">₹{inr(pl.total_income)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <SectionTitle>Expenses</SectionTitle>
            <table className="w-full text-sm border border-zinc-800">
              <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900"><th className="text-left px-4 py-2">Account</th><th className="text-right px-4 py-2">Amount</th></tr></thead>
              <tbody>
                {(pl.expense || []).map(r => (
                  <tr key={r.code} className="border-b border-zinc-900 hover:bg-zinc-900">
                    <td className="px-4 py-2 text-white">{r.name} <span className="text-zinc-500 font-mono text-xs">{r.code}</span></td>
                    <td className="px-4 py-2 text-right tabular text-red-400">₹{inr(r.amount)}</td>
                  </tr>
                ))}
                <tr className="border-t border-zinc-700 bg-zinc-900">
                  <td className="px-4 py-3 font-bold text-white">Total Expenses</td>
                  <td className="px-4 py-3 text-right tabular font-bold text-red-400">₹{inr(pl.total_expense)}</td>
                </tr>
              </tbody>
            </table>
            <div className={`mt-4 border p-4 flex items-center justify-between ${pl.net_profit >= 0 ? "border-green-700 bg-green-950" : "border-red-700 bg-red-950"}`}>
              <span className="font-display font-bold text-white uppercase tracking-wider">Net {pl.net_profit >= 0 ? "Profit" : "Loss"}</span>
              <span className={`font-display font-black text-2xl tabular ${pl.net_profit >= 0 ? "text-green-400" : "text-red-400"}`}>₹{inr(Math.abs(pl.net_profit))}</span>
            </div>
          </div>
        </div>
      )}

      {/* Balance Sheet Tab */}
      {tab === "bs" && bs && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div>
            <SectionTitle>Assets</SectionTitle>
            <table className="w-full text-sm border border-zinc-800">
              <tbody>
                {(bs.assets || []).map(r => (
                  <tr key={r.code} className="border-b border-zinc-900 hover:bg-zinc-900">
                    <td className="px-4 py-2 text-white text-xs">{r.name}</td>
                    <td className="px-4 py-2 text-right tabular text-blue-400">₹{inr(r.balance)}</td>
                  </tr>
                ))}
                <tr className="border-t border-zinc-700 bg-zinc-900 font-bold">
                  <td className="px-4 py-3 text-white">Total Assets</td>
                  <td className="px-4 py-3 text-right tabular text-yellow-400">₹{inr(bs.total_assets)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <SectionTitle>Liabilities</SectionTitle>
            <table className="w-full text-sm border border-zinc-800">
              <tbody>
                {(bs.liabilities || []).map(r => (
                  <tr key={r.code} className="border-b border-zinc-900 hover:bg-zinc-900">
                    <td className="px-4 py-2 text-white text-xs">{r.name}</td>
                    <td className="px-4 py-2 text-right tabular text-red-400">₹{inr(r.balance)}</td>
                  </tr>
                ))}
                <tr className="border-t border-zinc-700 bg-zinc-900 font-bold">
                  <td className="px-4 py-3 text-white">Total Liabilities</td>
                  <td className="px-4 py-3 text-right tabular text-yellow-400">₹{inr(bs.total_liabilities)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <SectionTitle>Equity</SectionTitle>
            <table className="w-full text-sm border border-zinc-800">
              <tbody>
                {(bs.equity || []).map(r => (
                  <tr key={r.code} className="border-b border-zinc-900 hover:bg-zinc-900">
                    <td className="px-4 py-2 text-white text-xs">{r.name}</td>
                    <td className="px-4 py-2 text-right tabular text-purple-400">₹{inr(r.balance)}</td>
                  </tr>
                ))}
                <tr className="border-t border-zinc-700 bg-zinc-900 font-bold">
                  <td className="px-4 py-3 text-white">Total Equity</td>
                  <td className="px-4 py-3 text-right tabular text-yellow-400">₹{inr(bs.total_equity)}</td>
                </tr>
              </tbody>
            </table>
            <div className="mt-4 border border-yellow-700 bg-yellow-950/30 p-3 flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider text-zinc-400">As of {bs.as_of_date}</span>
            </div>
          </div>
        </div>
      )}

      {/* Day Book Tab */}
      {tab === "daybook" && (
        <div className="space-y-6">
          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : dayBook ? (
            <>
              <div className="flex gap-3 mb-4">
                <StatTile label="Journal Entries" value={dayBook.journal_entries?.length || 0} />
                <StatTile label="Vouchers" value={dayBook.vouchers?.length || 0} />
                <StatTile label="Total Records" value={dayBook.total_entries || 0} accent />
              </div>
              {(dayBook.journal_entries?.length > 0) && (
                <div>
                  <SectionTitle>Journal Entries</SectionTitle>
                  <table className="w-full text-sm border border-zinc-800">
                    <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                      <th className="text-left px-4 py-2">Entry No</th>
                      <th className="text-left px-4 py-2">Narration</th>
                      <th className="text-right px-4 py-2">Debit</th>
                      <th className="text-right px-4 py-2">Credit</th>
                    </tr></thead>
                    <tbody>
                      {dayBook.journal_entries.map(je => (
                        <tr key={je.id} className="border-b border-zinc-900 hover:bg-zinc-900">
                          <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{je.entry_number}</td>
                          <td className="px-4 py-2 text-white text-xs">{je.narration}</td>
                          <td className="px-4 py-2 text-right tabular">₹{inr(je.total_debit)}</td>
                          <td className="px-4 py-2 text-right tabular">₹{inr(je.total_credit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <EmptyState message="No day book data" />
          )}
        </div>
      )}

      {/* Cash Flow Tab */}
      {tab === "cashflow" && (
        <div className="space-y-6">
          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : cashFlow ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <StatTile label="Operating Cash Flow" value={`₹${inr(cashFlow.operating_activities?.net_operating_cash_flow)}`} accent={cashFlow.operating_activities?.net_operating_cash_flow >= 0} />
                <StatTile label="Investing Cash Flow" value={`₹${inr(cashFlow.investing_activities?.net_investing_cash_flow)}`} />
                <StatTile label="Financing Cash Flow" value={`₹${inr(cashFlow.financing_activities?.net_financing_cash_flow)}`} />
                <StatTile label="Net Cash Change" value={`₹${inr(cashFlow.net_cash_change)}`} accent={cashFlow.net_cash_change >= 0} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Operating Activities */}
                <div className="bg-zinc-950 border border-zinc-800 p-4 space-y-4">
                  <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2 font-bold">1. Operating Activities</div>
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-zinc-400">Net Profit Before Tax</span>
                      <span className={`font-mono ${cashFlow.operating_activities?.net_profit >= 0 ? "text-green-400" : "text-red-400"}`}>₹{inr(cashFlow.operating_activities?.net_profit)}</span>
                    </div>
                    {cashFlow.operating_activities?.working_capital_adjustments?.map((w, idx) => (
                      <div key={idx} className="flex justify-between text-xs border-b border-zinc-900 pb-1">
                        <span className="text-zinc-500">{w.label}</span>
                        <span className={`font-mono ${w.amount >= 0 ? "text-green-500" : "text-red-500"}`}>
                          {w.amount >= 0 ? "+" : ""}₹{inr(w.amount)}
                        </span>
                      </div>
                    ))}
                    <div className="flex justify-between text-xs pt-2 border-t border-zinc-800 font-bold">
                      <span className="text-zinc-300">Working Capital Net</span>
                      <span className="text-zinc-200">₹{inr(cashFlow.operating_activities?.working_capital_net)}</span>
                    </div>
                    <div className="flex justify-between text-xs pt-2 border-t border-zinc-700 font-bold text-yellow-400">
                      <span>Net Cash from Operating</span>
                      <span>₹{inr(cashFlow.operating_activities?.net_operating_cash_flow)}</span>
                    </div>
                  </div>
                </div>

                {/* Investing Activities */}
                <div className="bg-zinc-950 border border-zinc-800 p-4 space-y-4">
                  <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2 font-bold">2. Investing Activities</div>
                  <div className="space-y-2">
                    {cashFlow.investing_activities?.items?.length === 0 ? (
                      <div className="text-xs text-zinc-600 font-mono italic">No investing activity logs</div>
                    ) : (
                      cashFlow.investing_activities?.items?.map((item, idx) => (
                        <div key={idx} className="flex justify-between text-xs border-b border-zinc-900 pb-1">
                          <span className="text-zinc-500">{item.label}</span>
                          <span className={`font-mono ${item.amount >= 0 ? "text-green-500" : "text-red-500"}`}>
                            {item.amount >= 0 ? "+" : ""}₹{inr(item.amount)}
                          </span>
                        </div>
                      ))
                    )}
                    <div className="flex justify-between text-xs pt-2 border-t border-zinc-700 font-bold text-yellow-400">
                      <span>Net Cash from Investing</span>
                      <span>₹{inr(cashFlow.investing_activities?.net_investing_cash_flow)}</span>
                    </div>
                  </div>
                </div>

                {/* Financing Activities */}
                <div className="bg-zinc-950 border border-zinc-800 p-4 space-y-4">
                  <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2 font-bold">3. Financing Activities</div>
                  <div className="space-y-2">
                    {cashFlow.financing_activities?.items?.length === 0 ? (
                      <div className="text-xs text-zinc-600 font-mono italic">No financing activity logs</div>
                    ) : (
                      cashFlow.financing_activities?.items?.map((item, idx) => (
                        <div key={idx} className="flex justify-between text-xs border-b border-zinc-900 pb-1">
                          <span className="text-zinc-500">{item.label}</span>
                          <span className={`font-mono ${item.amount >= 0 ? "text-green-500" : "text-red-500"}`}>
                            {item.amount >= 0 ? "+" : ""}₹{inr(item.amount)}
                          </span>
                        </div>
                      ))
                    )}
                    <div className="flex justify-between text-xs pt-2 border-t border-zinc-700 font-bold text-yellow-400">
                      <span>Net Cash from Financing</span>
                      <span>₹{inr(cashFlow.financing_activities?.net_financing_cash_flow)}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="border border-zinc-800 bg-zinc-900/50 p-4 flex justify-between items-center">
                <div>
                  <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">Net Increase/Decrease in Cash</div>
                  <div className="text-xs text-zinc-600 font-mono">Indirect Method formula: Net Operating + Investing + Financing Cash Flow.</div>
                </div>
                <div className={`font-display font-black text-2xl tabular ${cashFlow.net_cash_change >= 0 ? "text-green-400" : "text-red-400"}`}>
                  ₹{inr(cashFlow.net_cash_change)}
                </div>
              </div>
            </div>
          ) : (
            <EmptyState message="No cash flow data available for the period" />
          )}
        </div>
      )}

      {/* Interest Outstanding Tab */}
      {tab === "interest" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-4 bg-zinc-950 border border-zinc-850 p-4">
            <div className="w-44">
              <span className="label-overline block mb-1">Interest Rate % (Annual)</span>
              <Input type="number" step="0.5" value={interestRate} onChange={e => setInterestRate(parseFloat(e.target.value) || 0)} className="!h-9" />
            </div>
            <SecondaryButton icon={RefreshCw} onClick={loadInterest} className="h-9">Recalculate</SecondaryButton>
          </div>

          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : interest ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <StatTile label="Total Outstanding" value={`₹${inr(interest.total_outstanding)}`} />
                <StatTile label="Accrued Interest" value={`₹${inr(interest.total_interest)}`} accent />
                <StatTile label="Total Due with Interest" value={`₹${inr(interest.total_due_with_interest)}`} />
              </div>

              <div className="bg-zinc-950 border border-zinc-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="label-overline border-b border-zinc-800 bg-zinc-900 text-zinc-400">
                      <th className="text-left px-4 py-2">Invoice No</th>
                      <th className="text-left px-4 py-2">Customer</th>
                      <th className="text-left px-4 py-2">Inv Date</th>
                      <th className="text-right px-4 py-2">Outstanding</th>
                      <th className="text-right px-4 py-2">Days Overdue</th>
                      <th className="text-right px-4 py-2">Rate % (p.a.)</th>
                      <th className="text-right px-4 py-2">Interest</th>
                      <th className="text-right px-4 py-2">Total Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {interest.invoices?.length === 0 && (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-zinc-600 font-mono">No unpaid invoices to calculate interest.</td>
                      </tr>
                    )}
                    {interest.invoices?.map((inv, i) => (
                      <tr key={inv.invoice_number} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                        <td className="px-4 py-2 font-mono text-yellow-400">{inv.invoice_number}</td>
                        <td className="px-4 py-2 text-white font-bold">{inv.customer_name}</td>
                        <td className="px-4 py-2 text-zinc-400 font-mono">{inv.invoice_date}</td>
                        <td className="px-4 py-2 text-right tabular">₹{inr(inv.amount_outstanding)}</td>
                        <td className="px-4 py-2 text-right tabular text-red-400 font-semibold">{inv.days_overdue} days</td>
                        <td className="px-4 py-2 text-right tabular text-zinc-500">{inv.interest_rate_pa}%</td>
                        <td className="px-4 py-2 text-right tabular text-yellow-500 font-bold">₹{inr(inv.interest_amount)}</td>
                        <td className="px-4 py-2 text-right tabular text-green-400 font-bold">₹{inr(inv.total_due_with_interest)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <EmptyState message="No interest report available" />
          )}
        </div>
      )}

      {/* COA Modal */}
      <Modal open={showCoaModal} onClose={() => setShowCoaModal(false)} title="Add Account">
        <form onSubmit={createAccount} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Account Code" required><Input value={coaForm.code} onChange={e => setCoaForm(f => ({ ...f, code: e.target.value }))} placeholder="e.g. 1001" required /></Field>
            <Field label="Account Type" required>
              <Select value={coaForm.account_type} onChange={e => setCoaForm(f => ({ ...f, account_type: e.target.value }))}>
                {ACCOUNT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Account Name" required><Input value={coaForm.name} onChange={e => setCoaForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Bank Account - Primary" required /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Opening Balance"><Input type="number" step="0.01" value={coaForm.opening_balance} onChange={e => setCoaForm(f => ({ ...f, opening_balance: e.target.value }))} /></Field>
            <Field label="Currency"><Select value={coaForm.currency} onChange={e => setCoaForm(f => ({ ...f, currency: e.target.value }))}><option>INR</option><option>USD</option><option>EUR</option></Select></Field>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowCoaModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Create Account</PrimaryButton>
          </div>
        </form>
      </Modal>

      {/* Journal Entry Modal */}
      <Modal open={showJeModal} onClose={() => setShowJeModal(false)} title="New Journal Entry">
        <form onSubmit={createJe} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Date" required><Input type="date" value={jeForm.date} onChange={e => setJeForm(f => ({ ...f, date: e.target.value }))} required /></Field>
          </div>
          <Field label="Narration" required><Input value={jeForm.narration} onChange={e => setJeForm(f => ({ ...f, narration: e.target.value }))} placeholder="Description of the entry" required /></Field>
          
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="label-overline">Lines</span>
              <SecondaryButton icon={Plus} onClick={addJeLine}>Add Line</SecondaryButton>
            </div>
            <table className="w-full text-xs">
              <thead><tr className="label-overline border-b border-zinc-800"><th className="text-left py-1">Account Code</th><th className="text-left py-1">Account Name</th><th className="text-right py-1">Debit</th><th className="text-right py-1">Credit</th><th></th></tr></thead>
              <tbody>
                {jeForm.lines.map((line, i) => (
                  <tr key={i} className="border-b border-zinc-900">
                    <td className="py-1 pr-2"><Input value={line.account_code} onChange={e => updateJeLine(i, "account_code", e.target.value)} placeholder="1001" className="!text-xs" /></td>
                    <td className="py-1 pr-2"><Input value={line.account_name} onChange={e => updateJeLine(i, "account_name", e.target.value)} placeholder="Cash in Hand" className="!text-xs" /></td>
                    <td className="py-1 pr-2"><Input type="number" step="0.01" value={line.debit} onChange={e => updateJeLine(i, "debit", e.target.value)} className="!text-xs text-right" /></td>
                    <td className="py-1 pr-2"><Input type="number" step="0.01" value={line.credit} onChange={e => updateJeLine(i, "credit", e.target.value)} className="!text-xs text-right" /></td>
                    <td className="py-1"><button type="button" onClick={() => removeJeLine(i)} className="text-red-500 hover:text-red-300 text-xs">✕</button></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className={`border-t ${Math.abs(totalDebit - totalCredit) < 0.01 ? "text-green-400" : "text-red-400"}`}>
                  <td colSpan={2} className="py-2 text-xs font-mono uppercase">
                    {Math.abs(totalDebit - totalCredit) < 0.01 ? "✓ Balanced" : "✗ Not balanced"}
                  </td>
                  <td className="py-2 text-right tabular font-bold">₹{inr(totalDebit)}</td>
                  <td className="py-2 text-right tabular font-bold">₹{inr(totalCredit)}</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowJeModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit" disabled={Math.abs(totalDebit - totalCredit) > 0.01}>
              Create Entry
            </PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
