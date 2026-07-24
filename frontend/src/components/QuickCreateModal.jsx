import { useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import Modal from "@/components/Modal";
import { Field, Input, PrimaryButton, SecondaryButton } from "@/components/ui-kit";
import useEnterNavigation from "@/hooks/useEnterNavigation";

/**
 * "Create a master without leaving the voucher" — the Ctrl+Enter quick-create
 * flow (spec: "Ctrl+Enter: Open/Create master for the current field...After
 * saving: close popup, return focus, refresh dropdown, automatically select
 * the newly created record"). One generic modal driven by a per-type field
 * spec rather than a bespoke modal per master, so adding a new quick-create
 * type is a config entry here, not a new component.
 *
 * Deliberately minimal: only the fields the backend actually requires (see
 * FIELD_SPECS below) — this is a fast "name it and get back to the voucher"
 * flow, not the full master form. The full record stays editable later from
 * its own master page.
 *
 * Usage — a page wires this once and passes seedName + onCreated to
 * useEnterNavigation's onQuickCreate:
 *   const [quickCreate, setQuickCreate] = useState(null); // { type, seed } | null
 *   useEnterNavigation(formRef, {
 *     onQuickCreate: (type, fieldEl) => setQuickCreate({ type, seed: fieldEl.value }),
 *   });
 *   <QuickCreateModal
 *     open={!!quickCreate} type={quickCreate?.type} seedName={quickCreate?.seed}
 *     onClose={() => setQuickCreate(null)}
 *     onCreated={(record) => { <select it in the field>; setQuickCreate(null); }}
 *   />
 */
const FIELD_SPECS = {
  customer: {
    title: "Quick-Create Customer",
    endpoint: "/customers",
    extra: { party_type: "CUSTOMER" },
    fields: [{ key: "name", label: "Customer Name", required: true }],
  },
  vendor: {
    title: "Quick-Create Vendor",
    endpoint: "/purchase/v2/vendors",
    fields: [{ key: "name", label: "Vendor Name", required: true }],
  },
  ledger: {
    title: "Quick-Create Ledger",
    endpoint: "/ledger/quick-ledger",
    fields: [{ key: "name", label: "Ledger Name", required: true }],
  },
  item: {
    title: "Quick-Create Product",
    endpoint: "/products",
    // sku/category are hard-required by the backend (no server-side default) —
    // shown here rather than silently guessed, so the created record is real
    // and usable, not a placeholder that breaks reports/valuation later.
    fields: [
      { key: "name", label: "Product Name", required: true },
      { key: "sku", label: "SKU", required: true },
      { key: "category", label: "Category", required: true },
    ],
  },
};

export default function QuickCreateModal({ open, type, seedName, onClose, onCreated }) {
  const spec = type ? FIELD_SPECS[type] : null;
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const formRef = useRef(null);
  const lastSeed = useRef(null);

  // Re-seed the name field from whatever the user had already typed in the
  // originating lookup, once per open (not on every render).
  if (open && spec && lastSeed.current !== seedName) {
    lastSeed.current = seedName;
    setForm({ [spec.fields[0].key]: seedName || "" });
  }
  if (!open) lastSeed.current = null;

  const submit = async () => {
    if (!spec) return;
    const missing = spec.fields.find((f) => f.required && !String(form[f.key] || "").trim());
    if (missing) return toast.error(`${missing.label} is required`);
    setSaving(true);
    try {
      const { data } = await api.post(spec.endpoint, { ...spec.extra, ...form });
      toast.success(`${spec.title.replace("Quick-Create ", "")} created`);
      onCreated?.(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Failed to create");
    } finally {
      setSaving(false);
    }
  };

  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: submit,
    onCancel: onClose,
  });

  if (!spec) return null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={spec.title}
      size="sm"
      footer={
        <>
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton onClick={submit} disabled={saving} testid="quick-create-save">
            {saving ? "Creating…" : "Create"}
          </PrimaryButton>
        </>
      }
    >
      <div ref={formRef} className="space-y-3">
        {spec.fields.map((f) => (
          <Field key={f.key} label={f.label} required={f.required}>
            <Input
              value={form[f.key] || ""}
              onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
              autoFocus={f === spec.fields[0]}
            />
          </Field>
        ))}
        <p className="text-xs text-muted-foreground">
          Ctrl+Enter to create · Esc to cancel · edit the full record later from its own master page.
        </p>
      </div>
    </Modal>
  );
}

export { FIELD_SPECS };
