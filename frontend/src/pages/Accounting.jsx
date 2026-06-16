import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
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

function Pagination({ currentPage, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex justify-between items-center mt-4 pt-4 border-t border-zinc-800 font-mono text-xs">
      <span className="text-zinc-500">
        Page {currentPage} of {totalPages}
      </span>
      <div className="flex gap-2">
        <SecondaryButton
          disabled={currentPage === 1}
          onClick={() => onPageChange(currentPage - 1)}
          className="h-8 !px-3"
        >
          Previous
        </SecondaryButton>
        <SecondaryButton
          disabled={currentPage === totalPages}
          onClick={() => onPageChange(currentPage + 1)}
          className="h-8 !px-3"
        >
          Next
        </SecondaryButton>
      </div>
    </div>
  );
}

export default function Accounting() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") || "coa";
  
  const [fromDate, setFromDate] = useState(searchParams.get("from") || "");
  const [toDate, setToDate] = useState(searchParams.get("to") || "");
  
  const setTab = (newTab) => {
    const params = { tab: newTab };
    if (fromDate) params.from = fromDate;
    if (toDate) params.to = toDate;
    setSearchParams(params);
  };

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
  const [page, setPage] = useState(1);

  // Sync state with URL search params (e.g. back button / history navigation)
  useEffect(() => {
    const urlFrom = searchParams.get("from") || "";
    const urlTo = searchParams.get("to") || "";
    if (urlFrom !== fromDate) setFromDate(urlFrom);
    if (urlTo !== toDate) setToDate(urlTo);
  }, [searchParams]);

  useEffect(() => {
    setPage(1);
  }, [tab, fromDate, toDate]);

  // COA form
  const [coaForm, setCoaForm] = useState({ code: "", name: "", account_type: "ASSET", opening_balance: 0, currency: "INR" });
  // JE form
  const [jeForm, setJeForm] = useState({ date: new Date().toISOString().split("T")[0], narration: "", lines: [{ account_code: "", account_name: "", debit: 0, credit: 0 }] });

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/accounting/chart-of-accounts");
      setAccounts(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Chart of Accounts");
    } finally { setLoading(false); }
  }, []);

  const loadJournalEntries = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/accounting/journal-entries", { params });
      setJournalEntries(r.data.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Journal Entries");
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
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Trial Balance");
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
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Profit & Loss Statement");
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadBS = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (toDate) params.as_of_date = toDate;
      const r = await api.get("/accounting/balance-sheet", { params });
      setBs(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Balance Sheet");
    } finally { setLoading(false); }
  }, [toDate]);

  const loadDayBook = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from = fromDate;
      if (toDate) params.to = toDate;
      const r = await api.get("/accounting/day-book", { params });
      setDayBook(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Day Book data");
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadCashFlow = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from = fromDate;
      if (toDate) params.to = toDate;
      const r = await api.get("/accounting/cash-flow", { params });
      setCashFlow(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Cash Flow data");
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  const loadInterest = useCallback(async () => {
    setLoading(true);
    try {
      const params = { annual_rate: interestRate };
      if (fromDate) params.from = fromDate;
      if (toDate) params.to = toDate;
      const r = await api.get("/accounting/interest-outstanding", { params });
      setInterest(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Interest Outstanding data");
    } finally { setLoading(false); }
  }, [fromDate, toDate, interestRate]);

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

  const ITEMS_PER_PAGE = 50;

  const dayBookEntries = dayBook?.entries || [];
  const totalDayBookPages = Math.ceil(dayBookEntries.length / ITEMS_PER_PAGE);
  const paginatedDayBookEntries = dayBookEntries.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const cashFlowTransactions = cashFlow?.transactions || [];
  const totalCashFlowPages = Math.ceil(cashFlowTransactions.length / ITEMS_PER_PAGE);
  const paginatedCashFlowTransactions = cashFlowTransactions.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const interestInvoices = interest?.invoices || [];
  const totalInterestPages = Math.ceil(interestInvoices.length / ITEMS_PER_PAGE);
  const paginatedInterestInvoices = interestInvoices.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

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
          const params = { tab };
          if (fromDate) params.from = fromDate;
          if (toDate) params.to = toDate;
          setSearchParams(params);

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
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center animate-pulse">Loading...</div>
          ) : dayBook ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <StatTile label="Journal Entries" value={dayBook.journal_entries_count || 0} />
                <StatTile label="Vouchers" value={dayBook.vouchers_count || 0} />
                <StatTile label="Total Records" value={dayBook.total_records || 0} accent />
              </div>
              {dayBookEntries.length > 0 ? (
                <div>
                  <table className="w-full text-sm border border-zinc-800">
                    <thead>
                      <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                        <th className="text-left px-4 py-2">Date</th>
                        <th className="text-left px-4 py-2">Voucher Number</th>
                        <th className="text-left px-4 py-2">Account Name</th>
                        <th className="text-left px-4 py-2">Description</th>
                        <th className="text-right px-4 py-2">Debit Amount</th>
                        <th className="text-right px-4 py-2">Credit Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedDayBookEntries.map((row, idx) => (
                        <tr key={idx} className={`border-b border-zinc-900 hover:bg-zinc-900/50 ${idx % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                          <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{row.date}</td>
                          <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{row.voucher_number}</td>
                          <td className="px-4 py-2 text-white font-medium">{row.account_name}</td>
                          <td className="px-4 py-2 text-zinc-400 text-xs max-w-xs truncate" title={row.description}>{row.description}</td>
                          <td className="px-4 py-2 text-right tabular text-zinc-300">{row.debit_amount > 0 ? `₹${inr(row.debit_amount)}` : "—"}</td>
                          <td className="px-4 py-2 text-right tabular text-zinc-300">{row.credit_amount > 0 ? `₹${inr(row.credit_amount)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Pagination currentPage={page} totalPages={totalDayBookPages} onPageChange={setPage} />
                </div>
              ) : (
                <EmptyState message="No day book entries available for the period" />
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
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center animate-pulse">Loading...</div>
          ) : cashFlow ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <StatTile label="Total Inflow" value={`₹${inr(cashFlow.total_inflow)}`} accent />
                <StatTile label="Total Outflow" value={`₹${inr(cashFlow.total_outflow)}`} />
                <StatTile label="Closing Balance" value={`₹${inr(cashFlow.closing_balance)}`} accent={cashFlow.closing_balance >= 0} />
              </div>
              {cashFlowTransactions.length > 0 ? (
                <div>
                  <table className="w-full text-sm border border-zinc-800">
                    <thead>
                      <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                        <th className="text-left px-4 py-2">Date</th>
                        <th className="text-left px-4 py-2">Transaction Reference</th>
                        <th className="text-left px-4 py-2">Description</th>
                        <th className="text-right px-4 py-2">Cash In</th>
                        <th className="text-right px-4 py-2">Cash Out</th>
                        <th className="text-right px-4 py-2">Running Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedCashFlowTransactions.map((row, idx) => (
                        <tr key={idx} className={`border-b border-zinc-900 hover:bg-zinc-900/50 ${idx % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                          <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{row.date}</td>
                          <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{row.reference}</td>
                          <td className="px-4 py-2 text-white text-xs max-w-xs truncate" title={row.description}>{row.description}</td>
                          <td className="px-4 py-2 text-right tabular text-green-400 font-medium">{row.cash_in > 0 ? `₹${inr(row.cash_in)}` : "—"}</td>
                          <td className="px-4 py-2 text-right tabular text-red-400 font-medium">{row.cash_out > 0 ? `₹${inr(row.cash_out)}` : "—"}</td>
                          <td className="px-4 py-2 text-right tabular text-zinc-300 font-semibold">₹{inr(row.running_balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Pagination currentPage={page} totalPages={totalCashFlowPages} onPageChange={setPage} />
                </div>
              ) : (
                <EmptyState message="No cash flow transactions available for the period" />
              )}
            </>
          ) : (
            <EmptyState message="No cash flow data available" />
          )}
        </div>
      )}

      {/* Interest Outstanding Tab */}
      {tab === "interest" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-4 bg-zinc-950 border border-zinc-850 p-4 font-mono">
            <div className="w-44">
              <span className="label-overline block mb-1">Interest Rate % (Annual)</span>
              <Input type="number" step="0.5" value={interestRate} onChange={e => setInterestRate(parseFloat(e.target.value) || 0)} className="!h-9" />
            </div>
            <SecondaryButton icon={RefreshCw} onClick={loadInterest} className="h-9">Recalculate</SecondaryButton>
          </div>

          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center animate-pulse">Loading...</div>
          ) : interest ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <StatTile label="Total Interest Due" value={`₹${inr(interest.total_interest_due)}`} accent />
                <StatTile label="Total Accounts" value={interest.total_accounts || 0} />
                <StatTile label="Overdue Accounts" value={interest.overdue_accounts || 0} accent={interest.overdue_accounts > 0} />
              </div>
              {interestInvoices.length > 0 ? (
                <div>
                  <table className="w-full text-sm border border-zinc-800">
                    <thead>
                      <tr className="label-overline border-b border-zinc-800 bg-zinc-900 text-zinc-400">
                        <th className="text-left px-4 py-2">Customer Name</th>
                        <th className="text-left px-4 py-2">Loan/Account Number</th>
                        <th className="text-right px-4 py-2">Interest Amount</th>
                        <th className="text-left px-4 py-2">Due Date</th>
                        <th className="text-right px-4 py-2">Days Outstanding</th>
                        <th className="text-left px-4 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedInterestInvoices.map((row, idx) => (
                        <tr key={idx} className={`border-b border-zinc-900 hover:bg-zinc-900/50 ${idx % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                          <td className="px-4 py-2 text-white font-bold">{row.customer_name}</td>
                          <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{row.account_number}</td>
                          <td className="px-4 py-2 text-right tabular text-yellow-500 font-bold">₹{inr(row.interest_amount)}</td>
                          <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{row.due_date}</td>
                          <td className="px-4 py-2 text-right tabular text-red-400 font-semibold">{row.days_outstanding} days</td>
                          <td className="px-4 py-2">
                            <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${
                              row.status === "OVERDUE" ? "border-red-900 bg-red-950 text-red-400" : "border-zinc-700 bg-zinc-800 text-zinc-500"
                            }`}>
                              {row.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Pagination currentPage={page} totalPages={totalInterestPages} onPageChange={setPage} />
                </div>
              ) : (
                <EmptyState message="No outstanding interest records available" />
              )}
            </>
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
