import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  Select,
  EmptyState,
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import LineItemsEditor from "@/components/LineItemsEditor";
import { CurrencyFields, downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import { Plus, Pencil, Trash2, Download, IndianRupee, Sparkles, FileJson, Truck, QrCode, ShieldAlert, Share2 } from "lucide-react";

const blank = {
  customer_id: "",
  invoice_type: "TAX_INVOICE",
  items: [],
  status: "UNPAID",
  payment_received: 0,
  notes: "",
  currency: "INR",
  exchange_rate: 1,
};

export default function Invoices() {
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [paymentItem, setPaymentItem] = useState(null);
  const [paymentAmount, setPaymentAmount] = useState(0);

  // E-Invoice & E-Way Bill modals
  const [einvoiceItem, setEinvoiceItem] = useState(null);
  const [ewbItem, setEwbItem] = useState(null);
  const [ewbForm, setEwbForm] = useState({
    transporter_name: "",
    vehicle_no: "",
    distance_km: 50,
    transport_mode: "ROAD"
  });

  const load = async () => {
    const r = await api.get("/invoices");
    setItems(r.data);
  };
  useEffect(() => {
    load();
    api.get("/customers").then((r) => setCustomers(r.data));
    api.get("/products").then((r) => setProducts(r.data));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.customer_id) return toast.error("Select a customer");
    if (form.items.length === 0) return toast.error("Add line items");
    const payload = {
      ...form,
      payment_received: Number(form.payment_received || 0),
      items: form.items.map((i) => ({
        ...i,
        quantity: Number(i.quantity),
        unit_price: Number(i.unit_price),
        gst_rate: Number(i.gst_rate),
      })),
    };
    try {
      if (editingId) await api.put(`/invoices/${editingId}`, payload);
      else await api.post("/invoices", payload);
      toast.success("Invoice Saved Successfully");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.invoice_number}?`)) return;
    try {
      await api.delete(`/invoices/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const recordPayment = async () => {
    if (!paymentAmount || paymentAmount <= 0)
      return toast.error("Enter a valid amount");
    try {
      await api.post(
        `/invoices/${paymentItem.id}/payment?amount=${paymentAmount}`
      );
      toast.success("Payment recorded");
      setPaymentItem(null);
      setPaymentAmount(0);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  // E-Invoice Actions
  const handleGenerateEinvoice = async (invoiceId) => {
    try {
      const res = await api.post(`/invoices/${invoiceId}/generate-einvoice`);
      toast.success("E-Invoice generated successfully!");
      setEinvoiceItem(res.data);
      load();
    } catch (e) {
      toast.error("Failed to generate E-Invoice.");
    }
  };

  const handleCancelEinvoice = async (invoiceId) => {
    if (!window.confirm("Are you sure you want to cancel this E-Invoice on the GST Portal?")) return;
    try {
      const res = await api.post(`/invoices/${invoiceId}/cancel-einvoice`);
      toast.success("E-Invoice cancelled successfully.");
      setEinvoiceItem(res.data);
      load();
    } catch (e) {
      toast.error("Failed to cancel E-Invoice.");
    }
  };

  const handleDownloadEinvoiceJson = async (invoice) => {
    try {
      const res = await api.get(`/invoices/${invoice.id}/einvoice-json`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `e-invoice-${invoice.invoice_number}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      toast.success("E-Invoice JSON schema downloaded.");
    } catch (e) {
      toast.error("Failed to download E-Invoice JSON.");
    }
  };

  // E-Way Bill Actions
  const handleOpenEwbModal = (invoice) => {
    setEwbItem(invoice);
    setEwbForm({
      transporter_name: invoice.transporter_name || "",
      vehicle_no: invoice.vehicle_no || "",
      distance_km: invoice.distance_km || 50,
      transport_mode: invoice.transport_mode || "ROAD"
    });
  };

  const handleGenerateEwb = async (e) => {
    e.preventDefault();
    try {
      const params = new URLSearchParams(ewbForm).toString();
      await api.post(`/invoices/${ewbItem.id}/generate-ewb?${params}`);
      toast.success("E-Way Bill generated successfully!");
      setEwbItem(null);
      load();
    } catch (err) {
      toast.error("Failed to generate E-Way Bill.");
    }
  };

  return (
    <div data-testid="invoices-page">
      <PageHeader
        eyebrow="Sales"
        title="GST Invoice Registry"
        description="Generate Tax Invoices, manage export logs, Debit/Credit notes, and file simulated portal E-Invoices and E-Way Bills."
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-invoice"
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New invoice
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No invoices yet" />
      ) : (
        <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto rounded-md">
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="border-b border-zinc-800 label-overline">
                <th className="px-3 py-2.5">Invoice#</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5 text-right">Taxable</th>
                <th className="px-3 py-2.5 text-right">CGST+SGST/IGST</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">GST Portal</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const out = Number(p.total || 0) - Number(p.payment_received || 0);
                const gst_disp = p.igst > 0 ? `${fmtMoney(p.igst, p.currency)} (IGST)` : `${fmtMoney(p.cgst + p.sgst, p.currency)} (CGST+SGST)`;
                return (
                  <tr
                    key={p.id}
                    className="border-b border-zinc-900 hover:bg-zinc-900/60 text-zinc-100"
                  >
                    <td className="px-3 py-2.5 font-bold text-primary">
                      {p.invoice_number}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-zinc-400">
                      {p.invoice_type?.replace("_", " ")}
                    </td>
                    <td className="px-3 py-2.5 text-white">{p.customer_name}</td>
                    <td className="px-3 py-2.5 text-right tabular text-zinc-300">
                      {fmtMoney(p.taxable_value || p.subtotal, p.currency)}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular text-zinc-400 text-xs">
                      {gst_disp}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular text-white font-bold">
                      {fmtMoney(p.total, p.currency)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-col gap-1">
                        <span className="text-[9px] uppercase flex items-center gap-1">
                          E-Inv: <span className={p.einvoice_status === "GENERATED" ? "text-green-500 font-bold" : p.einvoice_status === "CANCELLED" ? "text-red-500" : "text-zinc-500"}>{p.einvoice_status}</span>
                        </span>
                        <span className="text-[9px] uppercase flex items-center gap-1">
                          E-Way: <span className={p.ewb_status === "GENERATED" ? "text-green-500 font-bold" : "text-zinc-500"}>{p.ewb_status || "PENDING"}</span>
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={p.status} />
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <div className="inline-flex gap-1">
                        <button
                          onClick={() => setEinvoiceItem(p)}
                          title="E-Invoice Details"
                          className="w-7 h-7 border border-zinc-800 hover:border-primary hover:text-primary text-zinc-400 flex items-center justify-center"
                        >
                          <QrCode className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleOpenEwbModal(p)}
                          title="E-Way Bill"
                          className="w-7 h-7 border border-zinc-800 hover:border-green-500 hover:text-green-400 text-zinc-400 flex items-center justify-center"
                        >
                          <Truck className="w-3.5 h-3.5" />
                        </button>
                        {p.status !== "PAID" && (
                          <button
                            onClick={() => {
                              setPaymentItem(p);
                              setPaymentAmount(out);
                            }}
                            title="Record Payment"
                            className="w-7 h-7 border border-zinc-800 hover:border-green-500 hover:text-green-400 text-zinc-400 flex items-center justify-center"
                          >
                            <IndianRupee className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() =>
                            downloadPdf(
                              `/invoices/${p.id}/pdf`,
                              `${p.invoice_number}.pdf`
                            )
                          }
                          title="Download PDF"
                          data-testid={`pdf-${p.id}`}
                          className="w-7 h-7 border border-zinc-800 hover:border-primary hover:text-primary text-zinc-400 flex items-center justify-center"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        <SendEmailButton
                          docType="invoice"
                          docId={p.id}
                          docNumber={p.invoice_number}
                          defaultRecipient={
                            customers.find((c) => c.id === p.customer_id)?.email || ""
                          }
                          defaultRecipientName={p.customer_name}
                        />
                        <button
                          onClick={() => {
                            const text = `Hi, here is Invoice ${p.invoice_number} from Gravity Engineering Works. Total: ${fmtMoney(p.total, p.currency)}. Download PDF: ${window.location.origin}/api/invoices/${p.id}/pdf`;
                            window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
                          }}
                          title="Share via WhatsApp"
                          className="w-7 h-7 border border-zinc-800 hover:border-green-500 hover:text-green-400 text-zinc-400 flex items-center justify-center"
                        >
                          <Share2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            setForm({ ...blank, ...p });
                            setEditingId(p.id);
                            setOpen(true);
                          }}
                          className="w-7 h-7 border border-zinc-800 hover:border-primary hover:text-primary text-zinc-400 flex items-center justify-center"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onDelete(p)}
                          className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Main Invoice Form Modal */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Invoice" : "New GST Invoice"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-invoice">
              Save
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Invoice Type" required>
              <Select
                value={form.invoice_type}
                onChange={(e) => setForm({ ...form, invoice_type: e.target.value })}
              >
                <option value="TAX_INVOICE">Tax Invoice</option>
                <option value="EXPORT_INVOICE">Export Invoice</option>
                <option value="DEBIT_NOTE">Debit Note</option>
                <option value="CREDIT_NOTE">Credit Note</option>
                <option value="PURCHASE_INVOICE">Purchase Invoice</option>
              </Select>
            </Field>

            <Field label="Customer" required>
              <select
                required
                data-testid="form-inv-customer"
                value={form.customer_id}
                onChange={(e) =>
                  setForm({ ...form, customer_id: e.target.value })
                }
                className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
              >
                <option value="">— select —</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.company || c.name}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Payment received">
              <Input
                type="number"
                step="0.01"
                value={form.payment_received}
                onChange={(e) =>
                  setForm({ ...form, payment_received: e.target.value })
                }
              />
            </Field>
            
            <div className="md:col-span-3">
              <CurrencyFields form={form} setForm={setForm} />
            </div>
          </div>
          <LineItemsEditor
            items={form.items}
            setItems={(items) => setForm({ ...form, items })}
            products={products}
          />
          <Field label="Notes">
            <textarea
              rows={2}
              value={form.notes || ""}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
            />
          </Field>
        </div>
      </Modal>

      {/* Record Payment Modal */}
      <Modal
        open={!!paymentItem}
        onClose={() => setPaymentItem(null)}
        title={`Record Payment · ${paymentItem?.invoice_number || ""}`}
        size="sm"
        footer={
          <>
            <SecondaryButton onClick={() => setPaymentItem(null)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={recordPayment}>Record</PrimaryButton>
          </>
        }
      >
        {paymentItem && (
          <div className="space-y-3">
            <div className="text-sm text-zinc-400">
              Outstanding:{" "}
              <span className="text-red-400 tabular">
                {fmtMoney(
                  Number(paymentItem.total || 0) -
                    Number(paymentItem.payment_received || 0),
                  paymentItem.currency
                )}
              </span>
            </div>
            <Field label={`Amount received (${paymentItem.currency || "INR"})`}>
              <Input
                type="number"
                step="0.01"
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(Number(e.target.value))}
              />
            </Field>
          </div>
        )}
      </Modal>

      {/* E-Invoice details & QR Code Modal */}
      <Modal
        open={!!einvoiceItem}
        onClose={() => setEinvoiceItem(null)}
        title={`GST E-Invoice Portal Registry · ${einvoiceItem?.invoice_number || ""}`}
        size="md"
      >
        {einvoiceItem && (
          <div className="space-y-4 font-mono text-xs text-zinc-300">
            <div className="flex justify-between items-center bg-zinc-900 p-3 border border-zinc-800">
              <span className="label-overline">E-Invoice Status</span>
              <StatusBadge status={einvoiceItem.einvoice_status} />
            </div>

            {einvoiceItem.einvoice_status === "GENERATED" ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-zinc-800 p-3 bg-zinc-950">
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Ack No</span>
                    <span className="text-white font-bold">{einvoiceItem.ack_no}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block text-[9px] uppercase">Ack Date</span>
                    <span className="text-white font-bold">{einvoiceItem.ack_date}</span>
                  </div>
                  <div className="md:col-span-2">
                    <span className="text-zinc-500 block text-[9px] uppercase">IRN (Invoice Reference Number)</span>
                    <span className="text-primary break-all text-[10px]">{einvoiceItem.irn}</span>
                  </div>
                </div>

                {/* Scanned QR Code Graphic Mock */}
                <div className="flex flex-col items-center justify-center p-4 border border-zinc-800 bg-zinc-950/40 space-y-2">
                  <div className="w-40 h-40 bg-white p-2 border-4 border-zinc-800 flex items-center justify-center relative">
                    <QrCode className="w-36 h-36 text-zinc-900" strokeWidth={1.5} />
                    <div className="absolute inset-0 bg-black/5 flex items-center justify-center" />
                  </div>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Digitally Signed QR Code</span>
                </div>

                <div className="flex gap-2 justify-end">
                  <SecondaryButton icon={FileJson} onClick={() => handleDownloadEinvoiceJson(einvoiceItem)}>
                    EXPORT SCHEMA JSON
                  </SecondaryButton>
                  <SecondaryButton icon={ShieldAlert} danger onClick={() => handleCancelEinvoice(einvoiceItem.id)}>
                    CANCEL E-INVOICE
                  </SecondaryButton>
                </div>
              </div>
            ) : (
              <div className="py-6 flex flex-col items-center justify-center text-center space-y-3 bg-zinc-900/10 border border-zinc-800">
                <QrCode className="w-12 h-12 text-zinc-700" />
                <div>
                  <div className="font-bold text-zinc-200">No Registry Record Found</div>
                  <p className="text-[10px] text-zinc-500 max-w-sm mt-1 leading-relaxed">
                    This invoice has not been registered on the NIC e-invoice portal yet, or the portal record has been revoked/cancelled.
                  </p>
                </div>
                {einvoiceItem.einvoice_status !== "CANCELLED" && (
                  <PrimaryButton icon={Sparkles} onClick={() => handleGenerateEinvoice(einvoiceItem.id)}>
                    GENERATE E-INVOICE
                  </PrimaryButton>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Modal: Generate E-Way Bill */}
      <Modal
        open={!!ewbItem}
        onClose={() => setEwbItem(null)}
        title={`Simulate E-Way Bill · ${ewbItem?.invoice_number || ""}`}
        size="md"
        footer={
          <>
            <SecondaryButton onClick={() => setEwbItem(null)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={handleGenerateEwb}>
              GENERATE EWB
            </PrimaryButton>
          </>
        }
      >
        {ewbItem && (
          <form className="space-y-4 text-xs font-mono">
            {ewbItem.ewb_number && (
              <div className="bg-green-950/20 border border-green-800 p-3 text-green-400 space-y-1">
                <div>E-Way Bill Status: <span className="font-bold">GENERATED</span></div>
                <div>EWB Number: <span className="font-bold text-white text-sm">{ewbItem.ewb_number}</span></div>
                <div>Validity: <span className="font-bold">{ewbItem.ewb_date}</span></div>
              </div>
            )}
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Transporter Name" required>
                <Input
                  value={ewbForm.transporter_name}
                  onChange={(e) => setEwbForm({ ...ewbForm, transporter_name: e.target.value })}
                  placeholder="e.g. VRL Logistics Ltd"
                  required
                />
              </Field>

              <Field label="Vehicle Number" required>
                <Input
                  value={ewbForm.vehicle_no}
                  onChange={(e) => setEwbForm({ ...ewbForm, vehicle_no: e.target.value })}
                  placeholder="e.g. MH-12-PQ-9876"
                  required
                />
              </Field>

              <Field label="Distance (KM)" required>
                <Input
                  type="number"
                  value={ewbForm.distance_km}
                  onChange={(e) => setEwbForm({ ...ewbForm, distance_km: parseFloat(e.target.value) })}
                  required
                />
              </Field>

              <Field label="Transport Mode" required>
                <Select
                  value={ewbForm.transport_mode}
                  onChange={(e) => setEwbForm({ ...ewbForm, transport_mode: e.target.value })}
                  required
                >
                  <option value="ROAD">Road</option>
                  <option value="RAIL">Rail</option>
                  <option value="AIR">Air</option>
                  <option value="SHIP">Ship</option>
                </Select>
              </Field>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
