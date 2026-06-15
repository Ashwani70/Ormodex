import { useState, useEffect, useCallback } from "react";
import portalApi, { setPortalToken, getPortalToken } from "@/lib/portalApi";
import { toast } from "sonner";

const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 ${className}`} style={{ borderRadius: "var(--radius)" }}>{children}</div>
);
const Btn = ({ children, onClick, variant = "primary", disabled, type = "button" }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`px-4 py-2 text-sm font-mono uppercase tracking-wider transition-colors disabled:opacity-40 ${styles[variant]}`}
      style={{ borderRadius: "var(--radius)" }}>{children}</button>
  );
};
const Input = (props) => (
  <input {...props}
    className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
    style={{ borderRadius: "var(--radius)" }} />
);
const StatusPill = ({ s }) => {
  const map = {
    PAID: "text-emerald-400", UNPAID: "text-red-400", PARTIAL: "text-amber-400",
    submitted: "text-amber-400", under_review: "text-blue-400", approved: "text-emerald-400",
    paid: "text-emerald-400", rejected: "text-red-400",
  };
  return <span className={`font-mono text-xs uppercase ${map[s] || "text-zinc-400"}`}>{s}</span>;
};

// ── Login ──
function PortalLogin({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await portalApi.post("/auth/login", { email, password });
      setPortalToken(data.token);
      onLogin(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <Card className="p-8 w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="font-display font-black text-2xl text-zinc-50">GravityOne</div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-yellow-400">Partner Portal</div>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <Btn type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign In"}</Btn>
        </form>
        <p className="text-zinc-600 text-xs mt-4 text-center">Customers & vendors only. Internal staff use the main app.</p>
      </Card>
    </div>
  );
}

// ── Customer dashboard ──
function CustomerDash({ session }) {
  const [invoices, setInvoices] = useState([]);
  const [statement, setStatement] = useState(null);
  const [tab, setTab] = useState("invoices");

  const load = useCallback(async () => {
    try {
      setInvoices((await portalApi.get("/invoices")).data);
      setStatement((await portalApi.get("/statement")).data);
    } catch { toast.error("Failed to load"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const pay = async (inv) => {
    try {
      const { data } = await portalApi.post(`/invoices/${inv.id}/pay`, { gateway: "mock" });
      // mock gateway: immediately fire the success callback
      const cb = await portalApi.post(`/pay/${data.payment_link_id}/callback`, {
        txn_ref: "MOCK-" + Date.now(), success: true,
      });
      toast.success(`Paid ₹${fmt(data.amount)} — receipt ${cb.data.receipt_voucher_id?.slice(0, 8)}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Payment failed"); }
  };

  const outstanding = invoices.reduce((s, i) => s + (i.outstanding || 0), 0);

  return (
    <div>
      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500">Total Outstanding</div>
          <div className="text-2xl font-display font-black text-red-400">₹{fmt(outstanding)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500">Open Invoices</div>
          <div className="text-2xl font-display font-black text-zinc-100">{invoices.filter((i) => i.status !== "PAID").length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500">Statement Balance</div>
          <div className="text-2xl font-display font-black text-yellow-400">₹{fmt(statement?.closing_balance)}</div>
        </Card>
      </div>

      <div className="flex gap-1 border-b border-zinc-800 mb-4">
        {["invoices", "statement"].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-mono uppercase tracking-wider border-b-2 -mb-px ${
              tab === t ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500"}`}>{t}</button>
        ))}
      </div>

      {tab === "invoices" && (
        <Card className="p-4">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Invoice</th><th>Status</th><th className="text-right">Total</th>
              <th className="text-right">Outstanding</th><th></th>
            </tr></thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-200 font-mono">{inv.invoice_number}</td>
                  <td><StatusPill s={inv.status} /></td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt(inv.total)}</td>
                  <td className="text-right font-mono text-zinc-100">₹{fmt(inv.outstanding)}</td>
                  <td className="text-right">
                    {inv.outstanding > 0 && <Btn onClick={() => pay(inv)}>Pay</Btn>}
                  </td>
                </tr>
              ))}
              {invoices.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-zinc-500">No invoices.</td></tr>}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "statement" && statement && (
        <Card className="p-4">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
              <th className="py-2">Date</th><th>Invoice</th><th className="text-right">Debit</th>
              <th className="text-right">Credit</th><th className="text-right">Balance</th>
            </tr></thead>
            <tbody>
              {statement.lines.map((l, i) => (
                <tr key={i} className="border-b border-zinc-900">
                  <td className="py-2 text-zinc-400">{l.date}</td>
                  <td className="text-zinc-200 font-mono">{l.invoice_no}</td>
                  <td className="text-right font-mono text-zinc-300">{l.debit ? `₹${fmt(l.debit)}` : ""}</td>
                  <td className="text-right font-mono text-emerald-400">{l.credit ? `₹${fmt(l.credit)}` : ""}</td>
                  <td className="text-right font-mono text-zinc-100">₹{fmt(l.running_balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Vendor dashboard ──
function VendorDash({ session }) {
  const [bills, setBills] = useState([]);
  const [form, setForm] = useState({ amount: "", bill_number: "", bill_date: "", description: "" });

  const load = useCallback(async () => {
    try { setBills((await portalApi.get("/bills")).data); }
    catch { toast.error("Failed to load bills"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!form.amount) return toast.error("Amount required");
    try {
      await portalApi.post("/bills", {
        amount: Number(form.amount), bill_number: form.bill_number || null,
        bill_date: form.bill_date || null, description: form.description || null,
      });
      toast.success("Bill submitted for review");
      setForm({ amount: "", bill_number: "", bill_date: "", description: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Submit failed"); }
  };

  return (
    <div>
      <Card className="p-5 mb-6">
        <h3 className="font-display font-bold text-zinc-50 mb-3">Submit a Bill</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Input placeholder="Amount" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <Input placeholder="Bill #" value={form.bill_number} onChange={(e) => setForm({ ...form, bill_number: e.target.value })} />
          <Input placeholder="Bill date" type="date" value={form.bill_date} onChange={(e) => setForm({ ...form, bill_date: e.target.value })} />
          <Input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-3"><Btn onClick={submit}>Submit Bill</Btn></div>
      </Card>

      <Card className="p-4">
        <h3 className="font-display font-bold text-zinc-50 mb-3">My Submissions</h3>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Submission</th><th>Bill #</th><th className="text-right">Amount</th><th>Status</th>
          </tr></thead>
          <tbody>
            {bills.map((b) => (
              <tr key={b.id} className="border-b border-zinc-900">
                <td className="py-2 text-zinc-200 font-mono">{b.submission_no}</td>
                <td className="text-zinc-400">{b.bill_number || "—"}</td>
                <td className="text-right font-mono text-zinc-100">₹{fmt(b.amount)}</td>
                <td><StatusPill s={b.status} /></td>
              </tr>
            ))}
            {bills.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-zinc-500">No submissions yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Portal shell ──
export default function Portal() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getPortalToken()) { setLoading(false); return; }
    portalApi.get("/auth/me")
      .then(({ data }) => setSession(data))
      .catch(() => setPortalToken(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    try { await portalApi.post("/auth/logout"); } catch {}
    setPortalToken(null);
    setSession(null);
  };

  if (loading) return <div className="min-h-screen bg-zinc-950" />;
  if (!session) return <PortalLogin onLogin={setSession} />;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div>
          <div className="font-display font-black text-lg text-zinc-50">GravityOne Portal</div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-yellow-400">
            {session.party_type} · {session.name || session.email}
          </div>
        </div>
        <Btn variant="ghost" onClick={logout}>Sign Out</Btn>
      </header>
      <main className="p-6 max-w-5xl mx-auto">
        {session.party_type === "customer" ? <CustomerDash session={session} /> : <VendorDash session={session} />}
      </main>
    </div>
  );
}
