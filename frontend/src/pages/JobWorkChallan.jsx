import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";
import {
  PageHeader, Card, Field, Input, Textarea, Select, PrimaryButton, SecondaryButton, StatusBadge,
} from "@/components/ui-kit";
import ItemSearch from "@/components/ItemSearch";
import SendEmailButton from "@/components/SendEmailButton";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import usePdfAction from "@/hooks/usePdfAction";
import {
  Plus, Trash2, Save, Printer, Eye, Download, MessageCircle, ArrowRightCircle, X, Ban,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const COLS_PER_ROW = 5; // item search, HSN, qty, rate, remarks — the keyboard-nav columns

const blankLine = () => ({
  product_id: null, product_name: "", sku: "", description: "", hsn_code: "",
  unit: DEFAULT_UOM, quantity: "", rate: "", remarks: "", is_custom: false,
});

export default function JobWorkChallan() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isEdit = !!id;

  const [products, setProducts] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [challanMeta, setChallanMeta] = useState(null); // { id, challan_number, status } once saved

  const [form, setForm] = useState({
    date: new Date().toISOString().split("T")[0],
    job_worker_id: "", job_worker_name: "", job_worker_gstin: "",
    contact_person: "", mobile: "", address: "",
    nature: "inputs", gst_type: "auto",
    vehicle_no: "", driver_name: "", transport: "", lr_number: "", eway_bill_number: "",
    process_name: "", instructions: "", notes: "",
    prepared_by: "", checked_by: "",
    status: "PENDING",
  });
  const [items, setItems] = useState([blankLine()]);

  const grid = useGridKeyNav({
    rowCount: items.length,
    colCount: COLS_PER_ROW,
    onRowComplete: () => setItems((prev) => [...prev, blankLine()]),
  });
  const { run: runPdf, busy: pdfBusy } = usePdfAction();

  useEffect(() => {
    Promise.allSettled([
      api.get("/products"),
      api.get("/purchase/v2/vendors"),
    ]).then(([pRes, vRes]) => {
      if (pRes.status === "fulfilled") setProducts(pRes.value.data.items || pRes.value.data || []);
      if (vRes.status === "fulfilled") setVendors(vRes.value.data.items || vRes.value.data || []);
    });
  }, []);

  useEffect(() => {
    if (!isEdit) return;
    setLoading(true);
    api.get(`/job-work/challans/${id}`)
      .then((res) => {
        const c = res.data;
        setChallanMeta({ id: c.id, challan_number: c.challan_number, status: c.status });
        setForm({
          date: c.date || "", job_worker_id: c.job_worker_id || "", job_worker_name: c.job_worker_name || "",
          job_worker_gstin: c.job_worker_gstin || "", contact_person: c.contact_person || "", mobile: c.mobile || "",
          address: c.address || "", nature: c.nature || "inputs", gst_type: c.gst_type || "auto",
          vehicle_no: c.vehicle_no || "", driver_name: c.driver_name || "", transport: c.transport || "",
          lr_number: c.lr_number || "", eway_bill_number: c.eway_bill_number || "",
          process_name: c.process_name || "", instructions: c.instructions || "", notes: c.notes || "",
          prepared_by: c.prepared_by || "", checked_by: c.checked_by || "", status: c.status || "PENDING",
        });
        setItems((c.items || []).map((it) => ({
          product_id: it.product_id, product_name: it.product_name, sku: it.sku || "",
          description: it.description || "", hsn_code: it.hsn_code || "",
          unit: it.uom || DEFAULT_UOM, quantity: it.quantity, rate: it.rate ?? "",
          remarks: it.remarks || "", is_custom: !!it.is_custom,
        })));
      })
      .catch(() => toast.error("Failed to load challan"))
      .finally(() => setLoading(false));
  }, [id, isEdit]);

  const locked = isEdit && challanMeta && !["DRAFT", "PENDING"].includes(challanMeta.status);

  const pickVendor = useCallback((vendorId) => {
    const v = vendors.find((x) => x.id === vendorId);
    setForm((f) => ({
      ...f,
      job_worker_id: vendorId,
      job_worker_name: v?.name || "",
      job_worker_gstin: v?.gstin || "",
      contact_person: v?.contact_person || f.contact_person,
      mobile: v?.mobile || v?.phone || f.mobile,
      address: v?.address || f.address,
    }));
  }, [vendors]);

  const setLine = (idx, changes) => {
    setItems((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], ...changes };
      return next;
    });
  };

  const pickProduct = (idx, productId, product) => {
    if (!product) {
      setLine(idx, { product_id: null, product_name: "", sku: "", unit: DEFAULT_UOM, is_custom: false });
      return;
    }
    if (product.is_custom) {
      setLine(idx, { product_id: null, product_name: product.name, is_custom: true });
      return;
    }
    setLine(idx, {
      product_id: product.id, product_name: product.name, sku: product.sku || "",
      unit: product.unit || DEFAULT_UOM, hsn_code: product.hsn_code || "",
      rate: product.cost_price ?? "",
    });
  };

  const addRow = () => setItems((prev) => [...prev, blankLine()]);
  const removeRow = (idx) => setItems((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev));

  const totals = useMemo(() => {
    let qty = 0, amount = 0;
    for (const it of items) {
      const q = parseFloat(it.quantity) || 0;
      const r = parseFloat(it.rate) || 0;
      qty += q;
      amount += q * r;
    }
    return { qty, amount };
  }, [items]);

  const buildPayload = (status) => {
    const validItems = items.filter((it) => (it.product_name || "").trim() && parseFloat(it.quantity) > 0);
    return {
      ...form,
      status,
      items: validItems.map((it) => ({
        product_id: it.product_id, product_name: it.product_name, sku: it.sku,
        description: it.description, hsn_code: it.hsn_code, unit: it.unit,
        quantity: parseFloat(it.quantity) || 0, rate: it.rate === "" ? null : parseFloat(it.rate),
        remarks: it.remarks, is_custom: it.is_custom,
      })),
    };
  };

  const save = async (status) => {
    if (!form.job_worker_id) { toast.error("Select a Job Worker"); return; }
    const payload = buildPayload(status);
    if (payload.items.length === 0) { toast.error("Add at least one item with quantity"); return; }
    setSaving(true);
    try {
      let result;
      if (isEdit) {
        result = await api.put(`/job-work/challans/${id}`, payload);
      } else {
        result = await api.post("/job-work/challans", payload);
      }
      toast.success(status === "DRAFT" ? "Saved as Draft" : "Challan saved");
      navigate(`/job-work/challans/${result.data.id}`, { replace: true });
      return result.data;
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Save failed");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const saveAndPrint = async () => {
    const saved = await save(form.status === "DRAFT" ? "DRAFT" : "PENDING");
    if (saved) runPdf(`/job-work/challans/${saved.id}/pdf`, `${saved.challan_number}.pdf`, saved.id);
  };

  const downloadPdf = () => {
    if (!challanMeta) { toast.error("Save the challan first"); return; }
    runPdf(`/job-work/challans/${challanMeta.id}/pdf`, `${challanMeta.challan_number}.pdf`, challanMeta.id);
  };

  const whatsappShare = () => {
    if (!challanMeta) { toast.error("Save the challan first"); return; }
    const text = `Job Work Challan ${challanMeta.challan_number} for ${form.job_worker_name} — ${totals.qty} units.`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  };

  const generateReceipt = () => {
    if (!challanMeta) { toast.error("Save the challan first"); return; }
    navigate(`/job-work/receipts/new?challan_id=${challanMeta.id}`);
  };

  // A challan past Draft/Pending can no longer be edited or deleted (material
  // has genuinely moved) — cancelling is the only way out, and reverses only
  // the portion still outstanding with the job worker.
  const cancelChallan = async () => {
    if (!challanMeta) return;
    if (!window.confirm(`Cancel challan ${challanMeta.challan_number}? This reverses the material still outstanding with the job worker back into stock.`)) return;
    try {
      const { data } = await api.post(`/job-work/challans/${challanMeta.id}/cancel`);
      setChallanMeta({ id: data.id, challan_number: data.challan_number, status: data.status });
      setForm((f) => ({ ...f, status: data.status }));
      toast.success("Challan cancelled");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Cancel failed");
    }
  };

  // Enter-as-Tab data entry (see useEnterNavigation): Enter/Tab walks the
  // header/job-worker/transport/sign-off fields, falling through to the
  // Material Grid's own Enter/Arrow handling (useGridKeyNav, marked
  // data-grid-managed below). Ctrl+Enter/Ctrl+S/Alt+S saves as PENDING,
  // Escape cancels back to the list. Disabled once the challan is locked
  // (non-draft/pending status) since fields are read-only at that point.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: !loading && !locked,
    autoFocus: !isEdit,
    onSave: () => save("PENDING"),
    onCancel: () => navigate("/job-work"),
  });

  if (loading) return <div className="p-6 text-muted-foreground font-mono text-sm">Loading…</div>;

  return (
    <div ref={formRef} data-testid="job-work-challan-page">
      <PageHeader
        eyebrow="Job Work · Outward"
        title={challanMeta ? `Challan ${challanMeta.challan_number}` : "New Job Work Challan"}
        description="Materials sent to a job worker. Enter moves to the next field — Tally-style."
        actions={challanMeta && <StatusBadge status={challanMeta.status} />}
      />

      <Card className="mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Date" required>
            <Input type="date" value={form.date} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} />
          </Field>
          <Field label="Nature">
            <Select value={form.nature} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, nature: e.target.value }))}>
              <option value="inputs">Inputs (1 yr return)</option>
              <option value="capital_goods">Capital Goods (3 yr return)</option>
            </Select>
          </Field>
          <Field label="GST Type">
            <Select value={form.gst_type} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, gst_type: e.target.value }))}>
              <option value="auto">Auto-detect</option>
              <option value="intra">Intra-state</option>
              <option value="inter">Inter-state</option>
            </Select>
          </Field>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-3">Job Worker</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Job Worker" required>
            <Select value={form.job_worker_id} disabled={locked}
              onChange={(e) => pickVendor(e.target.value)}>
              <option value="">Select job worker…</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </Select>
          </Field>
          <Field label="Contact Person">
            <Input value={form.contact_person} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, contact_person: e.target.value }))} />
          </Field>
          <Field label="GSTIN">
            <Input value={form.job_worker_gstin} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, job_worker_gstin: e.target.value }))} />
          </Field>
          <Field label="Mobile Number">
            <Input value={form.mobile} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, mobile: e.target.value }))} />
          </Field>
          <div className="md:col-span-2">
            <Field label="Address">
              <Textarea rows={1} value={form.address} disabled={locked}
                onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
            </Field>
          </div>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-3">Transport Information</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Vehicle Number">
            <Input value={form.vehicle_no} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, vehicle_no: e.target.value }))} />
          </Field>
          <Field label="Driver Name">
            <Input value={form.driver_name} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, driver_name: e.target.value }))} />
          </Field>
          <Field label="Transport Name">
            <Input value={form.transport} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value }))} />
          </Field>
          <Field label="LR Number">
            <Input value={form.lr_number} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, lr_number: e.target.value }))} />
          </Field>
          <Field label="E-Way Bill Number">
            <Input value={form.eway_bill_number} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, eway_bill_number: e.target.value }))} />
          </Field>
        </div>
      </Card>

      <Card className="mb-4" padded={false}>
        <div className="p-4 pb-0 flex items-center justify-between">
          <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Material Grid</div>
          {!locked && (
            <SecondaryButton icon={Plus} onClick={addRow}>Add Row</SecondaryButton>
          )}
        </div>
        <div className="overflow-x-auto p-4">
          <table data-grid-managed className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="p-2 w-8">#</th>
                <th className="p-2 min-w-[220px]">Item</th>
                <th className="p-2 w-24">HSN</th>
                <th className="p-2 w-20">UOM</th>
                <th className="p-2 w-28">Sent Qty</th>
                <th className="p-2 w-28">Rate</th>
                <th className="p-2 w-28 text-right">Amount</th>
                <th className="p-2 min-w-[140px]">Remarks</th>
                <th className="p-2 w-10"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, idx) => {
                const amount = (parseFloat(it.quantity) || 0) * (parseFloat(it.rate) || 0);
                return (
                  <tr key={idx} className="border-b border-border/60">
                    <td className="p-2 text-muted-foreground">{idx + 1}</td>
                    <td className="p-2">
                      <ItemSearch
                        products={products}
                        value={it.product_id}
                        allowCustom
                        testid={`jwc-item-${idx}`}
                        inputRef={grid.registerCell(idx, 0)}
                        onKeyDown={grid.handleKeyDown(idx, 0)}
                        onChange={(pid, p) => pickProduct(idx, pid, p)}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        ref={grid.registerCell(idx, 1)}
                        onKeyDown={grid.handleKeyDown(idx, 1)}
                        value={it.hsn_code}
                        onChange={(e) => setLine(idx, { hsn_code: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <select
                        value={it.unit}
                        onChange={(e) => setLine(idx, { unit: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-1 focus:border-primary focus:outline-none"
                      >
                        {it.unit && !STANDARD_UOMS.includes(it.unit) && (
                          <option key={it.unit} value={it.unit}>{it.unit}</option>
                        )}
                        {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                      </select>
                    </td>
                    <td className="p-2">
                      <input
                        ref={grid.registerCell(idx, 2)}
                        onKeyDown={grid.handleKeyDown(idx, 2)}
                        type="number" min="0" step="any"
                        value={it.quantity}
                        onChange={(e) => setLine(idx, { quantity: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        ref={grid.registerCell(idx, 3)}
                        onKeyDown={grid.handleKeyDown(idx, 3)}
                        type="number" min="0" step="any"
                        value={it.rate}
                        placeholder="Auto"
                        onChange={(e) => setLine(idx, { rate: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2 text-right font-mono tabular">{amount ? inr(amount) : "—"}</td>
                    <td className="p-2">
                      <input
                        ref={grid.registerCell(idx, 4)}
                        onKeyDown={grid.handleKeyDown(idx, 4)}
                        value={it.remarks}
                        onChange={(e) => setLine(idx, { remarks: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      {items.length > 1 && (
                        <button type="button" onClick={() => removeRow(idx)} className="text-muted-foreground hover:text-destructive">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Sticky footer totals */}
        <div className="sticky bottom-0 border-t border-border bg-muted/60 px-4 py-3 flex justify-end gap-8 text-sm font-mono">
          <span className="text-muted-foreground">Total Qty: <b className="text-foreground">{totals.qty}</b></span>
          <span className="text-muted-foreground">Total Amount: <b className="text-foreground">₹{inr(totals.amount)}</b></span>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-3">Details & Sign-off</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Process Name">
            <Input value={form.process_name} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, process_name: e.target.value }))} />
          </Field>
          <Field label="Expected Return Date">
            <Input value={challanMeta?.due_date || "Auto-computed on save (Rule 45)"} disabled readOnly />
          </Field>
          <div className="md:col-span-2">
            <Field label="Instructions">
              <Textarea rows={2} value={form.instructions} disabled={locked}
                onChange={(e) => setForm((f) => ({ ...f, instructions: e.target.value }))} />
            </Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Terms & Conditions / Notes">
              <Textarea rows={2} value={form.notes} disabled={locked}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
            </Field>
          </div>
          <Field label="Prepared By">
            <Input value={form.prepared_by} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, prepared_by: e.target.value }))} />
          </Field>
          <Field label="Checked By">
            <Input value={form.checked_by} disabled={locked}
              onChange={(e) => setForm((f) => ({ ...f, checked_by: e.target.value }))} />
          </Field>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-2 pb-8">
        {!locked && (
          <>
            <PrimaryButton icon={Save} disabled={saving} onClick={() => save("PENDING")}>
              Save
            </PrimaryButton>
            <SecondaryButton icon={Save} disabled={saving} onClick={() => save("DRAFT")}>
              Save as Draft
            </SecondaryButton>
          </>
        )}
        <SecondaryButton icon={Printer} disabled={saving || pdfBusy} onClick={saveAndPrint}>
          Save & Print
        </SecondaryButton>
        {challanMeta && (
          <>
            <SecondaryButton icon={Eye} disabled={pdfBusy} onClick={downloadPdf}>Preview</SecondaryButton>
            <SecondaryButton icon={Download} disabled={pdfBusy} onClick={downloadPdf}>PDF</SecondaryButton>
            <SecondaryButton icon={MessageCircle} onClick={whatsappShare}>WhatsApp</SecondaryButton>
            <SendEmailButton
              docType="job_work_challan"
              docId={challanMeta.id}
              docNumber={challanMeta.challan_number}
              defaultRecipientName={form.job_worker_name}
            />
            <PrimaryButton icon={ArrowRightCircle} onClick={generateReceipt}>
              Generate Receipt
            </PrimaryButton>
          </>
        )}
        {locked && challanMeta && challanMeta.status !== "CANCELLED" && (
          <SecondaryButton icon={Ban} danger onClick={cancelChallan}>
            Cancel Challan
          </SecondaryButton>
        )}
        <SecondaryButton icon={X} onClick={() => navigate("/job-work")}>Close</SecondaryButton>
      </div>
    </div>
  );
}
