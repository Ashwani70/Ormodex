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
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, RefreshCw, Download, FileText, Search, Shield, Activity, ShieldCheck, AlertTriangle, Clock } from "lucide-react";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const TABS = [
  { id: "dashboard", label: "GST Dashboard" },
  { id: "records", label: "Records" },
  { id: "gstr1", label: "GSTR-1" },
  { id: "gstr3b", label: "GSTR-3B" },
  { id: "itc", label: "ITC Summary" },
  { id: "tds", label: "TDS" },
  { id: "tcs", label: "TCS" },
  { id: "filing", label: "Filing Status" },
  { id: "compliance", label: "Filing Compliance" },
  { id: "validate", label: "Validate GSTIN" },
];

const GST_TYPES = ["SALES", "PURCHASE", "CREDIT_NOTE", "DEBIT_NOTE"];
const FILING_STATUSES = ["PENDING", "FILED", "LATE_FILED"];

export default function GstAccounting() {
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [records, setRecords] = useState([]);
  const [gstr1, setGstr1] = useState(null);
  const [gstr3b, setGstr3b] = useState(null);
  const [itc, setItc] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [returnPeriod, setReturnPeriod] = useState(
    new Date().toLocaleDateString("en-IN", { month: "2-digit", year: "numeric" }).replace("/", "")
  );
  const [gstinInput, setGstinInput] = useState("");
  const [gstinResult, setGstinResult] = useState(null);
  const [search, setSearch] = useState("");
  const [tdsEntries, setTdsEntries] = useState([]);
  const [tcsEntries, setTcsEntries] = useState([]);
  const [tdsSummary, setTdsSummary] = useState(null);
  const [tcsSummary, setTcsSummary] = useState(null);
  const [tdsSections, setTdsSections] = useState([]);
  const [showTdsForm, setShowTdsForm] = useState(false);
  const [showTcsForm, setShowTcsForm] = useState(false);
  const [tdsForm, setTdsForm] = useState({
    entry_date: new Date().toISOString().split("T")[0], party_name: "", party_pan: "",
    tds_section: "194J", base_amount: "", tds_rate: 10, tds_amount: 0, net_amount: 0,
    return_period: returnPeriod, status: "DEDUCTED", remarks: "",
  });
  const [tcsForm, setTcsForm] = useState({
    entry_date: new Date().toISOString().split("T")[0], party_name: "", party_pan: "",
    tcs_section: "206C", base_amount: "", tcs_rate: 0.1, tcs_amount: 0, gross_amount: 0,
    return_period: returnPeriod, status: "COLLECTED", remarks: "",
  });

  // Filing Status tab state
  const [filingGstin, setFilingGstin] = useState("");
  const [filingFy, setFilingFy] = useState("2024-25");
  const [filingData, setFilingData] = useState(null);
  const [filingLoading, setFilingLoading] = useState(false);
  const [filingFilter, setFilingFilter] = useState("ALL");

  // Filing Compliance tab state
  const [complianceData, setComplianceData] = useState(null);
  const [complianceFy, setComplianceFy] = useState("2024-25");
  const [complianceLoading, setComplianceLoading] = useState(false);

  const [form, setForm] = useState({
    invoice_number: "", invoice_date: new Date().toISOString().split("T")[0],
    party_name: "", party_gstin: "", taxable_amount: "",
    cgst: 0, sgst: 0, igst: 0, cess: 0,
    gst_type: "SALES", return_period: returnPeriod,
    filing_status: "PENDING", source: "MANUAL",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "dashboard") {
        const r = await api.get("/gst/dashboard");
        setDashboard(r.data);
      } else if (tab === "records") {
        const r = await api.get("/gst/records", { params: { search } });
        setRecords(r.data.items || []);
      } else if (tab === "gstr1") {
        const r = await api.get("/gst/gstr1", { params: { return_period: returnPeriod } });
        setGstr1(r.data);
      } else if (tab === "gstr3b") {
        const r = await api.get("/gst/gstr3b", { params: { return_period: returnPeriod } });
        setGstr3b(r.data);
      } else if (tab === "tds") {
        const [e, s, sec] = await Promise.all([
          api.get("/gst/tds", { params: { return_period: returnPeriod } }),
          api.get("/gst/tds-summary", { params: { return_period: returnPeriod } }),
          api.get("/gst/tds-sections"),
        ]);
        setTdsEntries(e.data?.items || []);
        setTdsSummary(s.data);
        setTdsSections(sec.data || []);
      } else if (tab === "tcs") {
        const [e, s] = await Promise.all([
          api.get("/gst/tcs", { params: { return_period: returnPeriod } }),
          api.get("/gst/tcs-summary", { params: { return_period: returnPeriod } }),
        ]);
        setTcsEntries(e.data?.items || []);
        setTcsSummary(s.data);
      } else if (tab === "itc") {
        const r = await api.get("/gst/itc-summary");
        setItc(r.data);
      }
    } finally { setLoading(false); }
  }, [tab, search, returnPeriod]);

  useEffect(() => { load(); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const syncFromInvoices = async () => {
    try {
      const r = await api.post("/gst/sync-from-invoices", null, { params: { return_period: returnPeriod } });
      toast.success(`Synced ${r.data.synced} records`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Sync failed");
    }
  };

  const validateGstin = async () => {
    try {
      const r = await api.post("/gst/validate-gstin", { gstin: gstinInput });
      setGstinResult(r.data);
    } catch (e) {
      toast.error("Validation failed");
    }
  };

  const createRecord = async (e) => {
    e.preventDefault();
    try {
      const total = parseFloat(form.taxable_amount) + parseFloat(form.cgst) + parseFloat(form.sgst) + parseFloat(form.igst) + parseFloat(form.cess);
      await api.post("/gst/records", { ...form, total_amount: total,
        taxable_amount: parseFloat(form.taxable_amount), cgst: parseFloat(form.cgst),
        sgst: parseFloat(form.sgst), igst: parseFloat(form.igst), cess: parseFloat(form.cess),
      });
      toast.success("GST record created");
      setShowModal(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const openNew = () => {
    setForm({
      invoice_number: "", invoice_date: new Date().toISOString().split("T")[0],
      party_name: "", party_gstin: "", taxable_amount: "",
      cgst: 0, sgst: 0, igst: 0, cess: 0,
      gst_type: "SALES", return_period: returnPeriod,
      filing_status: "PENDING", source: "MANUAL",
    });
    setShowModal(true);
  };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank record, Esc
  // cancels, first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: showModal,
    autoFocus: true,
    onSave: () => createRecord(new Event("submit", { cancelable: true })),
    onSaveAndNew: async () => {
      await createRecord(new Event("submit", { cancelable: true }));
      openNew();
    },
    onCancel: () => setShowModal(false),
  });

  useModuleShortcuts({
    onNew: () => { if (!showModal) openNew(); },
  });

  return (
    <div data-testid="gst-page">
      <PageHeader
        eyebrow="Finance"
        title="GST Accounting"
        description="GST records, GSTR-1, GSTR-3B, ITC tracking and GSTIN validation."
        actions={
          <>
            <SecondaryButton icon={RefreshCw} onClick={syncFromInvoices} testid="sync-gst-btn">
              Sync from Invoices
            </SecondaryButton>
            <PrimaryButton icon={Plus} onClick={openNew} testid="add-gst-record-btn">
              Add Record
            </PrimaryButton>
          </>
        }
      />

      {/* Period selector */}
      <div className="flex items-center gap-3 mb-4">
        <span className="label-overline">Return Period (MMYYYY)</span>
        <Input value={returnPeriod} onChange={e => setReturnPeriod(e.target.value)} className="w-28" placeholder="052025" />
        <SecondaryButton icon={RefreshCw} onClick={load}>Apply</SecondaryButton>
      </div>

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-yellow-400 text-black font-bold" : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}>{t.label}</button>
        ))}
      </div>

      {loading && <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>}

      {/* Dashboard */}
      {!loading && tab === "dashboard" && dashboard && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="GST Liability" value={`₹${inr(dashboard.gst_liability)}`} accent />
            <StatTile label="ITC Available" value={`₹${inr(dashboard.itc_available)}`} />
            <StatTile label="Net Payable" value={`₹${inr(dashboard.net_payable)}`} />
            <StatTile label="Pending Filings" value={dashboard.pending_invoices} />
          </div>
          <div className="border border-zinc-800 bg-zinc-900 p-4">
            <p className="label-overline mb-2">Current Period: <span className="text-yellow-400">{dashboard.current_period}</span></p>
            <p className="text-xs text-zinc-500 font-mono">ITC offset applied. Net payable = GST Liability - ITC Available.</p>
          </div>
        </div>
      )}

      {/* Records */}
      {!loading && tab === "records" && (
        <>
          <div className="flex gap-2 mb-4">
            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search invoice, party..." className="max-w-xs" />
            <SecondaryButton icon={Search} onClick={load}>Search</SecondaryButton>
          </div>
          {records.length === 0 ? (
            <EmptyState message="No GST records" action={<PrimaryButton icon={Plus} onClick={openNew}>Add Record</PrimaryButton>} />
          ) : (
            <table className="w-full text-sm border border-zinc-800">
              <thead>
                <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                  <th className="text-left px-4 py-2">Invoice No</th>
                  <th className="text-left px-4 py-2">Date</th>
                  <th className="text-left px-4 py-2">Party</th>
                  <th className="text-left px-4 py-2">Type</th>
                  <th className="text-right px-4 py-2">Taxable</th>
                  <th className="text-right px-4 py-2">CGST</th>
                  <th className="text-right px-4 py-2">SGST</th>
                  <th className="text-right px-4 py-2">IGST</th>
                  <th className="text-right px-4 py-2">Total</th>
                  <th className="text-left px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-yellow-400 text-xs">{r.invoice_number}</td>
                    <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{r.invoice_date}</td>
                    <td className="px-4 py-2 text-white text-xs">{r.party_name}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${r.gst_type === "SALES" ? "border-green-800 bg-green-950 text-green-400" : "border-blue-800 bg-blue-950 text-blue-400"}`}>{r.gst_type}</span>
                    </td>
                    <td className="px-4 py-2 text-right tabular text-xs">₹{inr(r.taxable_amount)}</td>
                    <td className="px-4 py-2 text-right tabular text-xs text-zinc-400">₹{inr(r.cgst)}</td>
                    <td className="px-4 py-2 text-right tabular text-xs text-zinc-400">₹{inr(r.sgst)}</td>
                    <td className="px-4 py-2 text-right tabular text-xs text-zinc-400">₹{inr(r.igst)}</td>
                    <td className="px-4 py-2 text-right tabular font-semibold">₹{inr(r.total_amount)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${r.filing_status === "FILED" ? "border-green-800 bg-green-950 text-green-400" : "border-yellow-800 bg-yellow-950 text-yellow-400"}`}>{r.filing_status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {/* GSTR-1 */}
      {!loading && tab === "gstr1" && gstr1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Total Invoices" value={gstr1.summary?.total_invoices || 0} />
            <StatTile label="Taxable Value" value={`₹${inr(gstr1.summary?.total_taxable)}`} />
            <StatTile label="Total Tax" value={`₹${inr(gstr1.summary?.total_tax)}`} accent />
            <StatTile label="Grand Total" value={`₹${inr(gstr1.summary?.grand_total)}`} />
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            {["total_cgst","total_sgst","total_igst"].map(k => (
              <div key={k} className="border border-zinc-800 bg-zinc-900 p-3">
                <div className="label-overline mb-1">{k.replace("total_","").toUpperCase()}</div>
                <div className="font-display font-black text-xl text-white">₹{inr(gstr1.summary?.[k])}</div>
              </div>
            ))}
          </div>
          {gstr1.b2b_invoices?.length > 0 && (
            <div>
              <SectionTitle>B2B Invoices ({gstr1.b2b_invoices.length})</SectionTitle>
              <p className="text-xs text-zinc-500 font-mono">Registered buyers with GSTIN</p>
            </div>
          )}
          {gstr1.b2c_invoices?.length > 0 && (
            <div>
              <SectionTitle>B2C Invoices ({gstr1.b2c_invoices.length})</SectionTitle>
              <p className="text-xs text-zinc-500 font-mono">Unregistered buyers</p>
            </div>
          )}
        </div>
      )}

      {/* GSTR-3B */}
      {!loading && tab === "gstr3b" && gstr3b && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="border border-green-900 bg-green-950/30 p-4">
            <SectionTitle>Outward Supplies (Sales)</SectionTitle>
            {Object.entries(gstr3b.outward_supplies || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-zinc-800 text-sm">
                <span className="text-zinc-400 font-mono uppercase keep-caps text-xs">{k.replace("_", " ")}</span>
                <span className="tabular text-white font-mono">₹{inr(v)}</span>
              </div>
            ))}
          </div>
          <div className="border border-blue-900 bg-blue-950/30 p-4">
            <SectionTitle>ITC Available (Purchases)</SectionTitle>
            {Object.entries(gstr3b.itc_available || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-zinc-800 text-sm">
                <span className="text-zinc-400 font-mono uppercase keep-caps text-xs">{k.replace("_", " ")}</span>
                <span className="tabular text-white font-mono">₹{inr(v)}</span>
              </div>
            ))}
          </div>
          <div className="border border-yellow-800 bg-yellow-950/30 p-4">
            <SectionTitle>Net Tax Payable</SectionTitle>
            {Object.entries(gstr3b.net_tax_payable || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between py-1 border-b border-zinc-800 text-sm">
                <span className="text-zinc-400 font-mono uppercase keep-caps text-xs">{k.replace("_", " ")}</span>
                <span className={`tabular font-mono font-bold ${v > 0 ? "text-red-400" : "text-green-400"}`}>₹{inr(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ITC Summary */}
      {!loading && tab === "itc" && (
        <table className="w-full text-sm border border-zinc-800">
          <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
            <th className="text-left px-4 py-2">Period</th>
            <th className="text-right px-4 py-2">CGST ITC</th>
            <th className="text-right px-4 py-2">SGST ITC</th>
            <th className="text-right px-4 py-2">IGST ITC</th>
            <th className="text-right px-4 py-2">Taxable</th>
            <th className="text-right px-4 py-2">Invoices</th>
          </tr></thead>
          <tbody>
            {itc.map((r, i) => (
              <tr key={r._id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                <td className="px-4 py-2 font-mono text-yellow-400">{r._id}</td>
                <td className="px-4 py-2 text-right tabular">₹{inr(r.total_cgst_itc)}</td>
                <td className="px-4 py-2 text-right tabular">₹{inr(r.total_sgst_itc)}</td>
                <td className="px-4 py-2 text-right tabular">₹{inr(r.total_igst_itc)}</td>
                <td className="px-4 py-2 text-right tabular">₹{inr(r.total_taxable)}</td>
                <td className="px-4 py-2 text-right tabular text-zinc-400">{r.invoice_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* TDS Management */}
      {tab === "tds" && (
        <div className="space-y-4">
          {tdsSummary && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <StatTile label="Total TDS Deducted" value={`₹${inr(tdsSummary.total_tds_deducted)}`} accent />
              <StatTile label="TDS Deposited" value={`₹${inr(tdsSummary.total_tds_deposited)}`} />
              <StatTile label="Pending Deposit" value={`₹${inr(tdsSummary.total_tds_pending)}`} />
            </div>
          )}
          <div className="flex justify-between items-center">
            <span className="font-mono text-xs text-zinc-500 uppercase">{tdsEntries.length} TDS Entries — Period: {returnPeriod}</span>
            <button onClick={() => setShowTdsForm(!showTdsForm)}
              className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2">
              <Plus className="w-3.5 h-3.5" /> Record TDS
            </button>
          </div>

          {showTdsForm && (
            <div className="bg-zinc-950 border border-zinc-800 p-5 space-y-3">
              <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2">New TDS Entry</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div>
                  <span className="label-overline block mb-1">Entry Date</span>
                  <input type="date" value={tdsForm.entry_date} onChange={e => setTdsForm(f => ({ ...f, entry_date: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">Party Name</span>
                  <input value={tdsForm.party_name} onChange={e => setTdsForm(f => ({ ...f, party_name: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">PAN</span>
                  <input value={tdsForm.party_pan} onChange={e => setTdsForm(f => ({ ...f, party_pan: e.target.value.toUpperCase() }))}
                    placeholder="ABCDE1234F"
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">TDS Section</span>
                  <select value={tdsForm.tds_section} onChange={e => setTdsForm(f => ({ ...f, tds_section: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                    {tdsSections.map(s => <option key={s.code} value={s.code}>Sec {s.code} — {s.description}</option>)}
                  </select>
                </div>
                <div>
                  <span className="label-overline block mb-1">Base Amount ₹</span>
                  <input type="text" inputMode="decimal" value={tdsForm.base_amount}
                    onChange={e => {
                      const base = parseFloat(e.target.value) || 0;
                      const tds = parseFloat((base * tdsForm.tds_rate / 100).toFixed(2));
                      setTdsForm(f => ({ ...f, base_amount: base, tds_amount: tds, net_amount: parseFloat((base - tds).toFixed(2)) }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">TDS Rate %</span>
                  <input type="text" inputMode="decimal" step="0.01" value={tdsForm.tds_rate}
                    onChange={e => {
                      const rate = parseFloat(e.target.value) || 0;
                      const tds = parseFloat((tdsForm.base_amount * rate / 100).toFixed(2));
                      setTdsForm(f => ({ ...f, tds_rate: rate, tds_amount: tds, net_amount: parseFloat((f.base_amount - tds).toFixed(2)) }));
                    }}
                    className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                </div>
                <div>
                  <span className="label-overline block mb-1">TDS Amount ₹</span>
                  <input type="text" inputMode="decimal" value={tdsForm.tds_amount} readOnly
                    className="w-full bg-zinc-900 border border-zinc-600 text-yellow-400 text-xs px-3 py-2 opacity-80" />
                </div>
                <div>
                  <span className="label-overline block mb-1">Net Amount ₹</span>
                  <input type="text" inputMode="decimal" value={tdsForm.net_amount} readOnly
                    className="w-full bg-zinc-900 border border-zinc-600 text-green-400 text-xs px-3 py-2 opacity-80" />
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={async () => {
                  try {
                    await api.post("/gst/tds", { ...tdsForm, return_period: returnPeriod });
                    toast.success("TDS entry recorded"); setShowTdsForm(false); load();
                  } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                }} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Record TDS</button>
                <button onClick={() => setShowTdsForm(false)} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
              </div>
            </div>
          )}

          <div className="bg-zinc-950 border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr>
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-left px-4 py-2">Party</th>
                <th className="text-left px-4 py-2">PAN</th>
                <th className="text-left px-4 py-2">Section</th>
                <th className="text-right px-4 py-2">Base</th>
                <th className="text-right px-4 py-2">Rate%</th>
                <th className="text-right px-4 py-2">TDS</th>
                <th className="text-right px-4 py-2">Net</th>
                <th className="text-left px-4 py-2">Status</th>
              </tr></thead>
              <tbody>
                {tdsEntries.length === 0 && <tr><td colSpan={9} className="px-4 py-8 text-center text-zinc-600">No TDS entries for this period</td></tr>}
                {tdsEntries.map((t, i) => (
                  <tr key={t.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-zinc-400">{t.entry_date}</td>
                    <td className="px-4 py-2 text-zinc-200">{t.party_name}</td>
                    <td className="px-4 py-2 font-mono text-zinc-500">{t.party_pan || "—"}</td>
                    <td className="px-4 py-2 font-mono text-yellow-400">{t.tds_section}</td>
                    <td className="px-4 py-2 text-right tabular">{inr(t.base_amount)}</td>
                    <td className="px-4 py-2 text-right tabular text-zinc-500">{t.tds_rate}%</td>
                    <td className="px-4 py-2 text-right tabular font-semibold text-red-400">{inr(t.tds_amount)}</td>
                    <td className="px-4 py-2 text-right tabular text-green-400">{inr(t.net_amount)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        t.status === "DEPOSITED" ? "bg-green-950" : "bg-yellow-950"
                      }`}>{t.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {tdsSummary?.section_summary?.length > 0 && (
            <div className="bg-zinc-950 border border-zinc-800">
              <div className="border-b border-zinc-800 px-5 py-3 font-mono text-[10px] uppercase tracking-widest text-zinc-400">Section-wise TDS Summary</div>
              <table className="w-full text-xs">
                <thead><tr>
                  <th className="text-left px-4 py-2">Section</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Base Amount</th>
                  <th className="text-right px-4 py-2">TDS Amount</th>
                  <th className="text-right px-4 py-2">Count</th>
                </tr></thead>
                <tbody>
                  {tdsSummary.section_summary.map((s, i) => (
                    <tr key={i} className="border-b border-zinc-900">
                      <td className="px-4 py-2 font-mono text-yellow-400">{s._id?.section}</td>
                      <td className="px-4 py-2">
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                          s._id?.status === "DEPOSITED" ? "bg-green-950" : "bg-yellow-950"
                        }`}>{s._id?.status}</span>
                      </td>
                      <td className="px-4 py-2 text-right tabular text-zinc-300">{inr(s.total_base)}</td>
                      <td className="px-4 py-2 text-right tabular font-semibold text-red-400">{inr(s.total_tds)}</td>
                      <td className="px-4 py-2 text-right tabular text-zinc-500">{s.entry_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TCS Management */}
      {tab === "tcs" && (
        <div className="space-y-4">
          {tcsSummary && tcsSummary.sections?.length > 0 && (
            <div className="bg-zinc-950 border border-zinc-800">
              <div className="border-b border-zinc-800 px-5 py-3 font-mono text-[10px] uppercase tracking-widest text-zinc-400">TCS Section Summary</div>
              <table className="w-full text-xs">
                <thead><tr>
                  <th className="text-left px-4 py-2">Section</th>
                  <th className="text-right px-4 py-2">Base Amount</th>
                  <th className="text-right px-4 py-2">TCS Amount</th>
                  <th className="text-right px-4 py-2">Gross</th>
                  <th className="text-right px-4 py-2">Entries</th>
                </tr></thead>
                <tbody>
                  {tcsSummary.sections.map((s, i) => (
                    <tr key={i} className="border-b border-zinc-900">
                      <td className="px-4 py-2 font-mono text-yellow-400">{s._id}</td>
                      <td className="px-4 py-2 text-right tabular text-zinc-300">{inr(s.total_base)}</td>
                      <td className="px-4 py-2 text-right tabular font-semibold text-blue-400">{inr(s.total_tcs)}</td>
                      <td className="px-4 py-2 text-right tabular text-zinc-200">{inr(s.total_gross)}</td>
                      <td className="px-4 py-2 text-right tabular text-zinc-500">{s.entry_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex justify-between items-center">
            <span className="font-mono text-xs text-zinc-500 uppercase">{tcsEntries.length} TCS Entries — Period: {returnPeriod}</span>
            <button onClick={() => setShowTcsForm(!showTcsForm)}
              className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2">
              <Plus className="w-3.5 h-3.5" /> Record TCS
            </button>
          </div>

          {showTcsForm && (
            <div className="bg-zinc-950 border border-zinc-800 p-5 space-y-3">
              <div className="font-mono text-xs uppercase text-yellow-400 border-b border-zinc-800 pb-2">New TCS Entry</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: "Entry Date", field: "entry_date", type: "date" },
                  { label: "Party Name", field: "party_name", type: "text" },
                  { label: "PAN", field: "party_pan", type: "text", placeholder: "ABCDE1234F" },
                  { label: "TCS Section", field: "tcs_section", type: "text", placeholder: "206C" },
                  { label: "Base Amount ₹", field: "base_amount", type: "number" },
                  { label: "TCS Rate %", field: "tcs_rate", type: "number" },
                ].map(f => (
                  <div key={f.field}>
                    <span className="label-overline block mb-1">{f.label}</span>
                    <input type={f.type} value={tcsForm[f.field] || ""}
                      onChange={e => setTcsForm(cf => ({ ...cf, [f.field]: e.target.value }))}
                      placeholder={f.placeholder || ""}
                      className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <button onClick={async () => {
                  try {
                    const base = parseFloat(tcsForm.base_amount) || 0;
                    const rate = parseFloat(tcsForm.tcs_rate) || 0;
                    const tcs = parseFloat((base * rate / 100).toFixed(2));
                    await api.post("/gst/tcs", { ...tcsForm, base_amount: base, tcs_rate: rate, tcs_amount: tcs, gross_amount: base + tcs, return_period: returnPeriod });
                    toast.success("TCS entry recorded"); setShowTcsForm(false); load();
                  } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
                }} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Record TCS</button>
                <button onClick={() => setShowTcsForm(false)} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
              </div>
            </div>
          )}

          <div className="bg-zinc-950 border border-zinc-800">
            <table className="w-full text-xs">
              <thead><tr>
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-left px-4 py-2">Party</th>
                <th className="text-left px-4 py-2">Section</th>
                <th className="text-right px-4 py-2">Base</th>
                <th className="text-right px-4 py-2">Rate%</th>
                <th className="text-right px-4 py-2">TCS</th>
                <th className="text-right px-4 py-2">Gross</th>
                <th className="text-left px-4 py-2">Status</th>
              </tr></thead>
              <tbody>
                {tcsEntries.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">No TCS entries for this period</td></tr>}
                {tcsEntries.map((t, i) => (
                  <tr key={t.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 font-mono text-zinc-400">{t.entry_date}</td>
                    <td className="px-4 py-2 text-zinc-200">{t.party_name}</td>
                    <td className="px-4 py-2 font-mono text-yellow-400">{t.tcs_section}</td>
                    <td className="px-4 py-2 text-right tabular">{inr(t.base_amount)}</td>
                    <td className="px-4 py-2 text-right tabular text-zinc-500">{t.tcs_rate}%</td>
                    <td className="px-4 py-2 text-right tabular font-semibold text-blue-400">{inr(t.tcs_amount)}</td>
                    <td className="px-4 py-2 text-right tabular text-zinc-200">{inr(t.gross_amount)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        t.status === "DEPOSITED" ? "bg-green-950" : "bg-blue-950"
                      }`}>{t.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Filing Status Tab */}
      {tab === "filing" && (
        <div className="space-y-6">
          <div className="border border-zinc-800 bg-zinc-950 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-yellow-400" />
              <span className="font-mono text-xs uppercase tracking-widest text-zinc-300 font-bold">GST Return Filing Status Lookup</span>
            </div>
            <p className="text-xs text-zinc-500 font-mono mb-4">Check whether a taxpayer has filed GSTR-1, GSTR-3B, GSTR-2X and other returns for a financial year.</p>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <span className="label-overline block mb-1">GSTIN</span>
                <input value={filingGstin} onChange={e => setFilingGstin(e.target.value.toUpperCase())}
                  placeholder="e.g. 24AABCA2804L1Z0" maxLength={15}
                  className="w-56 bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 font-mono focus:outline-none focus:border-yellow-400" />
              </div>
              <div>
                <span className="label-overline block mb-1">Financial Year</span>
                <select value={filingFy} onChange={e => setFilingFy(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 font-mono focus:outline-none focus:border-yellow-400">
                  {["2025-26","2024-25","2023-24","2022-23","2021-22"].map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <button
                onClick={async () => {
                  if (!filingGstin || filingGstin.length < 15) { toast.error("Enter a valid 15-character GSTIN"); return; }
                  setFilingLoading(true); setFilingData(null);
                  try {
                    const r = await api.get(`/gst/filing-status/${filingGstin}/${filingFy}`);
                    setFilingData(r.data);
                  } catch (e) {
                    toast.error(e.response?.data?.detail || "Filing status lookup failed");
                  } finally { setFilingLoading(false); }
                }}
                disabled={filingLoading}
                className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2 disabled:opacity-50 flex items-center gap-2"
              >
                {filingLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                {filingLoading ? "Checking..." : "Check Filing Status"}
              </button>
            </div>
          </div>

          {filingLoading && (
            <div className="flex flex-col items-center justify-center py-16 border border-zinc-800 bg-zinc-950">
              <RefreshCw className="w-8 h-8 text-yellow-400 animate-spin mb-3" />
              <p className="font-mono text-xs uppercase text-zinc-500 tracking-widest">Fetching filing data from GST portal...</p>
            </div>
          )}

          {filingData && !filingLoading && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatTile label="Total Filings" value={filingData.total_filings || 0} />
                {Object.entries(filingData.summary || {}).slice(0, 3).map(([rt, s]) => (
                  <StatTile key={rt} label={rt} value={`${s.filed}/${s.total}`} accent={rt === "GSTR1"} />
                ))}
              </div>

              {filingData.from_cache && (
                <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-500 bg-zinc-900 border border-zinc-800 px-3 py-1.5 w-fit">
                  <Clock className="w-3 h-3" /> Cached result · Fetched {new Date(filingData.cached_at).toLocaleString("en-IN")}
                </div>
              )}

              {/* Filter tabs */}
              <div className="flex gap-1">
                {["ALL", "GSTR1", "GSTR3B", "GSTR2X", "GSTR1A"].map(f => (
                  <button key={f} onClick={() => setFilingFilter(f)}
                    className={`text-[10px] font-mono uppercase px-3 py-1.5 border transition-colors ${
                      filingFilter === f ? "border-yellow-400 bg-yellow-400/10 text-yellow-400" : "border-zinc-800 text-zinc-500 hover:text-white hover:border-zinc-600"
                    }`}>{f === "ALL" ? "All Returns" : f}</button>
                ))}
              </div>

              {/* Filing records table */}
              <div className="border border-zinc-800 bg-zinc-950 overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                      <th className="text-left px-4 py-2.5">Return Type</th>
                      <th className="text-left px-4 py-2.5">Period</th>
                      <th className="text-left px-4 py-2.5">Status</th>
                      <th className="text-left px-4 py-2.5">Date of Filing</th>
                      <th className="text-left px-4 py-2.5">Mode</th>
                      <th className="text-left px-4 py-2.5">ARN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(filingData.filings || []).filter(f => filingFilter === "ALL" || f.return_type === filingFilter).map((f, i) => (
                      <tr key={`${f.return_type}-${f.return_period}-${i}`}
                        className={`border-b border-zinc-900 hover:bg-zinc-900/80 transition-colors ${i % 2 === 1 ? "bg-zinc-900/20" : ""}`}>
                        <td className="px-4 py-2.5">
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 border ${
                            f.return_type === "GSTR1" ? "border-blue-800 bg-blue-950/40 text-blue-400" :
                            f.return_type === "GSTR3B" ? "border-purple-800 bg-purple-950/40 text-purple-400" :
                            f.return_type === "GSTR2X" ? "border-cyan-800 bg-cyan-950/40 text-cyan-400" :
                            "border-zinc-700 bg-zinc-800/40 text-zinc-400"
                          }`}>{f.return_type}</span>
                        </td>
                        <td className="px-4 py-2.5 text-zinc-300 font-mono">{f.return_period_formatted || f.return_period}</td>
                        <td className="px-4 py-2.5">
                          <span className={`text-[10px] font-mono px-2 py-0.5 border ${
                            f.status === "Filed" ? "border-green-800 bg-green-950/30 text-green-400" :
                            "border-red-800 bg-red-950/30 text-red-400"
                          }`}>{f.status}</span>
                        </td>
                        <td className="px-4 py-2.5 text-zinc-300 font-mono">{f.date_of_filing || "—"}</td>
                        <td className="px-4 py-2.5 text-zinc-500 font-mono">{f.mode_of_filing || "—"}</td>
                        <td className="px-4 py-2.5 text-zinc-600 font-mono text-[10px]">{f.acknowledgement_number || "—"}</td>
                      </tr>
                    ))}
                    {(filingData.filings || []).filter(f => filingFilter === "ALL" || f.return_type === filingFilter).length === 0 && (
                      <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600 font-mono">No records for this filter</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* Filing Compliance Tab */}
      {tab === "compliance" && (
        <div className="space-y-6">
          <div className="border border-zinc-800 bg-zinc-950 p-5">
            <div className="flex items-center gap-2 mb-4">
              <ShieldCheck className="w-4 h-4 text-yellow-400" />
              <span className="font-mono text-xs uppercase tracking-widest text-zinc-300 font-bold">Vendor Filing Compliance Check</span>
            </div>
            <p className="text-xs text-zinc-500 font-mono mb-4">Checks if your vendors have filed GSTR-1 and GSTR-3B. Vendors who haven't filed put your ITC at risk.</p>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <span className="label-overline block mb-1">Return Period (MMYYYY)</span>
                <input value={returnPeriod} onChange={e => setReturnPeriod(e.target.value)}
                  placeholder="052024" maxLength={6}
                  className="w-28 bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 font-mono focus:outline-none focus:border-yellow-400" />
              </div>
              <div>
                <span className="label-overline block mb-1">Financial Year</span>
                <select value={complianceFy} onChange={e => setComplianceFy(e.target.value)}
                  className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 font-mono focus:outline-none focus:border-yellow-400">
                  {["2025-26","2024-25","2023-24","2022-23"].map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <button
                onClick={async () => {
                  setComplianceLoading(true); setComplianceData(null);
                  try {
                    const r = await api.post(`/gst/reconciliation/filing-check?return_period=${returnPeriod}&financial_year=${complianceFy}`);
                    setComplianceData(r.data);
                    toast.success(`Checked ${r.data.total_vendors} vendors`);
                  } catch (e) {
                    toast.error(e.response?.data?.detail || "Compliance check failed");
                  } finally { setComplianceLoading(false); }
                }}
                disabled={complianceLoading}
                className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2 disabled:opacity-50 flex items-center gap-2"
              >
                {complianceLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                {complianceLoading ? "Checking Vendors..." : "Run Compliance Check"}
              </button>
            </div>
          </div>

          {complianceLoading && (
            <div className="flex flex-col items-center justify-center py-16 border border-zinc-800 bg-zinc-950">
              <RefreshCw className="w-8 h-8 text-yellow-400 animate-spin mb-3" />
              <p className="font-mono text-xs uppercase text-zinc-500 tracking-widest">Checking vendor filing status...</p>
              <p className="font-mono text-[10px] text-zinc-600 mt-1">This may take a moment if there are many vendors</p>
            </div>
          )}

          {complianceData && !complianceLoading && (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatTile label="Total Vendors" value={complianceData.total_vendors} />
                <div className="border border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/20 p-4">
                  <div className="label-overline text-green-700 dark:text-green-400 mb-1">Compliant</div>
                  <div className="font-display font-black text-2xl text-green-700 dark:text-green-400">{complianceData.compliant}</div>
                </div>
                <div className="border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/20 p-4">
                  <div className="label-overline text-red-700 dark:text-red-400 mb-1">Non-Compliant</div>
                  <div className="font-display font-black text-2xl text-red-700 dark:text-red-400">{complianceData.non_compliant}</div>
                </div>
                <div className="border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20 p-4">
                  <div className="label-overline text-amber-700 dark:text-amber-400 mb-1">At Risk</div>
                  <div className="font-display font-black text-2xl text-amber-700 dark:text-amber-400">{complianceData.at_risk}</div>
                </div>
              </div>

              {/* Vendor compliance table */}
              <div className="border border-zinc-800 bg-zinc-950 overflow-hidden">
                <div className="border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-zinc-400">
                    Vendor Filing Compliance — {complianceData.return_period} / {complianceData.financial_year}
                  </span>
                  {complianceData.non_compliant > 0 && (
                    <span className="flex items-center gap-1.5 text-[10px] font-mono text-red-400">
                      <AlertTriangle className="w-3 h-3" /> {complianceData.non_compliant} vendor(s) not filed — ITC at risk
                    </span>
                  )}
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                      <th className="text-left px-4 py-2.5">Vendor</th>
                      <th className="text-left px-4 py-2.5">GSTIN</th>
                      <th className="text-center px-4 py-2.5">GSTR-1</th>
                      <th className="text-left px-4 py-2.5">Filed On</th>
                      <th className="text-center px-4 py-2.5">GSTR-3B</th>
                      <th className="text-left px-4 py-2.5">Filed On</th>
                      <th className="text-right px-4 py-2.5">Purchase ₹</th>
                      <th className="text-right px-4 py-2.5">Tax ₹</th>
                      <th className="text-center px-4 py-2.5">ITC Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(complianceData.vendors || []).map((v, i) => (
                      <tr key={v.gstin}
                        className={`border-b border-zinc-900 hover:bg-zinc-900/80 transition-colors ${i % 2 === 1 ? "bg-zinc-900/20" : ""} ${
                          v.itc_risk === "HIGH" ? "bg-red-950/10" : ""
                        }`}>
                        <td className="px-4 py-2.5 text-zinc-200 font-medium">{v.vendor_name}</td>
                        <td className="px-4 py-2.5 font-mono text-zinc-400">{v.gstin}</td>
                        <td className="px-4 py-2.5 text-center">
                          {v.gstr1_filed ? (
                            <span className="text-green-400 text-[10px] font-mono font-bold">✓ FILED</span>
                          ) : (
                            <span className="text-red-400 text-[10px] font-mono font-bold">✗ NOT FILED</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-zinc-500">{v.gstr1_date || "—"}</td>
                        <td className="px-4 py-2.5 text-center">
                          {v.gstr3b_filed ? (
                            <span className="text-green-400 text-[10px] font-mono font-bold">✓ FILED</span>
                          ) : (
                            <span className="text-red-400 text-[10px] font-mono font-bold">✗ NOT FILED</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-zinc-500">{v.gstr3b_date || "—"}</td>
                        <td className="px-4 py-2.5 text-right tabular text-zinc-300">₹{inr(v.purchase_taxable)}</td>
                        <td className="px-4 py-2.5 text-right tabular text-zinc-400">₹{inr(v.purchase_tax)}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 border ${
                            v.itc_risk === "HIGH" ? "border-red-700 bg-red-950/40 text-red-400 animate-pulse" :
                            v.itc_risk === "MEDIUM" ? "border-amber-700 bg-amber-950/40 text-amber-400" :
                            v.itc_risk === "LOW" ? "border-green-700 bg-green-950/40 text-green-400" :
                            "border-zinc-700 bg-zinc-800 text-zinc-400"
                          }`}>{v.itc_risk}</span>
                        </td>
                      </tr>
                    ))}
                    {(complianceData.vendors || []).length === 0 && (
                      <tr><td colSpan={9} className="px-4 py-12 text-center text-zinc-600 font-mono">No vendor GSTINs found in purchase records for this period</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              {complianceData.vendors?.some(v => v.error) && (
                <div className="border border-amber-900 bg-amber-950/10 p-3">
                  <p className="text-[10px] font-mono text-amber-400 mb-1">⚠ Some vendor lookups encountered errors:</p>
                  {complianceData.vendors.filter(v => v.error).map(v => (
                    <p key={v.gstin} className="text-[10px] font-mono text-zinc-500">• {v.gstin}: {v.error}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === "validate" && (
        <div className="max-w-lg">
          <SectionTitle><Shield className="w-4 h-4" /> GSTIN Validator</SectionTitle>
          <div className="flex gap-2 mb-4">
            <Input value={gstinInput} onChange={e => setGstinInput(e.target.value.toUpperCase())} placeholder="e.g. 27AABCS1429B1Z2" maxLength={15} />
            <PrimaryButton onClick={validateGstin} testid="validate-gstin-btn">Validate</PrimaryButton>
          </div>
          {gstinResult && (
            <div className={`border p-4 space-y-2 ${gstinResult.is_valid ? "border-green-700 bg-green-950/30" : "border-red-700 bg-red-950/30"}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className={`text-lg font-bold ${gstinResult.is_valid ? "text-green-400" : "text-red-400"}`}>
                  {gstinResult.is_valid ? "✓ Valid GSTIN" : "✗ Invalid GSTIN"}
                </span>
              </div>
              {Object.entries(gstinResult).filter(([k]) => !["is_valid","error"].includes(k)).map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm border-b border-zinc-800 pb-1">
                  <span className="text-zinc-400 font-mono text-xs uppercase keep-caps">{k.replace(/_/g, " ")}</span>
                  <span className="text-white font-mono">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Add Record Modal */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="Add GST Record">
        <form ref={formRef} onSubmit={createRecord} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Invoice Number" required><Input value={form.invoice_number} onChange={e => setForm(f => ({ ...f, invoice_number: e.target.value }))} required /></Field>
            <Field label="Invoice Date" required><Input type="date" value={form.invoice_date} onChange={e => setForm(f => ({ ...f, invoice_date: e.target.value }))} required /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Party Name" required><Input value={form.party_name} onChange={e => setForm(f => ({ ...f, party_name: e.target.value }))} required /></Field>
            <Field label="Party GSTIN"><Input value={form.party_gstin} onChange={e => setForm(f => ({ ...f, party_gstin: e.target.value }))} placeholder="Optional" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="GST Type"><Select value={form.gst_type} onChange={e => setForm(f => ({ ...f, gst_type: e.target.value }))}>{GST_TYPES.map(t => <option key={t}>{t}</option>)}</Select></Field>
            <Field label="Filing Status"><Select value={form.filing_status} onChange={e => setForm(f => ({ ...f, filing_status: e.target.value }))}>{FILING_STATUSES.map(s => <option key={s}>{s}</option>)}</Select></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Taxable Amount"><Input type="text" inputMode="decimal" step="0.01" value={form.taxable_amount} onChange={e => setForm(f => ({ ...f, taxable_amount: e.target.value }))} /></Field>
            <Field label="Return Period"><Input value={form.return_period} onChange={e => setForm(f => ({ ...f, return_period: e.target.value }))} placeholder="MMYYYY" /></Field>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {["cgst","sgst","igst","cess"].map(k => (
              <Field key={k} label={k.toUpperCase()}><Input type="text" inputMode="decimal" step="0.01" value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} /></Field>
            ))}
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Create</PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
