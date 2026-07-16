import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import usePdfAction from "@/hooks/usePdfAction";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";

const TABS = ["PDC Register", "Maturity Alerts", "Cheque Print", "Bank Reconciliation", "Overdue Interest"];

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
const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const v = { primary: "bg-yellow-400 text-zinc-950 hover:bg-yellow-300", secondary: "bg-zinc-700 text-white hover:bg-zinc-600", danger: "bg-red-800 text-white hover:bg-red-700", success: "bg-emerald-700 text-white hover:bg-emerald-600", ghost: "text-zinc-400 hover:text-white" };
  return <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${v[variant]} ${className}`} onClick={onClick} disabled={disabled}>{children}</button>;
};
const StatusBadge = ({ status }) => {
  const c = { PENDING: "bg-zinc-700 text-zinc-300", PRESENTED: "bg-blue-900 text-blue-300", CLEARED: "bg-emerald-900 text-emerald-300", BOUNCED: "bg-red-900 text-red-300", CANCELLED: "bg-zinc-700 text-zinc-500" };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c[status] ?? "bg-zinc-700 text-zinc-300"}`}>{status}</span>;
};
const fmt = (n) => `₹${Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

// ════════════════════════════════════════════
// PDC Register
// ════════════════════════════════════════════
function PDCRegisterTab() {
  const [pdcs, setPdcs] = useState([]);
  const [typeFilter, setTypeFilter] = useState("received");
  const [statusFilter, setStatusFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ type: "received", party_id: "", party_name: "", cheque_no: "", bank_name: "", amount: "", instrument_date: "", notes: "" });
  const [actionModal, setActionModal] = useState(null); // {pdc, action: "clear"|"bounce"}
  const [actionForm, setActionForm] = useState({ action_date: "", bounce_charges: "0", notes: "" });

  const load = useCallback(async () => {
    const params = { pdc_type: typeFilter };
    if (statusFilter) params.status = statusFilter;
    try { const { data } = await api.get("/banking-pdc/pdc", { params }); setPdcs(data); }
    catch { setPdcs([]); }
  }, [typeFilter, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      await api.post("/banking-pdc/pdc", { ...form, amount: parseFloat(form.amount) || 0 });
      setShowForm(false); load();
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  const present = async (pdc) => {
    try { await api.post(`/banking-pdc/pdc/${pdc.id}/present`); load(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  const doAction = async () => {
    const { pdc, action } = actionModal;
    try {
      await api.post(`/banking-pdc/pdc/${pdc.id}/${action}`, { ...actionForm, bounce_charges: parseFloat(actionForm.bounce_charges) || 0 });
      setActionModal(null); load();
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  // Add-PDC modal: this is the tab's primary create action, so it owns Ctrl+N.
  const pdcFormRef = useRef(null);
  useEnterNavigation(pdcFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: save,
    onCancel: () => setShowForm(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!showForm) setShowForm(true); },
  });

  // Clear/Bounce modal: secondary action, no Ctrl+N.
  const actionFormRef = useRef(null);
  useEnterNavigation(actionFormRef, {
    enabled: !!actionModal,
    autoFocus: true,
    onSave: doAction,
    onCancel: () => setActionModal(null),
  });

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-4">
      <SectionHeader title="PDC Register" action={<Btn onClick={() => setShowForm(true)}>+ Add PDC</Btn>} />
      <Card>
        <div className="flex gap-3 mb-4">
          {["received", "issued"].map(t => (
            <button key={t} onClick={() => setTypeFilter(t)} className={`px-4 py-1.5 rounded-lg text-sm font-medium ${typeFilter === t ? "bg-yellow-400 text-zinc-950" : "bg-zinc-800 text-zinc-400 hover:text-white"}`}>{t === "received" ? "Received" : "Issued"}</button>
          ))}
          <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">All Status</option>
            {["PENDING", "PRESENTED", "CLEARED", "BOUNCED"].map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">PDC No</th><th className="text-left py-2 pr-3">Party</th>
            <th className="text-left py-2 pr-3">Cheque No</th><th className="text-left py-2 pr-3">Bank</th>
            <th className="text-right py-2 pr-3">Amount</th><th className="text-left py-2 pr-3">Instrument Date</th>
            <th className="text-left py-2 pr-3">Status</th><th className="text-left py-2">Actions</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {pdcs.map(p => (
              <tr key={p.id} className="hover:bg-zinc-800/40">
                <td className="py-2 pr-3 text-yellow-400 font-mono">{p.pdc_no}</td>
                <td className="py-2 pr-3 text-white">{p.party_name || p.party_id}</td>
                <td className="py-2 pr-3 text-zinc-300 font-mono">{p.cheque_no}</td>
                <td className="py-2 pr-3 text-zinc-400">{p.bank_name}</td>
                <td className="py-2 pr-3 text-right font-semibold text-white">{fmt(p.amount)}</td>
                <td className={`py-2 pr-3 ${p.instrument_date < today && p.status === "PENDING" ? "text-red-400 font-semibold" : "text-zinc-300"}`}>{p.instrument_date}</td>
                <td className="py-2 pr-3"><StatusBadge status={p.status} /></td>
                <td className="py-2 flex gap-1">
                  {p.status === "PENDING" && <Btn variant="secondary" className="text-xs !px-2 !py-1" onClick={() => present(p)}>Present</Btn>}
                  {["PENDING", "PRESENTED"].includes(p.status) && (
                    <>
                      <Btn variant="success" className="text-xs !px-2 !py-1" onClick={() => { setActionModal({ pdc: p, action: "clear" }); setActionForm({ action_date: today, bounce_charges: "0", notes: "" }); }}>Clear</Btn>
                      <Btn variant="danger" className="text-xs !px-2 !py-1" onClick={() => { setActionModal({ pdc: p, action: "bounce" }); setActionForm({ action_date: today, bounce_charges: "500", notes: "" }); }}>Bounce</Btn>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {pdcs.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-zinc-500">No PDCs found</td></tr>}
          </tbody>
        </table>
      </Card>

      {/* Note about PDC control ledger */}
      <Card className="bg-zinc-900/50 border-zinc-800/50">
        <p className="text-xs text-zinc-500">PDCs remain in a PDC Control ledger until cleared. Clearing/bouncing posts the accounting entry to the bank account. Balance remains unaffected until clearance.</p>
      </Card>

      {/* Add PDC Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div ref={pdcFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-white font-semibold">Add PDC</h3>
            <Select label="Type" value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
              <option value="received">Received (from customer)</option>
              <option value="issued">Issued (to vendor)</option>
            </Select>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Party ID" value={form.party_id} onChange={e => setForm(f => ({ ...f, party_id: e.target.value }))} />
              <Input label="Party Name" value={form.party_name} onChange={e => setForm(f => ({ ...f, party_name: e.target.value }))} />
              <Input label="Cheque No" value={form.cheque_no} onChange={e => setForm(f => ({ ...f, cheque_no: e.target.value }))} />
              <Input label="Bank Name" value={form.bank_name} onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))} />
              <Input label="Amount (₹)" inputMode="decimal" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} />
              <Input label="Instrument Date" type="date" value={form.instrument_date} onChange={e => setForm(f => ({ ...f, instrument_date: e.target.value }))} />
              <div className="col-span-2"><Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} /></div>
            </div>
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn onClick={save}>Save PDC</Btn>
            </div>
          </div>
        </div>
      )}

      {/* Clear/Bounce Modal */}
      {actionModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div ref={actionFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm space-y-4">
            <h3 className={`font-semibold ${actionModal.action === "bounce" ? "text-red-400" : "text-emerald-400"}`}>
              {actionModal.action === "bounce" ? "Bounce" : "Clear"} PDC — {actionModal.pdc.pdc_no}
            </h3>
            <p className="text-zinc-400 text-sm">Cheque #{actionModal.pdc.cheque_no} · {fmt(actionModal.pdc.amount)}</p>
            <Input label="Action Date" type="date" value={actionForm.action_date} onChange={e => setActionForm(f => ({ ...f, action_date: e.target.value }))} />
            {actionModal.action === "bounce" && <Input label="Bounce Charges (₹)" inputMode="decimal" value={actionForm.bounce_charges} onChange={e => setActionForm(f => ({ ...f, bounce_charges: e.target.value }))} />}
            <Input label="Notes" value={actionForm.notes} onChange={e => setActionForm(f => ({ ...f, notes: e.target.value }))} />
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setActionModal(null)}>Cancel</Btn>
              <Btn variant={actionModal.action === "bounce" ? "danger" : "success"} onClick={doAction}>Confirm {actionModal.action === "bounce" ? "Bounce" : "Clear"}</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Maturity Alerts
// ════════════════════════════════════════════
function MaturityTab() {
  const [maturing, setMaturing] = useState([]);
  const [range, setRange] = useState({ from: new Date().toISOString().slice(0, 10), to: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10) });

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/banking-pdc/pdc/maturing", { params: { from: range.from, to: range.to } });
      setMaturing(data);
    } catch { setMaturing([]); }
  }, [range.from, range.to]);

  // Load once on mount; subsequent loads are explicit via the "Load" button
  // so editing the date fields doesn't fire a request per keystroke.
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const overdue = maturing.filter(p => p.is_overdue);
  const upcoming = maturing.filter(p => !p.is_overdue);

  return (
    <div className="space-y-4">
      <SectionHeader title="PDC Maturity Alerts" />
      <Card>
        <div className="grid grid-cols-3 gap-3 items-end">
          <Input label="From Date" type="date" value={range.from} onChange={e => setRange(r => ({ ...r, from: e.target.value }))} />
          <Input label="To Date" type="date" value={range.to} onChange={e => setRange(r => ({ ...r, to: e.target.value }))} />
          <Btn onClick={load}>Load</Btn>
        </div>
      </Card>
      {overdue.length > 0 && (
        <Card className="border-red-800/40">
          <p className="text-red-400 font-semibold mb-3">Overdue PDCs ({overdue.length})</p>
          <table className="w-full text-sm">
            <thead><tr className="text-zinc-500 border-b border-zinc-800"><th className="text-left pb-1">PDC No</th><th className="text-left pb-1">Party</th><th className="text-right pb-1">Amount</th><th className="text-left pb-1">Due Date</th><th className="text-right pb-1">Days Overdue</th></tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {overdue.map(p => (
                <tr key={p.id}>
                  <td className="py-2 text-yellow-400 font-mono">{p.pdc_no}</td>
                  <td className="py-2 text-white">{p.party_name || p.party_id}</td>
                  <td className="py-2 text-right font-semibold">{fmt(p.amount)}</td>
                  <td className="py-2 text-red-400">{p.instrument_date}</td>
                  <td className="py-2 text-right text-red-400 font-semibold">{Math.abs(p.days_to_maturity)} days</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <Card>
        <p className="text-zinc-400 font-medium mb-3">Upcoming ({upcoming.length})</p>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-500 border-b border-zinc-800"><th className="text-left pb-1">PDC No</th><th className="text-left pb-1">Party</th><th className="text-right pb-1">Amount</th><th className="text-left pb-1">Due Date</th><th className="text-right pb-1">Days Remaining</th></tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {upcoming.map(p => (
              <tr key={p.id}>
                <td className="py-2 text-yellow-400 font-mono">{p.pdc_no}</td>
                <td className="py-2 text-white">{p.party_name || p.party_id}</td>
                <td className="py-2 text-right font-semibold">{fmt(p.amount)}</td>
                <td className="py-2 text-zinc-300">{p.instrument_date}</td>
                <td className={`py-2 text-right font-semibold ${p.days_to_maturity <= 7 ? "text-amber-400" : "text-emerald-400"}`}>{p.days_to_maturity} days</td>
              </tr>
            ))}
            {upcoming.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-zinc-500">No upcoming PDCs in range</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════
// Cheque Print
// ════════════════════════════════════════════
// The preview/print canvas uses the same coordinate space the cheque formats are
// authored in (x/y in px against this box), so what you preview is what prints.
const CHEQUE_CANVAS = { width: 500, height: 200 };
// Standard Indian CTS-2010 cheque leaf ≈ 8" × 3.66". The print canvas is scaled
// from the authoring coordinate space to these physical dimensions.
const CHEQUE_PRINT = { width: "8in", height: "3.66in" };

function ChequePrintTab() {
  const [formats, setFormats] = useState([]);
  const [form, setForm] = useState({ payee_name: "", amount: "", amount_date: new Date().toISOString().slice(0, 10), format_id: "" });
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/banking-pdc/cheque-formats").then(r => { setFormats(r.data); if (r.data[0]) setForm(f => ({ ...f, format_id: r.data[0].id })); }).catch(() => {});
  }, []);

  const generate = async () => {
    if (!form.payee_name || !form.amount || !form.format_id) return;
    setLoading(true);
    try { const { data } = await api.post("/banking-pdc/cheques/print", { ...form, amount: parseFloat(form.amount) || 0 }); setPreview(data); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
    finally { setLoading(false); }
  };

  // Open a clean print window containing ONLY the cheque, sized to a real cheque
  // leaf with the fields absolutely positioned from the format coordinates. This
  // sends actual ink to the physical cheque (no app chrome, no background).
  const printCheque = () => {
    if (!preview) return;
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
    ));
    // Scale each field's authoring coordinate to the physical canvas in %.
    const fieldsHtml = (preview.fields || []).map((fld) => {
      const leftPct = (Number(fld.x) || 0) / CHEQUE_CANVAS.width * 100;
      const topPct = (Number(fld.y) || 0) / CHEQUE_CANVAS.height * 100;
      return `<div style="position:absolute;left:${leftPct}%;top:${topPct}%;`
        + `font-size:${Number(fld.font_size) || 12}pt;`
        + `font-family:${esc(fld.font || "Arial")};white-space:nowrap;color:#000;">`
        + `${esc(fld.value)}</div>`;
    }).join("");

    const win = window.open("", "_blank", "width=900,height=500");
    if (!win) { alert("Please allow pop-ups to print cheques."); return; }
    win.document.write(`<!DOCTYPE html><html><head><title>Cheque — ${esc(preview.payee_name || form.payee_name)}</title>
      <style>
        @page { size: ${CHEQUE_PRINT.width} ${CHEQUE_PRINT.height}; margin: 0; }
        * { box-sizing: border-box; }
        html, body { margin: 0; padding: 0; }
        .cheque { position: relative; width: ${CHEQUE_PRINT.width}; height: ${CHEQUE_PRINT.height};
                  background: #fff; color: #000; overflow: hidden; }
        .micr { position: absolute; left: 8%; bottom: 4%; font-family: 'Courier New', monospace; font-size: 11pt; color: #000; }
        @media screen { body { background: #555; padding: 24px; }
                        .cheque { box-shadow: 0 2px 12px rgba(0,0,0,.4); } }
      </style></head>
      <body>
        <div class="cheque">
          ${fieldsHtml}
          ${preview.micr_line ? `<div class="micr">${esc(preview.micr_line)}</div>` : ""}
        </div>
        <script>window.onload = function(){ window.focus(); window.print(); };${"<"}/script>
      </body></html>`);
    win.document.close();
  };

  // Server-rendered, archivable cheque PDF (sized to a real leaf). The endpoint
  // is a POST with a body, so we fetch the blob directly rather than via the
  // GET-only usePdfAction helper.
  const [pdfBusy, setPdfBusy] = useState(false);
  const savePdf = async () => {
    if (!form.payee_name || !form.amount || !form.format_id) return;
    setPdfBusy(true);
    try {
      const resp = await api.post(
        "/banking-pdc/cheques/pdf",
        { ...form, amount: parseFloat(form.amount) || 0 },
        { responseType: "blob" }
      );
      const url = URL.createObjectURL(new Blob([resp.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `cheque-${(form.payee_name || "cheque").replace(/[^a-z0-9 _-]/gi, "").trim() || "cheque"}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      let detail = e.response?.data;
      if (detail instanceof Blob) { try { detail = JSON.parse(await detail.text())?.detail; } catch { detail = null; } }
      else { detail = detail?.detail; }
      alert(detail || "Could not generate PDF.");
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Cheque Print" />
      <Card>
        <div className="grid grid-cols-2 gap-4">
          <Input label="Payee Name" value={form.payee_name} onChange={e => setForm(f => ({ ...f, payee_name: e.target.value }))} placeholder="Pay To..." />
          <Input label="Amount (₹)" inputMode="decimal" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} />
          <Input label="Date" type="date" value={form.amount_date} onChange={e => setForm(f => ({ ...f, amount_date: e.target.value }))} />
          <Select label="Cheque Format" value={form.format_id} onChange={e => setForm(f => ({ ...f, format_id: e.target.value }))}>
            <option value="">Select format...</option>
            {formats.map(f => <option key={f.id} value={f.id}>{f.name} — {f.bank_name}</option>)}
          </Select>
        </div>
        <div className="mt-4"><Btn onClick={generate} disabled={loading}>{loading ? "Generating..." : "Preview Cheque"}</Btn></div>
      </Card>

      {preview && (
        <Card className="border-yellow-800/40">
          <SectionHeader
            title={`${preview.format} — ${preview.bank_name}`}
            action={
              <div className="flex gap-2">
                <Btn variant="secondary" onClick={savePdf} disabled={pdfBusy}>{pdfBusy ? "Saving..." : "Save as PDF"}</Btn>
                <Btn onClick={printCheque}>Print Cheque</Btn>
              </div>
            }
          />
          {/* Amount-in-words display */}
          <div className="bg-zinc-800 rounded-lg p-4 mb-4">
            <p className="text-xs text-zinc-400 mb-1">Amount in Words</p>
            <p className="text-white font-semibold text-lg">{preview.amount_words}</p>
          </div>
          {/* Field layout preview — positioned as a % of the canvas so it matches
              the printed cheque exactly. */}
          <div
            className="bg-white rounded-lg relative mx-auto"
            style={{ width: "100%", maxWidth: `${CHEQUE_CANVAS.width}px`, aspectRatio: `${CHEQUE_CANVAS.width} / ${CHEQUE_CANVAS.height}`, overflow: "hidden" }}
          >
            {preview.fields.map((field, i) => (
              <div key={i} style={{
                position: "absolute",
                left: `${(Number(field.x) || 0) / CHEQUE_CANVAS.width * 100}%`,
                top: `${(Number(field.y) || 0) / CHEQUE_CANVAS.height * 100}%`,
                // physical cheque-print preview: black ink on white paper is intentional, not app chrome
                // eslint-disable-next-line no-restricted-syntax
                fontSize: field.font_size, fontFamily: field.font || "Arial", color: "#000", whiteSpace: "nowrap",
              }}>
                {field.value}
              </div>
            ))}
          </div>
          {preview.micr_line && (
            <div className="mt-3 font-mono text-xs text-zinc-500">{preview.micr_line}</div>
          )}
          <p className="mt-3 text-xs text-zinc-500">
            Tip: in the print dialog set margins to <span className="text-zinc-300">None</span> and scale to <span className="text-zinc-300">100%</span>, then load the cheque leaf in your printer.
          </p>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Bank Reconciliation
// ════════════════════════════════════════════
function BankReconTab() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [importLines, setImportLines] = useState("");
  const [reconResult, setReconResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  // Statement PDF reads the bank_statements store keyed by the CoA account code,
  // which is a different identifier from the recon bank_account_id above — so it
  // gets its own account picker sourced from the chart of accounts.
  const { run: downloadStatementPdf, busy: pdfBusy } = usePdfAction();
  const [coaAccounts, setCoaAccounts] = useState([]);
  const [stmtCode, setStmtCode] = useState("");
  const [stmtFrom, setStmtFrom] = useState("");
  const [stmtTo, setStmtTo] = useState("");

  useEffect(() => {
    api.get("/banking-pdc/bank-accounts").then(r => setAccounts(r.data)).catch(() => {});
    api.get("/accounting/chart-of-accounts").then(r => setCoaAccounts(r.data)).catch(() => {});
  }, []);

  const downloadStatement = () => {
    const params = new URLSearchParams({ bank_account_code: stmtCode });
    if (stmtFrom) params.append("from_date", stmtFrom);
    if (stmtTo) params.append("to_date", stmtTo);
    downloadStatementPdf(`/banking/statements/pdf?${params.toString()}`, `statement-${stmtCode}.pdf`);
  };

  const loadSummary = useCallback(async () => {
    if (!selectedAccount) return;
    try { const { data } = await api.get("/banking-pdc/bank-recon/summary", { params: { bank_account_id: selectedAccount } }); setSummary(data); }
    catch { setSummary(null); }
  }, [selectedAccount]);

  useEffect(() => { if (selectedAccount) loadSummary(); }, [selectedAccount, loadSummary]);

  const importFeed = async () => {
    if (!selectedAccount || !importLines.trim()) return;
    try {
      const lines = importLines.trim().split("\n").map(row => {
        const [txn_date, narration, debit, credit, reference] = row.split(",");
        return { bank_account_id: selectedAccount, txn_date: txn_date?.trim(), narration: narration?.trim(), debit: parseFloat(debit) || 0, credit: parseFloat(credit) || 0, reference: reference?.trim() };
      }).filter(l => l.txn_date && l.narration);
      await api.post(`/banking-pdc/bank-feeds/import?bank_account_id=${selectedAccount}`, lines);
      alert(`Imported ${lines.length} lines`);
      loadSummary();
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  const autoMatch = async () => {
    if (!selectedAccount) return;
    setLoading(true);
    try { const { data } = await api.post(`/banking-pdc/bank-recon/match?bank_account_id=${selectedAccount}`); setReconResult(data); loadSummary(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Bank Reconciliation" />

      {/* Statement PDF export toolbar */}
      <Card>
        <p className="text-zinc-400 text-sm font-medium mb-2">Bank Statement (PDF)</p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <Select label="Account" value={stmtCode} onChange={e => setStmtCode(e.target.value)}>
            <option value="">Select account...</option>
            {coaAccounts.map(a => <option key={a.code} value={a.code}>{a.code} — {a.name}</option>)}
          </Select>
          <Input label="From" type="date" value={stmtFrom} onChange={e => setStmtFrom(e.target.value)} />
          <Input label="To" type="date" value={stmtTo} onChange={e => setStmtTo(e.target.value)} />
          <Btn onClick={downloadStatement} disabled={!stmtCode || pdfBusy}>
            {pdfBusy ? "Generating..." : "Download PDF"}
          </Btn>
        </div>
      </Card>

      <Card>
        <div className="grid grid-cols-2 gap-3 items-end">
          <Select label="Bank Account" value={selectedAccount} onChange={e => setSelectedAccount(e.target.value)}>
            <option value="">Select account...</option>
            {accounts.map(a => <option key={a.id} value={a.id}>{a.name} ({a.account_no_masked})</option>)}
          </Select>
          <Btn onClick={autoMatch} disabled={loading || !selectedAccount}>{loading ? "Matching..." : "Auto-Match"}</Btn>
        </div>
      </Card>

      {summary && (
        <div className="grid grid-cols-3 gap-4">
          {[["Total Lines", summary.total_lines], ["Matched", summary.matched], ["Unmatched", summary.unmatched]].map(([label, val]) => (
            <Card key={label}><p className="text-xs text-zinc-400 mb-1">{label}</p><p className={`text-xl font-bold ${label === "Unmatched" && val > 0 ? "text-red-400" : label === "Matched" ? "text-emerald-400" : "text-white"}`}>{val}</p></Card>
          ))}
        </div>
      )}

      {/* Import section */}
      <Card>
        <p className="text-zinc-400 text-sm font-medium mb-2">Import Statement Lines (CSV: date,narration,debit,credit,reference)</p>
        <textarea className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono h-24 resize-none focus:outline-none focus:border-yellow-400" value={importLines} onChange={e => setImportLines(e.target.value)} placeholder="2024-06-01,NEFT CREDIT XYZ CO,0,50000,REF123&#10;2024-06-02,RTGS PAYMENT ABC,25000,0,PAY456" />
        <div className="mt-2"><Btn variant="secondary" onClick={importFeed} disabled={!selectedAccount || !importLines.trim()}>Import Lines</Btn></div>
      </Card>

      {reconResult && (
        <div className="space-y-4">
          <Card className="border-emerald-800/40">
            <p className="text-emerald-400 font-semibold mb-3">Auto-Match Results — {reconResult.matched_count} matched</p>
            {reconResult.matched?.slice(0, 10).map((m, i) => (
              <div key={i} className="flex justify-between text-xs py-1 border-b border-zinc-800">
                <span className="text-zinc-300">{m.statement_line.txn_date} · {m.statement_line.narration}</span>
                <span className="text-emerald-400">{fmt(m.matched_pdc?.amount)} — PDC {m.matched_pdc?.pdc_no}</span>
              </div>
            ))}
          </Card>
          {reconResult.unmatched_stmt?.length > 0 && (
            <Card className="border-amber-800/40">
              <p className="text-amber-400 font-semibold mb-3">Unmatched Statement Lines ({reconResult.unmatched_statement_lines})</p>
              {reconResult.unmatched_stmt?.slice(0, 10).map((l, i) => (
                <div key={i} className="flex justify-between text-xs py-1 border-b border-zinc-800">
                  <span className="text-zinc-300">{l.txn_date} · {l.narration}</span>
                  <span className="text-amber-400">{l.credit > 0 ? `+${fmt(l.credit)}` : `-${fmt(l.debit)}`}</span>
                </div>
              ))}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Overdue Interest
// ════════════════════════════════════════════
function OverdueInterestTab() {
  const [rules, setRules] = useState([]);
  const [form, setForm] = useState({ as_of_date: new Date().toISOString().slice(0, 10), rule_id: "", party_id: "", create_debit_notes: false });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [ruleForm, setRuleForm] = useState({ name: "", rate_pct_pa: "", grace_days: "7", basis: "simple", min_amount: "0" });

  const loadRules = () => api.get("/banking-pdc/interest-rules").then(r => setRules(r.data)).catch(() => {});
  useEffect(() => { loadRules(); }, []);

  const run = async () => {
    setLoading(true);
    try {
      const payload = { ...form, create_debit_notes: form.create_debit_notes };
      if (!payload.rule_id) delete payload.rule_id;
      if (!payload.party_id) delete payload.party_id;
      const { data } = await api.post("/banking-pdc/interest/run", payload);
      setResult(data);
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
    finally { setLoading(false); }
  };

  const saveRule = async () => {
    try {
      await api.post("/banking-pdc/interest-rules", { ...ruleForm, rate_pct_pa: parseFloat(ruleForm.rate_pct_pa) || 0, grace_days: parseInt(ruleForm.grace_days) || 0, min_amount: parseFloat(ruleForm.min_amount) || 0 });
      setShowRuleForm(false); loadRules();
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Overdue Interest" action={<Btn variant="secondary" onClick={() => setShowRuleForm(true)}>+ Add Rule</Btn>} />

      {/* Rules */}
      <Card>
        <p className="text-zinc-400 text-sm font-medium mb-3">Interest Rules</p>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-500 border-b border-zinc-800"><th className="text-left pb-1">Name</th><th className="text-right pb-1">Rate</th><th className="text-right pb-1">Grace Days</th><th className="text-left pb-1">Basis</th></tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {rules.map(r => (
              <tr key={r.id}>
                <td className="py-2 text-white">{r.name}</td>
                <td className="py-2 text-right text-yellow-400">{r.rate_pct_pa}% pa</td>
                <td className="py-2 text-right text-zinc-300">{r.grace_days} days</td>
                <td className="py-2 text-zinc-400 capitalize">{r.basis}</td>
              </tr>
            ))}
            {rules.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-zinc-500">No interest rules</td></tr>}
          </tbody>
        </table>
      </Card>

      {/* Run */}
      <Card>
        <p className="text-zinc-400 text-sm font-medium mb-3">Run Overdue Interest Computation</p>
        <div className="grid grid-cols-3 gap-3 items-end">
          <Input label="As of Date" type="date" value={form.as_of_date} onChange={e => setForm(f => ({ ...f, as_of_date: e.target.value }))} />
          <Select label="Interest Rule" value={form.rule_id} onChange={e => setForm(f => ({ ...f, rule_id: e.target.value }))}>
            <option value="">Use global rule</option>
            {rules.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <Input label="Party ID (optional)" value={form.party_id} onChange={e => setForm(f => ({ ...f, party_id: e.target.value }))} />
        </div>
        <div className="mt-3 flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
            <input type="checkbox" checked={form.create_debit_notes} onChange={e => setForm(f => ({ ...f, create_debit_notes: e.target.checked }))} className="rounded" />
            Create debit notes for applicable interest
          </label>
          <Btn onClick={run} disabled={loading}>{loading ? "Computing..." : "Run Interest"}</Btn>
        </div>
      </Card>

      {result && (
        <Card>
          <div className="flex justify-between items-center mb-4">
            <div>
              <p className="text-white font-semibold">Interest Run — {result.as_of_date}</p>
              <p className="text-zinc-400 text-sm">Rule: {result.rule} · {result.invoices_checked} invoices checked · {result.interest_applicable} applicable</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-zinc-400">Total Interest</p>
              <p className="text-2xl font-bold text-amber-400">{fmt(result.total_interest)}</p>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="text-zinc-400 border-b border-zinc-800">
              <th className="text-left py-2 pr-3">Invoice</th><th className="text-right py-2 pr-3">Amount</th><th className="text-left py-2 pr-3">Due Date</th>
              <th className="text-right py-2 pr-3">Overdue Days</th><th className="text-right py-2">Interest</th>
            </tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {result.results?.map((r, i) => (
                <tr key={i}>
                  <td className="py-2 pr-3 text-yellow-400 font-mono">{r.invoice_no || r.invoice_id}</td>
                  <td className="py-2 pr-3 text-right">{fmt(r.invoice_amount)}</td>
                  <td className="py-2 pr-3 text-zinc-400">{r.due_date}</td>
                  <td className="py-2 pr-3 text-right text-red-400">{r.overdue_days}</td>
                  <td className="py-2 text-right text-amber-400 font-semibold">{fmt(r.interest)}</td>
                </tr>
              ))}
              {!result.results?.length && <tr><td colSpan={5} className="py-4 text-center text-zinc-500">No overdue invoices found</td></tr>}
            </tbody>
          </table>
        </Card>
      )}

      {showRuleForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-white font-semibold">New Interest Rule</h3>
            <Input label="Rule Name" value={ruleForm.name} onChange={e => setRuleForm(f => ({ ...f, name: e.target.value }))} />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Rate % per annum" inputMode="decimal" value={ruleForm.rate_pct_pa} onChange={e => setRuleForm(f => ({ ...f, rate_pct_pa: e.target.value }))} />
              <Input label="Grace Days" inputMode="numeric" value={ruleForm.grace_days} onChange={e => setRuleForm(f => ({ ...f, grace_days: e.target.value }))} />
              <Select label="Basis" value={ruleForm.basis} onChange={e => setRuleForm(f => ({ ...f, basis: e.target.value }))}>
                <option value="simple">Simple Interest</option>
                <option value="compound">Compound (Daily)</option>
              </Select>
              <Input label="Min Invoice Amount" inputMode="decimal" value={ruleForm.min_amount} onChange={e => setRuleForm(f => ({ ...f, min_amount: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setShowRuleForm(false)}>Cancel</Btn>
              <Btn onClick={saveRule}>Save Rule</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Main
// ════════════════════════════════════════════
export default function Banking() {
  const [activeTab, setActiveTab] = useState(0);

  const tabs = [
    <PDCRegisterTab key="pdc" />,
    <MaturityTab key="mat" />,
    <ChequePrintTab key="chq" />,
    <BankReconTab key="recon" />,
    <OverdueInterestTab key="int" />,
  ];

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Banking</h1>
          <p className="text-zinc-400 text-sm mt-1">PDC management · Cheque printing (Indian amount-in-words) · Bank reconciliation · Overdue interest</p>
        </div>
        <div className="flex gap-1 mb-6 bg-zinc-900 border border-zinc-800 rounded-xl p-1 flex-wrap">
          {TABS.map((tab, i) => (
            <button key={tab} onClick={() => setActiveTab(i)} className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === i ? "bg-yellow-400 text-zinc-950" : "text-zinc-400 hover:text-white"}`}>{tab}</button>
          ))}
        </div>
        {tabs[activeTab]}
      </div>
    </div>
  );
}
