import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const fmt = (v) => Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const uuid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : "uuid-" + Date.now() + "-" + Math.random().toString(16).slice(2));

const QUEUE_KEY = "gew_pos_offline_queue";

// ── offline queue helpers ──
const loadQueue = () => { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]"); } catch { return []; } };
const saveQueue = (q) => localStorage.setItem(QUEUE_KEY, JSON.stringify(q));

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

// ══════════════════════════════════════════════════════════════
// Session open / close
// ══════════════════════════════════════════════════════════════
function SessionGate({ session, setSession }) {
  const [terminal, setTerminal] = useState("COUNTER-1");
  const [openingCash, setOpeningCash] = useState("2000");
  const [countedCash, setCountedCash] = useState("");
  const [summary, setSummary] = useState(null);

  const open = async () => {
    try {
      const { data } = await api.post("/pos/sessions", { terminal, opening_cash: Number(openingCash || 0) });
      setSession(data);
      toast.success(`Session ${data.session_no} open`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Open failed"); }
  };

  const loadSummary = useCallback(async () => {
    if (!session) return;
    try { setSummary((await api.get(`/pos/sessions/${session.id}/summary`)).data); } catch {}
  }, [session]);
  useEffect(() => { loadSummary(); }, [loadSummary]);

  const close = async () => {
    if (countedCash === "") return toast.error("Count the drawer first");
    try {
      const { data } = await api.post(`/pos/sessions/${session.id}/close`, { counted_cash: Number(countedCash) });
      const r = data.reconciliation;
      toast[r.status === "balanced" ? "success" : "warning"](
        `Drawer ${r.status} · variance ₹${fmt(r.variance)}`);
      setSession(null);
    } catch (e) { toast.error(e?.response?.data?.detail || "Close failed"); }
  };

  if (!session) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="bg-zinc-900 border border-zinc-800 p-8 w-full max-w-sm" style={{ borderRadius: "var(--radius)" }}>
          <h1 className="font-display font-black text-xl text-zinc-50 mb-1">Open POS Session</h1>
          <p className="text-zinc-500 text-sm mb-5">Start a billing session for this terminal.</p>
          <label className="block mb-3">
            <span className="block text-xs font-mono uppercase text-zinc-500 mb-1">Terminal</span>
            <input value={terminal} onChange={(e) => setTerminal(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-zinc-100" />
          </label>
          <label className="block mb-5">
            <span className="block text-xs font-mono uppercase text-zinc-500 mb-1">Opening Cash</span>
            <input type="number" value={openingCash} onChange={(e) => setOpeningCash(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-zinc-100" />
          </label>
          <Btn onClick={open} className="w-full">Open Session</Btn>
        </div>
      </div>
    );
  }

  // close panel (rendered alongside counter via the parent; here it's the footer bar)
  return (
    <div className="flex items-center gap-3">
      {summary && (
        <span className="text-xs font-mono text-zinc-500">
          expected ₹{fmt(summary.expected_cash)} · {summary.sales_count} sales
        </span>
      )}
      <input type="number" placeholder="counted cash" value={countedCash} onChange={(e) => setCountedCash(e.target.value)}
        className="w-32 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" />
      <Btn variant="danger" onClick={close}>Close Session</Btn>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Billing counter
// ══════════════════════════════════════════════════════════════
function Counter({ session, online, queue, setQueue }) {
  const [scan, setScan] = useState("");
  const [cart, setCart] = useState([]);
  const [tender, setTender] = useState({ cash: "", card: "", upi: "" });
  const scanRef = useRef(null);

  useEffect(() => { scanRef.current?.focus(); }, [cart]);

  // demo: resolve scanned code to a product via inventory. Fallback to a quick line.
  const addItem = async (code) => {
    if (!code) return;
    try {
      const { data } = await api.get("/products", { params: { q: code } });
      const prod = (Array.isArray(data) ? data : data.items || []).find(
        (p) => p.sku === code || p.id === code) || (Array.isArray(data) ? data[0] : null);
      if (prod) {
        upsertCart({ item_id: prod.id, name: prod.name, unit_price: prod.selling_price || 0,
                     gst_rate: prod.gst_rate ?? 18, hsn_code: prod.hsn_code, qty: 1 });
      } else {
        toast.error(`No product for '${code}'`);
      }
    } catch {
      toast.error("Lookup failed (offline?) — add manually");
    }
    setScan("");
  };

  const upsertCart = (line) => {
    setCart((c) => {
      const i = c.findIndex((x) => x.item_id === line.item_id);
      if (i >= 0) {
        const next = [...c]; next[i] = { ...next[i], qty: next[i].qty + line.qty }; return next;
      }
      return [...c, line];
    });
  };

  const setQty = (idx, qty) => setCart((c) => c.map((x, i) => i === idx ? { ...x, qty: Math.max(0, qty) } : x).filter((x) => x.qty > 0));

  const totals = cart.reduce((acc, l) => {
    const taxable = l.qty * l.unit_price;
    const gst = taxable * (l.gst_rate || 0) / 100;
    acc.taxable += taxable; acc.gst += gst; return acc;
  }, { taxable: 0, gst: 0 });
  const grand = Math.round((totals.taxable + totals.gst) * 100) / 100;
  const tendered = Number(tender.cash || 0) + Number(tender.card || 0) + Number(tender.upi || 0);
  const change = Math.max(0, tendered - grand);

  const checkout = async () => {
    if (cart.length === 0) return toast.error("Cart empty");
    if (tendered + 0.01 < grand) return toast.error("Insufficient tender");

    const sale = {
      client_uuid: uuid(),
      session_id: session.id,
      lines: cart.map((l) => ({ item_id: l.item_id, name: l.name, qty: l.qty,
        unit_price: l.unit_price, gst_rate: l.gst_rate, hsn_code: l.hsn_code })),
      payment: { cash: Number(tender.cash || 0), card: Number(tender.card || 0), upi: Number(tender.upi || 0) },
      is_interstate: false,
      created_at_client: new Date().toISOString(),
    };

    if (!online) {
      const q = [...queue, sale];
      setQueue(q); saveQueue(q);
      toast.warning("Offline — sale queued, will sync on reconnect");
      resetSale();
      return;
    }

    try {
      const { data } = await api.post("/pos/sales", sale);
      toast.success(`Receipt ${data.sale.receipt_no} · change ₹${fmt(data.sale.change)}`);
      if (data.receipt) printReceipt(data.receipt);
      resetSale();
    } catch (e) {
      // network blip mid-online → queue it (idempotent client_uuid keeps it safe)
      const q = [...queue, sale];
      setQueue(q); saveQueue(q);
      toast.warning("Post failed — queued for retry");
      resetSale();
    }
  };

  const resetSale = () => { setCart([]); setTender({ cash: "", card: "", upi: "" }); scanRef.current?.focus(); };

  return (
    <div className="grid grid-cols-3 gap-4 h-full">
      {/* Left: scan + cart */}
      <div className="col-span-2 flex flex-col">
        <form onSubmit={(e) => { e.preventDefault(); addItem(scan.trim()); }} className="mb-3">
          <input ref={scanRef} autoFocus value={scan} onChange={(e) => setScan(e.target.value)}
            placeholder="Scan barcode / SKU and press Enter…"
            className="w-full bg-zinc-950 border-2 border-yellow-400/40 focus:border-yellow-400 px-4 py-3 text-lg text-zinc-100 font-mono focus:outline-none"
            style={{ borderRadius: "var(--radius)" }} />
        </form>
        <div className="flex-1 overflow-y-auto bg-zinc-900 border border-zinc-800" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800 sticky top-0 bg-zinc-900">
              <th className="py-2 px-3">Item</th><th className="text-right">Rate</th>
              <th className="text-center">Qty</th><th className="text-right">GST%</th><th className="text-right px-3">Amount</th>
            </tr></thead>
            <tbody>
              {cart.map((l, i) => (
                <tr key={i} className="border-b border-zinc-900">
                  <td className="py-2 px-3 text-zinc-200">{l.name || l.item_id}</td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt(l.unit_price)}</td>
                  <td className="text-center">
                    <input type="number" value={l.qty} onChange={(e) => setQty(i, Number(e.target.value))}
                      className="w-16 bg-zinc-950 border border-zinc-800 px-2 py-1 text-center text-zinc-100" />
                  </td>
                  <td className="text-right font-mono text-zinc-500">{l.gst_rate}%</td>
                  <td className="text-right px-3 font-mono text-zinc-100">₹{fmt(l.qty * l.unit_price)}</td>
                </tr>
              ))}
              {cart.length === 0 && <tr><td colSpan={5} className="py-12 text-center text-zinc-600">Scan to begin…</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: tender */}
      <div className="bg-zinc-900 border border-zinc-800 p-5 flex flex-col" style={{ borderRadius: "var(--radius)" }}>
        <div className="space-y-1 mb-4">
          <Line label="Taxable" value={totals.taxable} />
          <Line label="GST" value={totals.gst} />
          <div className="border-t border-zinc-700 pt-2 mt-2">
            <div className="flex justify-between items-center">
              <span className="font-display font-black text-zinc-100">TOTAL</span>
              <span className="font-display font-black text-2xl text-yellow-400">₹{fmt(grand)}</span>
            </div>
          </div>
        </div>
        <div className="space-y-2 mb-4">
          {["cash", "card", "upi"].map((m) => (
            <label key={m} className="flex items-center gap-2">
              <span className="w-12 text-xs font-mono uppercase text-zinc-500">{m}</span>
              <input type="number" value={tender[m]} onChange={(e) => setTender({ ...tender, [m]: e.target.value })}
                className="flex-1 bg-zinc-950 border border-zinc-800 px-3 py-2 text-zinc-100" />
            </label>
          ))}
          <button onClick={() => setTender({ ...tender, cash: String(grand) })}
            className="text-xs font-mono text-yellow-400 hover:text-yellow-300">exact cash →</button>
        </div>
        <div className="flex justify-between text-sm mb-4">
          <span className="text-zinc-400">Tendered ₹{fmt(tendered)}</span>
          <span className="text-emerald-400 font-mono">Change ₹{fmt(change)}</span>
        </div>
        <Btn onClick={checkout} className="w-full text-base py-3" disabled={cart.length === 0}>Checkout (₹{fmt(grand)})</Btn>
      </div>
    </div>
  );
}

const Line = ({ label, value }) => (
  <div className="flex justify-between text-sm">
    <span className="text-zinc-400">{label}</span>
    <span className="font-mono text-zinc-200">₹{fmt(value)}</span>
  </div>
);

// ── thermal receipt to a print window ──
function printReceipt(r) {
  const gstRows = (r.gst_breakup || [])
    .map((b) => `  ${b.rate}%  CGST ${fmt(b.cgst)}  SGST ${fmt(b.sgst)}  IGST ${fmt(b.igst)}`).join("\n");
  const lines = r.lines.map((l) =>
    `${(l.name || "").slice(0, 18).padEnd(18)} ${String(l.qty).padStart(3)} x ${fmt(l.rate).padStart(8)} = ${fmt(l.amount).padStart(9)}`).join("\n");
  const text =
`        TAX INVOICE
   Receipt: ${r.receipt_no}
   ${r.date}   ${r.terminal}
   Cashier: ${r.cashier || "-"}
----------------------------------------
${lines}
----------------------------------------
   Taxable:            ₹${fmt(r.taxable_value)}
${gstRows}
   CGST ₹${fmt(r.cgst)}  SGST ₹${fmt(r.sgst)}  IGST ₹${fmt(r.igst)}
========================================
   TOTAL:              ₹${fmt(r.grand_total)}
   ${r.amount_in_words}
----------------------------------------
   Cash ₹${fmt(r.payment.cash)}  Card ₹${fmt(r.payment.card)}  UPI ₹${fmt(r.payment.upi)}
   Change: ₹${fmt(r.change)}
========================================
   ${r.footer}
`;
  const w = window.open("", "receipt", "width=320,height=600");
  if (w) {
    w.document.write(`<pre style="font:12px monospace;white-space:pre">${text.replace(/</g, "&lt;")}</pre>`);
    w.document.close();
    w.print();
  }
}

// ══════════════════════════════════════════════════════════════
// Shell — wires online/offline + sync
// ══════════════════════════════════════════════════════════════
export default function POS() {
  const [session, setSession] = useState(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [queue, setQueue] = useState(loadQueue());

  const syncQueue = useCallback(async () => {
    const q = loadQueue();
    if (q.length === 0) return;
    try {
      const { data } = await api.post("/pos/sales/sync", q);
      // posted + duplicates are both safely done → clear queue
      saveQueue([]); setQueue([]);
      toast.success(`Synced ${data.posted} sale(s), ${data.duplicates} already posted`);
    } catch {
      toast.error("Sync failed — will retry");
    }
  }, []);

  useEffect(() => {
    const goOnline = () => { setOnline(true); syncQueue(); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    if (navigator.onLine) syncQueue();   // sync any leftover queue on mount
    return () => { window.removeEventListener("online", goOnline); window.removeEventListener("offline", goOffline); };
  }, [syncQueue]);

  return (
    <div className="fixed inset-0 bg-zinc-950 text-zinc-100 flex flex-col">
      <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <span className="font-display font-black text-lg text-zinc-50">POS</span>
          {session && <span className="font-mono text-xs text-zinc-500">{session.session_no} · {session.terminal}</span>}
          <span className={`text-xs font-mono px-2 py-0.5 ${online ? "text-emerald-400" : "text-red-400 bg-red-500/10"}`}>
            {online ? "● online" : "○ OFFLINE"}
          </span>
          {queue.length > 0 && <span className="text-xs font-mono text-amber-400">{queue.length} queued</span>}
        </div>
        {session && <SessionGate session={session} setSession={setSession} />}
      </header>

      <main className="flex-1 p-4 overflow-hidden">
        {!session
          ? <SessionGate session={session} setSession={setSession} />
          : <Counter session={session} online={online} queue={queue} setQueue={setQueue} />}
      </main>
    </div>
  );
}
