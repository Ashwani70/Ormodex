import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Textarea, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Plus, Pencil, Trash2 } from "lucide-react";

const blank = { name: "", address: "", parent_godown_id: "" };

export default function Godowns() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/inventory/v2/godowns");
    setItems(r.data);
  };
  useEffect(() => { load(); }, []);

  const nameById = (id) => items.find((g) => g.id === id)?.name || "—";

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const payload = { ...form, parent_godown_id: form.parent_godown_id || null };
    try {
      if (editingId) await api.put(`/inventory/v2/godowns/${editingId}`, payload);
      else await api.post("/inventory/v2/godowns", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (!window.confirm(`Delete godown ${item.name}?`)) return;
    try {
      await api.delete(`/inventory/v2/godowns/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  return (
    <div data-testid="godowns-page">
      <PageHeader
        eyebrow="Inventory"
        title="Godowns"
        description="Storage locations. Godowns can be nested under a parent location."
        actions={
          <PrimaryButton testid="new-godown" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank); setEditingId(null); setOpen(true); }}>
            New godown
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {items.length === 0 ? (
        <EmptyState message="No godowns yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Parent</th>
                <th className="px-3 py-2.5">Address</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((g) => (
                <tr key={g.id} data-testid={`godown-row-${g.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{g.name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.parent_godown_id ? nameById(g.parent_godown_id) : "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.address || "—"}</td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => { setForm({ ...blank, ...g, parent_godown_id: g.parent_godown_id || "" }); setEditingId(g.id); setOpen(true); }}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => onDelete(g)}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={editingId ? "Edit Godown" : "New Godown"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-godown" disabled={!online}>Save</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Name" required>
            <Input required data-testid="form-godown-name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Parent Godown">
            <Select value={form.parent_godown_id}
              onChange={(e) => setForm({ ...form, parent_godown_id: e.target.value })}>
              <option value="">— None (top level) —</option>
              {items.filter((g) => g.id !== editingId).map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Address">
            <Textarea rows={2} value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
