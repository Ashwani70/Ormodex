import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 ${className}`} style={{ borderRadius: "var(--radius)" }}>{children}</div>
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
const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
    danger: "border border-red-700 text-red-400 hover:bg-red-500/10",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={`px-4 py-2 text-sm font-mono uppercase tracking-wider transition-colors disabled:opacity-40 ${styles[variant]} ${className}`}
      style={{ borderRadius: "var(--radius)" }}>{children}</button>
  );
};
const Input = ({ label, ...props }) => (
  <label className="block">
    {label && <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-1">{label}</span>}
    <input {...props}
      className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
      style={{ borderRadius: "var(--radius)" }} />
  </label>
);

// ══════════════════════════════════════════════════════════════
// Tally import wizard
// ══════════════════════════════════════════════════════════════
function TallyTab() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState(null);

  const runDry = async () => {
    if (!file) return toast.error("Choose a Tally XML file");
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post("/integration/import/tally-xml?dryRun=true", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(data.preview); setResult(null);
    } catch (e) { toast.error(e?.response?.data?.detail || "Preview failed"); }
  };

  const commit = async () => {
    const fd = new FormData(); fd.append("file", file);
    setCommitting(true);
    try {
      const { data } = await api.post("/integration/import/tally-xml?dryRun=false", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data); toast.success("Committed");
    } catch (e) { toast.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Commit failed"); }
    finally { setCommitting(false); }
  };

  return (
    <div>
      <SectionHeader title="Tally XML Import" subtitle="Upload → preview (dry-run) → commit with reconciliation" />
      <Card className="p-5 mb-5">
        <div className="flex items-end gap-3">
          <label className="flex-1">
            <span className="block text-xs font-mono uppercase text-zinc-500 mb-1">Tally XML file</span>
            <input type="file" accept=".xml" onChange={(e) => { setFile(e.target.files[0]); setPreview(null); setResult(null); }}
              className="block w-full text-sm text-zinc-400 file:mr-3 file:py-2 file:px-4 file:border-0 file:bg-zinc-800 file:text-zinc-200 file:font-mono file:text-xs file:uppercase" />
          </label>
          <Btn onClick={runDry}>Preview</Btn>
        </div>
      </Card>

      {preview && (
        <Card className="p-5 mb-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display font-bold text-zinc-50">Dry-Run Preview</h3>
            <span className={`text-xs font-mono px-2 py-1 ${preview.ready_to_commit ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"}`}>
              {preview.ready_to_commit ? "READY TO COMMIT" : "NOT READY"}
            </span>
          </div>
          <div className="grid grid-cols-3 md:grid-cols-5 gap-3 mb-4">
            {Object.entries(preview.summary).map(([k, v]) => (
              <div key={k} className="bg-zinc-950 border border-zinc-800 p-3 text-center">
                <div className="text-2xl font-display font-black text-zinc-100">{v}</div>
                <div className="text-[11px] font-mono uppercase text-zinc-500">{k}</div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-zinc-500">New ledgers:</span> <b className="text-emerald-400">{preview.ledgers_new}</b></div>
            <div><span className="text-zinc-500">Duplicate ledgers:</span> <b className="text-amber-400">{preview.ledgers_duplicate}</b></div>
          </div>
          {preview.unmapped_ledgers.length > 0 && (
            <div className="mt-3 bg-amber-500/10 border border-amber-700 p-3">
              <div className="text-xs font-mono uppercase text-amber-400 mb-1">Unmapped ledgers (defaulted to ASSET)</div>
              {preview.unmapped_ledgers.map((u, i) => (
                <div key={i} className="text-sm text-zinc-300">▸ {u.ledger} <span className="text-zinc-600">(group: {u.group})</span></div>
              ))}
            </div>
          )}
          {preview.unbalanced_vouchers.length > 0 && (
            <div className="mt-3 bg-red-500/10 border border-red-700 p-3">
              <div className="text-xs font-mono uppercase text-red-400 mb-1">Unbalanced vouchers</div>
              {preview.unbalanced_vouchers.map((v, i) => (
                <div key={i} className="text-sm text-zinc-300">▸ {v.number}: Dr {v.debit} ≠ Cr {v.credit}</div>
              ))}
            </div>
          )}
          <div className="mt-4">
            <Btn onClick={commit} disabled={!preview.ready_to_commit || committing}>
              {committing ? "Committing…" : "Commit Import"}
            </Btn>
          </div>
        </Card>
      )}

      {result && (
        <Card className="p-5">
          <h3 className="font-display font-bold text-emerald-400 mb-3">Committed ✓</h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>Ledgers: <b className="text-zinc-100">{result.committed.ledgers}</b></div>
            <div>Vouchers: <b className="text-zinc-100">{result.committed.vouchers}</b></div>
          </div>
          <div className="mt-3 bg-zinc-950 border-l-4 border-yellow-400 p-3 text-sm">
            <div className="text-xs font-mono uppercase text-yellow-400 mb-1">Reconciliation</div>
            <div>Ledgers reconciled: {result.reconciliation.ledgers_reconciled ? "✓" : "✗"}</div>
            <div>Vouchers reconciled: {result.reconciliation.vouchers_reconciled ? "✓" : "✗"}</div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Backups
// ══════════════════════════════════════════════════════════════
function BackupsTab() {
  const [backups, setBackups] = useState([]);
  const [label, setLabel] = useState("");

  const load = useCallback(async () => {
    try { setBackups((await api.get("/integration/backups")).data); } catch {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const { data } = await api.post("/integration/backups", { label: label || null });
      toast.success(`Backup ${data.total_docs} docs`); setLabel(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Backup failed"); }
  };

  const restore = async (id) => {
    if (!window.confirm("Restore overwrites current data. Continue?")) return;
    try {
      const { data } = await api.post("/integration/backups/restore", { backup_id: id, confirm: true });
      toast.success(`Restored ${Object.keys(data.restored).length} collections`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Restore failed"); }
  };

  return (
    <div>
      <SectionHeader title="Backups & Restore" subtitle="Logical snapshots; restore requires confirmation"
        right={<div className="flex gap-2"><Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="label (optional)" /><Btn onClick={create}>Backup Now</Btn></div>} />
      <Card className="p-4">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Label</th><th>Date</th><th className="text-right">Docs</th><th></th>
          </tr></thead>
          <tbody>
            {backups.map((b) => (
              <tr key={b.id} className="border-b border-zinc-900">
                <td className="py-2 text-zinc-200">{b.label}</td>
                <td className="text-zinc-500">{b.created_at?.slice(0, 16).replace("T", " ")}</td>
                <td className="text-right font-mono text-zinc-300">{b.total_docs}</td>
                <td className="text-right"><Btn variant="ghost" onClick={() => restore(b.id)}>Restore</Btn></td>
              </tr>
            ))}
            {backups.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-zinc-500">No backups yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// API keys & webhooks
// ══════════════════════════════════════════════════════════════
function ApiTab() {
  const [keys, setKeys] = useState([]);
  const [subs, setSubs] = useState([]);
  const [events, setEvents] = useState([]);
  const [keyForm, setKeyForm] = useState({ name: "", scopes: "" });
  const [subForm, setSubForm] = useState({ url: "", events: [] });
  const [newKey, setNewKey] = useState(null);

  const load = useCallback(async () => {
    try {
      setKeys((await api.get("/integration/api-keys")).data);
      setSubs((await api.get("/integration/webhooks/subscriptions")).data);
      setEvents((await api.get("/integration/webhooks/events")).data.events);
    } catch {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const createKey = async () => {
    if (!keyForm.name) return toast.error("Name required");
    try {
      const { data } = await api.post("/integration/api-keys", {
        name: keyForm.name, scopes: keyForm.scopes.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setNewKey(data.api_key); setKeyForm({ name: "", scopes: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const createSub = async () => {
    if (!subForm.url || subForm.events.length === 0) return toast.error("URL and ≥1 event required");
    try {
      await api.post("/integration/webhooks/subscriptions", subForm);
      toast.success("Subscription created"); setSubForm({ url: "", events: [] }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6">
      <div>
        <SectionHeader title="API Keys" subtitle="Scoped keys for the public /api/v1 surface" />
        {newKey && (
          <div className="bg-emerald-500/10 border border-emerald-700 p-3 mb-3">
            <div className="text-xs font-mono uppercase text-emerald-400 mb-1">New key (shown once — copy now)</div>
            <code className="text-emerald-300 text-sm break-all">{newKey}</code>
          </div>
        )}
        <Card className="p-4 mb-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
            <Input label="Key Name" value={keyForm.name} onChange={(e) => setKeyForm({ ...keyForm, name: e.target.value })} />
            <Input label="Scopes (csv)" value={keyForm.scopes} onChange={(e) => setKeyForm({ ...keyForm, scopes: e.target.value })} placeholder="invoices:read,products:read" />
            <Btn onClick={createKey}>Create Key</Btn>
          </div>
        </Card>
        <Card className="p-4">
          {keys.map((k) => (
            <div key={k.id} className="flex justify-between py-2 border-b border-zinc-900 text-sm">
              <span className="text-zinc-200">{k.name} <span className="text-zinc-600 font-mono">{k.key_prefix}…</span></span>
              <span className="text-zinc-500 font-mono text-xs">{(k.scopes || []).join(", ") || "no scopes"} {!k.active && "· revoked"}</span>
            </div>
          ))}
          {keys.length === 0 && <p className="text-zinc-500 text-sm text-center py-4">No API keys.</p>}
        </Card>
      </div>

      <div>
        <SectionHeader title="Webhook Subscriptions" subtitle="Signed payloads, retry with backoff" />
        <Card className="p-4 mb-3">
          <Input label="Endpoint URL" value={subForm.url} onChange={(e) => setSubForm({ ...subForm, url: e.target.value })} placeholder="https://example.com/webhook" />
          <div className="mt-3 flex flex-wrap gap-2">
            {events.map((ev) => (
              <button key={ev} onClick={() => setSubForm((s) => ({ ...s, events: s.events.includes(ev) ? s.events.filter((x) => x !== ev) : [...s.events, ev] }))}
                className={`text-xs font-mono px-2 py-1 border ${subForm.events.includes(ev) ? "border-yellow-400 text-yellow-400" : "border-zinc-800 text-zinc-500"}`}>
                {ev}
              </button>
            ))}
          </div>
          <div className="mt-3"><Btn onClick={createSub}>Subscribe</Btn></div>
        </Card>
        <Card className="p-4">
          {subs.map((s) => (
            <div key={s.id} className="flex justify-between py-2 border-b border-zinc-900 text-sm">
              <span className="text-zinc-200 break-all">{s.url}</span>
              <span className="text-zinc-500 font-mono text-xs">{(s.events || []).length} events {!s.active && "· off"}</span>
            </div>
          ))}
          {subs.length === 0 && <p className="text-zinc-500 text-sm text-center py-4">No subscriptions.</p>}
        </Card>
      </div>
    </div>
  );
}

const TABS = [
  { id: "tally", label: "Tally Import" },
  { id: "backups", label: "Backups" },
  { id: "api", label: "API & Webhooks" },
];

export default function Integration() {
  const [tab, setTab] = useState("tally");
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Data & Integration</h1>
        <p className="text-zinc-500 text-sm mt-1">Tally import, backups, public API keys, and webhooks.</p>
      </div>
      <div className="flex gap-1 border-b border-zinc-800 mb-6">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-mono uppercase tracking-wider border-b-2 -mb-px ${
              tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "tally" && <TallyTab />}
      {tab === "backups" && <BackupsTab />}
      {tab === "api" && <ApiTab />}
    </div>
  );
}
