import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Plus, X, Trash2, RefreshCw, AlertTriangle } from "lucide-react";

const blankLine = () => ({ stock_item_id: "", qty: 1 });
const blank = () => ({ from_godown_id: "", to_godown_id: "", transfer_date: "", remarks: "", lines: [blankLine()] });

// Normalize paginated ({items:[]}) or bare-array API responses.
const toArray = (d) => (Array.isArray(d) ? d : d?.items ?? []);

export default function StockTransfers() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [godowns, setGodowns] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [it, gd, tr] = await Promise.all([
        api.get("/inventory/v2/items"),
        api.get("/inventory/v2/godowns"),
        api.get("/inventory/v2/transfers"),
      ]);
      setItems(toArray(it.data));
      setGodowns(toArray(gd.data));
      setTransfers(toArray(tr.data));
    } catch (e) {
      const detail = formatApiErrorDetail(e.response?.data?.detail) || e.message;
      const status = e.response?.status;
      console.error("[StockTransfers] load failed:", status, detail, e);
      setLoadError(status ? `Error ${status}: ${detail}` : detail);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const itemName = (id) => items.find((i) => i.id === id)?.name || id;
  const godownName = (id) => godowns.find((g) => g.id === id)?.name || id;

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (form.from_godown_id === form.to_godown_id)
      return toast.error("Source and destination warehouses must differ.");
    const payload = {
      ...form,
      transfer_date: form.transfer_date || null,
      lines: form.lines
        .filter((l) => l.stock_item_id && parseFloat(l.qty) > 0)
        .map((l) => ({ stock_item_id: l.stock_item_id, qty: parseFloat(l.qty) })),
    };
    if (payload.lines.length === 0) return toast.error("Add at least one line with a qty.");
    if (saving) return;
    setSaving(true);
    try {
      await api.post("/inventory/v2/transfers", payload);
      toast.success("Transfer posted");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="stock-transfers-page">
      <PageHeader
        eyebrow="Inventory"
        title="Stock Transfers"
        description="Move stock between warehouses. Posts paired outward/inward stock-ledger entries."
        actions={
          <PrimaryButton testid="new-transfer" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank()); setOpen(true); }}>
            New transfer
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {loading ? (
        <div className="flex items-center justify-center py-16" data-testid="transfers-loading">
          <div className="w-7 h-7 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : loadError ? (
        <div
          data-testid="transfers-error"
          className="border border-red-800/60 bg-red-950/30 rounded-lg p-6 flex flex-col items-center text-center gap-3"
        >
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div className="font-semibold text-red-200">Couldn't load stock transfers</div>
          <div className="text-sm text-red-300/90 font-mono max-w-lg break-words">{loadError}</div>
          <SecondaryButton onClick={load} icon={RefreshCw}>Retry</SecondaryButton>
        </div>
      ) : transfers.length === 0 ? (
        <EmptyState message="No stock transfers yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Number</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">From</th>
                <th className="px-3 py-2.5">To</th>
                <th className="px-3 py-2.5 text-right">Lines</th>
              </tr>
            </thead>
            <tbody>
              {transfers.map((t) => (
                <tr key={t.id} data-testid={`transfer-row-${t.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{t.transfer_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{t.transfer_date}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{godownName(t.from_godown_id)}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{godownName(t.to_godown_id)}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{(t.lines || []).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New Stock Transfer" size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-transfer" disabled={!online || saving}>{saving ? "Saving…" : "Post Transfer"}</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="From Warehouse" required>
              <Select required value={form.from_godown_id} data-testid="transfer-from"
                onChange={(e) => setForm({ ...form, from_godown_id: e.target.value })}>
                <option value="">— Select —</option>
                {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="To Warehouse" required>
              <Select required value={form.to_godown_id} data-testid="transfer-to"
                onChange={(e) => setForm({ ...form, to_godown_id: e.target.value })}>
                <option value="">— Select —</option>
                {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="Transfer Date">
              <Input type="date" value={form.transfer_date}
                onChange={(e) => setForm({ ...form, transfer_date: e.target.value })} />
            </Field>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="label-overline">Lines</div>
              <SecondaryButton icon={Plus} onClick={addLine}>Add line</SecondaryButton>
            </div>
            <div className="space-y-2">
              {form.lines.map((l, idx) => (
                <div key={idx} className="flex gap-2 items-end">
                  <div className="flex-1">
                    <Select value={l.stock_item_id} onChange={(e) => setLine(idx, { stock_item_id: e.target.value })}>
                      <option value="">— Select item —</option>
                      {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                    </Select>
                  </div>
                  <div className="w-32">
                    <Input type="text" inputMode="decimal" step="0.0001" min="0" value={l.qty} placeholder="Qty"
                      onChange={(e) => setLine(idx, { qty: e.target.value })} />
                  </div>
                  <button type="button" onClick={() => removeLine(idx)}
                    className="w-9 h-9 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center mb-0.5">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <Field label="Remarks">
            <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
