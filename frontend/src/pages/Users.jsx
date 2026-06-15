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
import { Plus, Pencil, Trash2, ShieldCheck, User } from "lucide-react";

const blank = {
  name: "",
  email: "",
  phone: "",
  role: "employee",
  password: "",
};

export default function Users() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/users");
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editingId) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        delete payload.email;
        await api.put(`/users/${editingId}`, payload);
      } else {
        await api.post("/users", form);
      }
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
      await api.delete(`/users/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="users-page">
      <PageHeader
        eyebrow="System"
        title="Users & Roles"
        description="Manage operators, supervisors and admins."
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-user"
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New user
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No users yet" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Email</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">Role</th>
                <th className="px-3 py-2.5">Created</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr
                  key={u.id}
                  className="border-t border-zinc-900 hover:bg-zinc-900/60"
                >
                  <td className="px-3 py-2.5 text-white">
                    <div className="flex items-center gap-2">
                      {u.role === "admin" ? (
                        <ShieldCheck className="w-3.5 h-3.5 text-yellow-400" />
                      ) : (
                        <User className="w-3.5 h-3.5 text-zinc-500" />
                      )}
                      {u.name}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">{u.email}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{u.phone}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`text-xs font-mono uppercase tracking-wider px-2 py-0.5 border ${
                        u.role === "admin"
                          ? "border-yellow-400 text-yellow-400"
                          : "border-zinc-700 text-zinc-400"
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...u, password: "" });
                          setEditingId(u.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(u)}
                        className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
                      >
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

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit User" : "New User"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-user">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Name" required>
            <Input
              required
              data-testid="form-user-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Email" required>
            <Input
              type="email"
              required
              disabled={!!editingId}
              data-testid="form-user-email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Phone">
            <Input
              value={form.phone || ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
            >
              <option value="employee">Employee</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          <div className="md:col-span-2">
            <Field label={editingId ? "New password (leave blank to keep)" : "Password"} required={!editingId}>
              <Input
                type="password"
                required={!editingId}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </Field>
          </div>
        </form>
      </Modal>
    </div>
  );
}
