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
import { downloadPdf } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import { Plus, Pencil, Trash2, Download, Truck } from "lucide-react";

const blank = {
  sales_order_id: "",
  customer_name: "",
  vehicle_no: "",
  driver_name: "",
  driver_phone: "",
  dispatch_date: new Date().toISOString().slice(0, 10),
  items: [],
  status: "PENDING",
  notes: "",
};

export default function Dispatches() {
  const [items, setItems] = useState([]);
  const [salesOrders, setSalesOrders] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/dispatches");
    setItems(r.data);
  };
  useEffect(() => {
    load();
    api.get("/sales-orders").then((r) => setSalesOrders(r.data));
  }, []);

  const onSelectSO = (soId) => {
    const so = salesOrders.find((x) => x.id === soId);
    setForm({
      ...form,
      sales_order_id: soId,
      customer_name: so?.customer_name || "",
      items: so?.items || [],
    });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.vehicle_no || !form.driver_name)
      return toast.error("Vehicle no & driver name required");
    try {
      if (editingId) await api.put(`/dispatches/${editingId}`, form);
      else await api.post("/dispatches", form);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.challan_number}?`)) return;
    try {
      await api.delete(`/dispatches/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="dispatches-page">
      <PageHeader
        eyebrow="Logistics"
        title="Dispatch Challans"
        description="Vehicle, driver and goods-in-transit log"
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-dispatch"
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New dispatch
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No dispatches yet" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Challan#</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5">Vehicle</th>
                <th className="px-3 py-2.5">Driver</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr
                  key={d.id}
                  className="border-t border-zinc-900 hover:bg-zinc-900/60"
                >
                  <td className="px-3 py-2.5 font-mono text-yellow-400">
                    {d.challan_number}
                  </td>
                  <td className="px-3 py-2.5 text-white">{d.customer_name}</td>
                  <td className="px-3 py-2.5 font-mono text-zinc-300 text-xs">
                    <Truck className="inline w-3 h-3 mr-1 text-yellow-400" />
                    {d.vehicle_no}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">
                    {d.driver_name}
                    {d.driver_phone && (
                      <span className="text-xs text-zinc-500 block">
                        {d.driver_phone}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                    {d.dispatch_date}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() =>
                          downloadPdf(
                            `/dispatches/${d.id}/pdf`,
                            `${d.challan_number}.pdf`
                          )
                        }
                        title="Download PDF"
                        data-testid={`pdf-${d.id}`}
                        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <SendEmailButton
                        docType="dispatch"
                        docId={d.id}
                        docNumber={d.challan_number}
                        defaultRecipientName={d.customer_name}
                      />
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...d });
                          setEditingId(d.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(d)}
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
        title={editingId ? "Edit Dispatch" : "New Dispatch"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-dispatch">
              Save
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Linked Sales Order">
              <select
                value={form.sales_order_id || ""}
                onChange={(e) => onSelectSO(e.target.value)}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
              >
                <option value="">— optional —</option>
                {salesOrders.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.order_number} · {s.customer_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Customer Name">
              <Input
                value={form.customer_name || ""}
                onChange={(e) =>
                  setForm({ ...form, customer_name: e.target.value })
                }
              />
            </Field>
            <Field label="Vehicle Number" required>
              <Input
                required
                data-testid="form-disp-vehicle"
                value={form.vehicle_no}
                onChange={(e) =>
                  setForm({ ...form, vehicle_no: e.target.value })
                }
                placeholder="MH-12-AB-1234"
              />
            </Field>
            <Field label="Driver Name" required>
              <Input
                required
                data-testid="form-disp-driver"
                value={form.driver_name}
                onChange={(e) =>
                  setForm({ ...form, driver_name: e.target.value })
                }
              />
            </Field>
            <Field label="Driver Phone">
              <Input
                value={form.driver_phone || ""}
                onChange={(e) =>
                  setForm({ ...form, driver_phone: e.target.value })
                }
              />
            </Field>
            <Field label="Dispatch Date">
              <Input
                type="date"
                value={form.dispatch_date || ""}
                onChange={(e) =>
                  setForm({ ...form, dispatch_date: e.target.value })
                }
              />
            </Field>
            <Field label="Status">
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
              >
                {["PENDING", "IN_TRANSIT", "DELIVERED"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Notes">
            <textarea
              rows={2}
              value={form.notes || ""}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
