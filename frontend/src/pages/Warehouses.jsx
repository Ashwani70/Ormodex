import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { Plus, Pencil, Trash2, MapPin } from "lucide-react";

const blank = { name: "", location: "", manager: "" };

export default function Warehouses() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/warehouses");
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, []);

  const startNew = () => {
    setForm(blank);
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (item) => {
    setForm({ ...blank, ...item });
    setEditingId(item.id);
    setOpen(true);
  };
  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editingId) await api.put(`/warehouses/${editingId}`, form);
      else await api.post("/warehouses", form);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };
  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api.delete(`/warehouses/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="warehouses-page">
      <PageHeader
        eyebrow="Inventory"
        title="Warehouses"
        description="Storage locations and yard managers"
        actions={
          <PrimaryButton testid="new-warehouse" onClick={startNew} icon={Plus}>
            New warehouse
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState
          message="No warehouses yet"
          action={
            <PrimaryButton onClick={startNew} icon={Plus}>
              Add warehouse
            </PrimaryButton>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((w) => (
            <div
              key={w.id}
              data-testid={`warehouse-card-${w.id}`}
              className="industrial-corner border border-zinc-800 bg-zinc-900 p-5 hover:border-yellow-400 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="font-display font-bold text-white text-lg">
                    {w.name}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-xs text-zinc-400">
                    <MapPin className="w-3 h-3 text-yellow-400" />
                    {w.location}
                  </div>
                </div>
              </div>
              <div className="border-t border-zinc-800 pt-3 flex items-center justify-between">
                <div>
                  <div className="label-overline">Yard Manager</div>
                  <div className="text-sm text-white mt-0.5">
                    {w.manager || "—"}
                  </div>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => startEdit(w)}
                    className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onDelete(w)}
                    className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Warehouse" : "New Warehouse"}
        size="md"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-warehouse">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form onSubmit={submit} className="space-y-3">
          <Field label="Name" required>
            <Input
              required
              data-testid="form-wh-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Location" required>
            <Input
              required
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label="Manager">
            <Input
              value={form.manager || ""}
              onChange={(e) => setForm({ ...form, manager: e.target.value })}
            />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
