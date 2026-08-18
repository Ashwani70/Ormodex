import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { Plus, X, Trash2, RefreshCw, AlertTriangle, Eye, Pencil } from "lucide-react";

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
  const [editId, setEditId] = useState(null);
  const [viewTransfer, setViewTransfer] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
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

  const handleEdit = (transfer) => {
    setEditId(transfer.id);
    setForm({
      from_godown_id: transfer.from_godown_id || "",
      to_godown_id: transfer.to_godown_id || "",
      transfer_date: transfer.transfer_date || "",
      remarks: transfer.remarks || "",
      lines: (transfer.lines && transfer.lines.length > 0)
        ? transfer.lines.map((l) => ({
            stock_item_id: l.stock_item_id || l.product_id || "",
            qty: l.qty ?? 1,
            batch_id: l.batch_id || "",
            serial_id: l.serial_id || "",
          }))
        : [blankLine()],
    });
    setOpen(true);
  };

  const handleDelete = async () => {
    if (!deleteConfirm?.id) return;
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    setDeleting(true);
    try {
      await api.delete(`/inventory/v2/transfers/${deleteConfirm.id}`);
      toast.success("Transfer deleted successfully");
      setDeleteConfirm(null);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to delete transfer");
    } finally {
      setDeleting(false);
    }
  };

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
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
      if (editId) {
        await api.put(`/inventory/v2/transfers/${editId}`, payload);
        toast.success("Transfer updated");
      } else {
        await api.post("/inventory/v2/transfers", payload);
        toast.success("Transfer posted");
      }
      setOpen(false);
      setEditId(null);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab data entry (see useEnterNavigation): Enter/Tab moves through
  // From/To/Date, each line's item+qty, and Remarks; Ctrl+Enter/Ctrl+S/Alt+S
  // posts the transfer; Escape cancels. Auto-focuses From Warehouse on open.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

  return (
    <div data-testid="stock-transfers-page">
      <PageHeader
        eyebrow="Inventory"
        title="Stock Transfers"
        description="Move stock between warehouses. Posts paired outward/inward stock-ledger entries."
        actions={
          <PrimaryButton testid="new-transfer" icon={Plus} disabled={!online}
            onClick={() => { setEditId(null); setForm(blank()); setOpen(true); }}>
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
                <th className="px-3 py-2.5 text-right">Actions</th>
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
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        title="View transfer details"
                        aria-label="View transfer details"
                        onClick={() => setViewTransfer(t)}
                        className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        title="Edit transfer"
                        aria-label="Edit transfer"
                        disabled={!online}
                        onClick={() => handleEdit(t)}
                        className="p-1.5 text-muted-foreground hover:text-primary hover:bg-muted rounded transition-colors disabled:opacity-40"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        title="Delete transfer"
                        aria-label="Delete transfer"
                        disabled={!online}
                        onClick={() => setDeleteConfirm(t)}
                        className="p-1.5 text-muted-foreground hover:text-red-400 hover:bg-muted rounded transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* New / Edit Transfer Modal */}
      <Modal open={open} onClose={() => setOpen(false)} title={editId ? "Edit Stock Transfer" : "New Stock Transfer"} size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-transfer" disabled={!online || saving}>
              {saving ? "Saving…" : (editId ? "Update Transfer" : "Post Transfer")}
            </PrimaryButton>
          </>
        }>
        <form ref={formRef} onSubmit={submit} className="space-y-4">
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

      {/* Seen / View Transfer Modal */}
      <Modal
        open={Boolean(viewTransfer)}
        onClose={() => setViewTransfer(null)}
        title={`Stock Transfer Details — ${viewTransfer?.transfer_number || ""}`}
        size="lg"
        footer={
          <div className="flex items-center justify-between w-full">
            <div className="flex gap-2">
              <SecondaryButton
                icon={Pencil}
                disabled={!online}
                onClick={() => {
                  const t = viewTransfer;
                  setViewTransfer(null);
                  handleEdit(t);
                }}
              >
                Edit Transfer
              </SecondaryButton>
              <SecondaryButton
                icon={Trash2}
                disabled={!online}
                className="text-red-400 border-red-800/60 hover:bg-red-950/40"
                onClick={() => {
                  const t = viewTransfer;
                  setViewTransfer(null);
                  setDeleteConfirm(t);
                }}
              >
                Delete
              </SecondaryButton>
            </div>
            <SecondaryButton onClick={() => setViewTransfer(null)}>Close</SecondaryButton>
          </div>
        }
      >
        {viewTransfer && (
          <div className="space-y-4 text-sm font-mono">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-3 bg-muted/30 rounded-md border border-border">
              <div>
                <div className="text-xs text-muted-foreground label-overline">Transfer No</div>
                <div className="font-semibold text-foreground">{viewTransfer.transfer_number}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground label-overline">Date</div>
                <div>{viewTransfer.transfer_date || "—"}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground label-overline">From Warehouse</div>
                <div className="font-medium text-foreground">{godownName(viewTransfer.from_godown_id)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground label-overline">To Warehouse</div>
                <div className="font-medium text-foreground">{godownName(viewTransfer.to_godown_id)}</div>
              </div>
            </div>

            {viewTransfer.remarks && (
              <div>
                <div className="text-xs text-muted-foreground label-overline mb-1">Remarks</div>
                <div className="p-2.5 bg-card border border-border rounded text-foreground text-xs">
                  {viewTransfer.remarks}
                </div>
              </div>
            )}

            <div>
              <div className="text-xs text-muted-foreground label-overline mb-2">Transferred Items</div>
              <div className="border border-border rounded overflow-hidden">
                <table className="w-full text-sm text-left">
                  <thead className="bg-muted text-muted-foreground border-b border-border">
                    <tr>
                      <th className="px-3 py-2 w-12 text-center">#</th>
                      <th className="px-3 py-2">Stock Item</th>
                      <th className="px-3 py-2 text-right">Quantity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(viewTransfer.lines || []).map((line, idx) => (
                      <tr key={idx} className="border-b border-border last:border-0 hover:bg-muted/20">
                        <td className="px-3 py-2 text-center text-muted-foreground">{idx + 1}</td>
                        <td className="px-3 py-2 font-medium text-foreground">
                          {itemName(line.stock_item_id || line.product_id)}
                        </td>
                        <td className="px-3 py-2 text-right font-semibold text-foreground">
                          {line.qty}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        open={Boolean(deleteConfirm)}
        onClose={() => setDeleteConfirm(null)}
        title="Delete Stock Transfer"
        size="sm"
        footer={
          <>
            <SecondaryButton onClick={() => setDeleteConfirm(null)}>Cancel</SecondaryButton>
            <PrimaryButton
              onClick={handleDelete}
              disabled={deleting || !online}
              className="bg-red-600 hover:bg-red-700 text-white border-none"
            >
              {deleting ? "Deleting…" : "Delete Transfer"}
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-3 text-red-400">
            <AlertTriangle className="w-6 h-6 shrink-0" />
            <span className="font-semibold text-foreground">Confirm Deletion</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete stock transfer{" "}
            <strong className="text-foreground font-mono">{deleteConfirm?.transfer_number}</strong>?
          </p>
          <p className="text-xs text-red-400/90 bg-red-950/30 p-2.5 rounded border border-red-800/40">
            This will permanently revert the outward and inward stock ledger entries and remove this transfer from stock records.
          </p>
        </div>
      </Modal>
    </div>
  );
}

