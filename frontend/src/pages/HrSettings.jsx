import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2 } from "lucide-react";

const TABS = [
  { key: "branches", label: "Branches", endpoint: "/hr/branches", fields: ["name", "code", "location", "manager"] },
  { key: "departments", label: "Departments", endpoint: "/hr/departments", fields: ["name", "description"] },
  { key: "designations", label: "Designations", endpoint: "/hr/designations", fields: ["name", "description"] },
  { key: "shifts", label: "Shifts", endpoint: "/hr/shifts", fields: ["name", "start_time", "end_time", "late_grace_min"] },
  { key: "holidays", label: "Holidays", endpoint: "/hr/holidays", fields: ["date", "name", "description"] },
  { key: "leave-types", label: "Leave Types", endpoint: "/hr/leave-types", fields: ["name", "annual_quota", "paid"] },
];

const FIELD_DEFS = {
  name: { type: "text", required: true, label: "Name" },
  code: { type: "text", label: "Short Code" },
  location: { type: "text", label: "Location" },
  manager: { type: "text", label: "Manager" },
  description: { type: "text", label: "Description" },
  start_time: { type: "time", label: "Start Time", default: "09:00" },
  end_time: { type: "time", label: "End Time", default: "18:00" },
  late_grace_min: { type: "number", label: "Late Grace (min)", default: 10 },
  date: { type: "date", required: true, label: "Date" },
  annual_quota: { type: "number", label: "Annual Quota (days)", default: 12 },
  paid: { type: "checkbox", label: "Paid leave", default: true },
};

export default function HrSettings() {
  const [tab, setTab] = useState("branches");
  const tabDef = TABS.find((t) => t.key === tab);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});

  const load = async () => {
    const r = await api.get(tabDef.endpoint);
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const blank = () =>
    tabDef.fields.reduce((acc, f) => {
      acc[f] = FIELD_DEFS[f]?.default !== undefined ? FIELD_DEFS[f].default : "";
      return acc;
    }, {});

  const startNew = () => {
    setForm(blank());
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (it) => {
    setForm({ ...blank(), ...it });
    setEditingId(it.id);
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = { ...form };
    tabDef.fields.forEach((f) => {
      if (FIELD_DEFS[f]?.type === "number") payload[f] = Number(payload[f] || 0);
    });
    try {
      if (editingId) await api.put(`${tabDef.endpoint}/${editingId}`, payload);
      else await api.post(tabDef.endpoint, payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (it) => {
    if (!window.confirm(`Delete ${it.name || it.date}?`)) return;
    try {
      await api.delete(`${tabDef.endpoint}/${it.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  // Enter-as-Tab across the modal form; Ctrl+Enter/Ctrl+S saves, Esc cancels,
  // first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

  useModuleShortcuts({
    onNew: () => { if (!open) startNew(); },
  });

  return (
    <div data-testid="hr-settings-page">
      <PageHeader
        eyebrow="HRM · Configuration"
        title="HR Settings"
        description="Branches, departments, designations, shifts, holidays and leave types."
      />

      <div className="flex flex-wrap gap-1 border-b border-zinc-800 mb-5">
        {TABS.map((t) => (
          <button
            key={t.key}
            data-testid={`tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-xs font-mono uppercase tracking-wider border-b-2 ${
              t.key === tab
                ? "border-yellow-400 text-yellow-400"
                : "border-transparent text-zinc-400 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
        <div className="ml-auto pb-2">
          <PrimaryButton icon={Plus} onClick={startNew} testid={`new-${tab}`}>
            New
          </PrimaryButton>
        </div>
      </div>

      <div className="border border-zinc-800 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900">
            <tr className="text-left label-overline">
              {tabDef.fields.map((f) => (
                <th key={f} className="px-3 py-2.5">{FIELD_DEFS[f]?.label || f}</th>
              ))}
              <th className="px-3 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={tabDef.fields.length + 1} className="text-center text-zinc-500 py-6 font-mono text-xs uppercase">No records</td></tr>
            ) : items.map((it) => (
              <tr key={it.id} className="border-t border-zinc-900 hover:bg-zinc-900/60">
                {tabDef.fields.map((f) => (
                  <td key={f} className="px-3 py-2 text-zinc-200">
                    {typeof it[f] === "boolean" ? (it[f] ? "Yes" : "No") : (it[f] ?? "—")}
                  </td>
                ))}
                <td className="px-3 py-2 text-right">
                  <div className="inline-flex gap-1">
                    <button onClick={() => startEdit(it)} className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => onDelete(it)} className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? `Edit ${tabDef.label}` : `New ${tabDef.label}`}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid={`save-${tab}`}>Save</PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {tabDef.fields.map((f) => {
            const def = FIELD_DEFS[f] || {};
            if (def.type === "checkbox") {
              return (
                <label key={f} className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    className="accent-yellow-400"
                    checked={!!form[f]}
                    onChange={(e) => setForm({ ...form, [f]: e.target.checked })}
                  />
                  {def.label}
                </label>
              );
            }
            return (
              <Field key={f} label={def.label || f} required={def.required}>
                <Input
                  type={def.type || "text"}
                  required={def.required}
                  value={form[f] ?? ""}
                  onChange={(e) => setForm({ ...form, [f]: e.target.value })}
                />
              </Field>
            );
          })}
        </form>
      </Modal>
    </div>
  );
}
