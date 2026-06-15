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
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import {
  Plus,
  Trash2,
  Mail,
  Phone,
  MessageCircle,
  PhoneCall,
  Globe,
  Pencil,
} from "lucide-react";

const STATUSES = ["NEW", "CONTACTED", "QUOTED", "WON", "LOST"];
const blank = {
  company_name: "",
  contact_person: "",
  country: "India",
  email: "",
  phone: "",
  source: "Website",
  interested_in: "",
  estimated_value: 0,
  status: "NEW",
  notes: "",
  next_follow_up: "",
};

export default function Leads() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/leads");
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      estimated_value: Number(form.estimated_value || 0),
    };
    try {
      if (editingId) await api.put(`/leads/${editingId}`, payload);
      else await api.post("/leads", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };
  const onDelete = async (item) => {
    if (!window.confirm(`Delete lead from ${item.company_name}?`)) return;
    try {
      await api.delete(`/leads/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const moveStatus = async (lead, status) => {
    try {
      await api.patch(`/leads/${lead.id}/status?status=${status}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const grouped = STATUSES.reduce((acc, s) => {
    acc[s] = items.filter((i) => i.status === s);
    return acc;
  }, {});

  return (
    <div data-testid="leads-page">
      <PageHeader
        eyebrow="CRM"
        title="Leads & Buyer Pipeline"
        description="Track buyer inquiries from first contact to closed deals."
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-lead"
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New lead
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No leads yet" />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
          {STATUSES.map((s) => (
            <div
              key={s}
              data-testid={`lead-col-${s}`}
              className="border border-zinc-800 bg-zinc-900/50"
            >
              <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-black">
                <div className="font-mono text-xs uppercase tracking-wider text-zinc-300 flex items-center gap-2">
                  <StatusBadge status={s} />
                </div>
                <span className="font-display font-bold text-yellow-400 text-sm">
                  {grouped[s].length}
                </span>
              </div>
              <div className="p-2 space-y-2 min-h-[200px]">
                {grouped[s].map((l) => (
                  <div
                    key={l.id}
                    data-testid={`lead-card-${l.id}`}
                    className="border border-zinc-800 bg-zinc-950 p-3 hover:border-yellow-400 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-display font-bold text-white text-sm truncate">
                          {l.company_name}
                        </div>
                        <div className="text-xs text-zinc-400 mt-0.5 flex items-center gap-1">
                          <Globe className="w-3 h-3 text-yellow-400" />
                          {l.country}
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...l });
                          setEditingId(l.id);
                          setOpen(true);
                        }}
                        className="text-zinc-500 hover:text-yellow-400"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {l.interested_in && (
                      <div className="mt-2 text-xs text-zinc-300 border-l-2 border-yellow-400 pl-2">
                        {l.interested_in}
                      </div>
                    )}
                    <div className="mt-2 flex items-center justify-between">
                      <div className="font-mono text-xs text-yellow-400 tabular">
                        ₹{Number(l.estimated_value || 0).toLocaleString("en-IN")}
                      </div>
                      <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                        {l.source}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-px bg-zinc-800 border border-zinc-800">
                      {l.phone && (
                        <a
                          href={`https://wa.me/${l.phone.replace(/\D/g, "")}`}
                          target="_blank"
                          rel="noreferrer"
                          data-testid={`wa-${l.id}`}
                          className="bg-zinc-950 hover:bg-yellow-400 hover:text-black text-zinc-300 flex items-center justify-center py-1.5 transition-colors"
                          title="WhatsApp"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                        </a>
                      )}
                      {l.email && (
                        <a
                          href={`mailto:${l.email}`}
                          data-testid={`mail-${l.id}`}
                          className="bg-zinc-950 hover:bg-yellow-400 hover:text-black text-zinc-300 flex items-center justify-center py-1.5 transition-colors"
                          title="Email"
                        >
                          <Mail className="w-3.5 h-3.5" />
                        </a>
                      )}
                      {l.phone && (
                        <a
                          href={`tel:${l.phone}`}
                          className="bg-zinc-950 hover:bg-yellow-400 hover:text-black text-zinc-300 flex items-center justify-center py-1.5 transition-colors"
                          title="Call"
                        >
                          <PhoneCall className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-1">
                      <select
                        value={l.status}
                        onChange={(e) => moveStatus(l, e.target.value)}
                        data-testid={`move-${l.id}`}
                        className="flex-1 bg-black border border-zinc-800 text-[10px] font-mono uppercase tracking-wider text-zinc-300 px-1.5 py-1 focus:border-yellow-400"
                      >
                        {STATUSES.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => onDelete(l)}
                        className="text-zinc-500 hover:text-red-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {grouped[s].length === 0 && (
                  <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-600 text-center py-6">
                    Empty column
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Lead" : "New Lead"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-lead">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Company name" required>
            <Input
              required
              data-testid="form-lead-company"
              value={form.company_name}
              onChange={(e) =>
                setForm({ ...form, company_name: e.target.value })
              }
            />
          </Field>
          <Field label="Contact Person">
            <Input
              value={form.contact_person || ""}
              onChange={(e) =>
                setForm({ ...form, contact_person: e.target.value })
              }
            />
          </Field>
          <Field label="Country">
            <Input
              value={form.country || ""}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
            />
          </Field>
          <Field label="Email">
            <Input
              type="email"
              value={form.email || ""}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Phone">
            <Input
              value={form.phone || ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          <Field label="Source">
            <Input
              value={form.source || ""}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
            />
          </Field>
          <Field label="Interested in">
            <Input
              value={form.interested_in || ""}
              onChange={(e) =>
                setForm({ ...form, interested_in: e.target.value })
              }
            />
          </Field>
          <Field label="Estimated value (₹)">
            <Input
              type="number"
              value={form.estimated_value}
              onChange={(e) =>
                setForm({ ...form, estimated_value: e.target.value })
              }
            />
          </Field>
          <Field label="Status">
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
            >
              {STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </Field>
          <Field label="Next follow-up">
            <Input
              type="date"
              value={form.next_follow_up?.slice(0, 10) || ""}
              onChange={(e) =>
                setForm({ ...form, next_follow_up: e.target.value })
              }
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="Notes">
              <textarea
                rows={3}
                value={form.notes || ""}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
              />
            </Field>
          </div>
        </form>
      </Modal>
    </div>
  );
}
