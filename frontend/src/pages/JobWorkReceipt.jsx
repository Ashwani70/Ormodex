import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, Card, Field, Input, Textarea, Select, PrimaryButton, SecondaryButton, StatusBadge,
} from "@/components/ui-kit";
import SendEmailButton from "@/components/SendEmailButton";
import usePdfAction from "@/hooks/usePdfAction";
import { Save, Printer, Download, MessageCircle, X } from "lucide-react";

const num = (v) => (v === "" || v === null || v === undefined ? 0 : parseFloat(v) || 0);

const lineFromChallan = (l) => ({
  challan_item_id: l.challan_item_id,
  product_id: l.product_id,
  product_name: l.product_name,
  sku: l.sku || "",
  is_custom: !!l.is_custom,
  uom: l.uom || "pcs",
  quantity_sent: l.quantity_sent,
  quantity_already_received: l.quantity_already_received,
  quantity_pending: l.quantity_pending,
  quantity_received: "",
  accepted_quantity: "",
  rejected_quantity: "",
  scrap_quantity: "",
  remarks: "",
});

export default function JobWorkReceipt() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const isEdit = !!id;
  const preselectChallanId = searchParams.get("challan_id") || "";

  const [challans, setChallans] = useState([]);
  const [selectedChallanId, setSelectedChallanId] = useState(preselectChallanId);
  const [challanInfo, setChallanInfo] = useState(null);
  const [lines, setLines] = useState([]);
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(isEdit);
  const [loadingLines, setLoadingLines] = useState(false);
  const [saving, setSaving] = useState(false);
  const [receiptMeta, setReceiptMeta] = useState(null);
  const { run: runPdf, busy: pdfBusy } = usePdfAction();

  useEffect(() => {
    api.get("/job-work/challans", { params: { limit: 500 } })
      .then((res) => setChallans((res.data.items || res.data || []).filter((c) => ["PENDING", "PARTIAL"].includes(c.status))))
      .catch(() => {});
  }, []);

  const loadChallanLines = useCallback((challanId) => {
    if (!challanId) { setChallanInfo(null); setLines([]); return; }
    setLoadingLines(true);
    api.get(`/job-work/challans/${challanId}/receipt-form`)
      .then((res) => {
        setChallanInfo(res.data);
        setLines((res.data.lines || []).map(lineFromChallan));
      })
      .catch((e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Failed to load challan"))
      .finally(() => setLoadingLines(false));
  }, []);

  useEffect(() => {
    if (!isEdit && preselectChallanId) loadChallanLines(preselectChallanId);
  }, [isEdit, preselectChallanId, loadChallanLines]);

  useEffect(() => {
    if (!isEdit) return;
    setLoading(true);
    api.get("/job-work/receipts", { params: { limit: 1000 } })
      .then((res) => {
        const found = (res.data.items || []).find((r) => r.id === id);
        if (!found) { toast.error("Receipt not found"); return; }
        setReceiptMeta({ id: found.id, receipt_number: found.receipt_number, status: found.status });
        setSelectedChallanId(found.challan_id);
        setDate(found.date || "");
        setNotes(found.notes || "");
        setChallanInfo({
          challan_id: found.challan_id, challan_number: found.challan_number,
          job_worker_name: found.job_worker_name, status: found.status,
        });
        setLines((found.items || []).map((it) => ({
          challan_item_id: it.challan_item_id, product_id: it.product_id, product_name: it.product_name,
          sku: it.sku || "", is_custom: !!it.is_custom, uom: it.uom || "pcs",
          quantity_sent: it.quantity_sent, quantity_already_received: Math.max(0, (it.quantity_sent || 0) - (it.quantity_pending || 0) - num(it.quantity_received)),
          quantity_pending: it.quantity_pending,
          quantity_received: it.quantity_received ?? "", accepted_quantity: it.accepted_quantity ?? "",
          rejected_quantity: it.rejected_quantity ?? "", scrap_quantity: it.scrap_quantity ?? "",
          remarks: it.remarks || "",
        })));
      })
      .catch(() => toast.error("Failed to load receipt"))
      .finally(() => setLoading(false));
  }, [id, isEdit]);

  const setLine = (idx, changes) => {
    setLines((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], ...changes };
      return next;
    });
  };

  const totals = useMemo(() => {
    let received = 0, accepted = 0, rejected = 0, scrap = 0;
    for (const l of lines) {
      received += num(l.quantity_received);
      accepted += num(l.accepted_quantity) || Math.max(0, num(l.quantity_received) - num(l.rejected_quantity) - num(l.scrap_quantity));
      rejected += num(l.rejected_quantity);
      scrap += num(l.scrap_quantity);
    }
    return { received, accepted, rejected, scrap };
  }, [lines]);

  const save = async () => {
    if (!selectedChallanId) { toast.error("Select a Challan"); return; }
    const validLines = lines.filter((l) => num(l.quantity_received) > 0);
    if (validLines.length === 0) { toast.error("Enter a received quantity for at least one line"); return; }
    for (const l of validLines) {
      if (num(l.quantity_received) > num(l.quantity_pending) + 1e-6) {
        toast.error(`Received qty for ${l.product_name} exceeds pending (${l.quantity_pending})`);
        return;
      }
    }
    const payload = {
      date,
      notes,
      items: validLines.map((l) => ({
        challan_item_id: l.challan_item_id,
        product_id: l.product_id,
        product_name: l.product_name,
        sku: l.sku,
        is_custom: l.is_custom,
        quantity_received: num(l.quantity_received),
        accepted_quantity: l.accepted_quantity === "" ? null : num(l.accepted_quantity),
        rejected_quantity: num(l.rejected_quantity),
        scrap_quantity: num(l.scrap_quantity),
        remarks: l.remarks,
      })),
    };
    setSaving(true);
    try {
      let result;
      if (isEdit) {
        result = await api.put(`/job-work/receipts/${id}`, payload);
      } else {
        result = await api.post(`/job-work/challans/${selectedChallanId}/receipt`, payload);
      }
      toast.success("Receipt saved");
      navigate(`/job-work/receipts/${result.data.id}`, { replace: true });
      return result.data;
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Save failed");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const saveAndPrint = async () => {
    const saved = await save();
    if (saved) runPdf(`/job-work/receipts/${saved.id}/pdf`, `${saved.receipt_number}.pdf`, saved.id);
  };

  const downloadPdf = () => {
    if (!receiptMeta) { toast.error("Save the receipt first"); return; }
    runPdf(`/job-work/receipts/${receiptMeta.id}/pdf`, `${receiptMeta.receipt_number}.pdf`, receiptMeta.id);
  };

  const whatsappShare = () => {
    if (!receiptMeta) { toast.error("Save the receipt first"); return; }
    const text = `Job Work Receipt ${receiptMeta.receipt_number} against Challan ${challanInfo?.challan_number}. Received: ${totals.received} units.`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  };

  if (loading) return <div className="p-6 text-muted-foreground font-mono text-sm">Loading…</div>;

  return (
    <div data-testid="job-work-receipt-page">
      <PageHeader
        eyebrow="Job Work · Inward"
        title={receiptMeta ? `Receipt ${receiptMeta.receipt_number}` : "New Job Work Receipt"}
        description="Material returned by a job worker. Sent quantity is fixed by the original challan and cannot be edited here."
        actions={challanInfo?.status && <StatusBadge status={challanInfo.status} />}
      />

      <Card className="mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Against Challan" required>
            <Select
              value={selectedChallanId}
              disabled={isEdit}
              onChange={(e) => { setSelectedChallanId(e.target.value); loadChallanLines(e.target.value); }}
            >
              <option value="">Select challan…</option>
              {challans.map((c) => (
                <option key={c.id} value={c.id}>{c.challan_number} — {c.job_worker_name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Date" required>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label="Job Worker">
            <Input value={challanInfo?.job_worker_name || ""} disabled readOnly />
          </Field>
        </div>
      </Card>

      {loadingLines && <div className="text-sm text-muted-foreground font-mono px-2 mb-4">Loading challan lines…</div>}

      {!loadingLines && lines.length > 0 && (
        <Card className="mb-4" padded={false}>
          <div className="p-4 pb-0 text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Material Grid — Sent quantity is read-only
          </div>
          <div className="overflow-x-auto p-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-border">
                  <th className="p-2 w-8">#</th>
                  <th className="p-2 min-w-[180px]">Item</th>
                  <th className="p-2 w-24 text-right">Sent</th>
                  <th className="p-2 w-24 text-right">Prev. Recv.</th>
                  <th className="p-2 w-24 text-right">Pending</th>
                  <th className="p-2 w-28 text-right">Current Recv.</th>
                  <th className="p-2 w-24 text-right">Accepted</th>
                  <th className="p-2 w-24 text-right">Rejected</th>
                  <th className="p-2 w-24 text-right">Scrap</th>
                  <th className="p-2 min-w-[140px]">Remarks</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l, idx) => (
                  <tr key={l.challan_item_id || idx} className="border-b border-border/60">
                    <td className="p-2 text-muted-foreground">{idx + 1}</td>
                    <td className="p-2">
                      <div className="text-sm text-foreground font-medium">{l.product_name}</div>
                      {l.sku && <div className="text-xs text-muted-foreground">{l.sku}</div>}
                    </td>
                    <td className="p-2 text-right font-mono tabular text-muted-foreground">{l.quantity_sent}</td>
                    <td className="p-2 text-right font-mono tabular text-muted-foreground">{l.quantity_already_received}</td>
                    <td className="p-2 text-right font-mono tabular text-foreground font-semibold">{l.quantity_pending}</td>
                    <td className="p-2">
                      <input
                        type="number" min="0" max={l.quantity_pending} step="any"
                        value={l.quantity_received}
                        onChange={(e) => setLine(idx, { quantity_received: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="number" min="0" step="any"
                        value={l.accepted_quantity}
                        placeholder="Auto"
                        onChange={(e) => setLine(idx, { accepted_quantity: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="number" min="0" step="any"
                        value={l.rejected_quantity}
                        onChange={(e) => setLine(idx, { rejected_quantity: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="number" min="0" step="any"
                        value={l.scrap_quantity}
                        onChange={(e) => setLine(idx, { scrap_quantity: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 text-right focus:border-primary focus:outline-none"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        value={l.remarks}
                        onChange={(e) => setLine(idx, { remarks: e.target.value })}
                        className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm px-2 focus:border-primary focus:outline-none"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="sticky bottom-0 border-t border-border bg-muted/60 px-4 py-3 flex justify-end gap-8 text-sm font-mono">
            <span className="text-muted-foreground">Received: <b className="text-foreground">{totals.received}</b></span>
            <span className="text-muted-foreground">Accepted: <b className="text-foreground">{totals.accepted}</b></span>
            <span className="text-muted-foreground">Rejected: <b className="text-foreground">{totals.rejected}</b></span>
            <span className="text-muted-foreground">Scrap: <b className="text-foreground">{totals.scrap}</b></span>
          </div>
        </Card>
      )}

      {!loadingLines && selectedChallanId && lines.length === 0 && (
        <Card className="mb-4">
          <div className="text-sm text-muted-foreground">This challan has no pending quantity left to receive.</div>
        </Card>
      )}

      <Card className="mb-4">
        <Field label="Remarks / Notes">
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </Card>

      <div className="flex flex-wrap items-center gap-2 pb-8">
        <PrimaryButton icon={Save} disabled={saving || lines.length === 0} onClick={save}>
          Save
        </PrimaryButton>
        <SecondaryButton icon={Printer} disabled={saving || pdfBusy || lines.length === 0} onClick={saveAndPrint}>
          Save & Print
        </SecondaryButton>
        {receiptMeta && (
          <>
            <SecondaryButton icon={Download} disabled={pdfBusy} onClick={downloadPdf}>PDF</SecondaryButton>
            <SecondaryButton icon={MessageCircle} onClick={whatsappShare}>WhatsApp</SecondaryButton>
            <SendEmailButton
              docType="job_work_receipt"
              docId={receiptMeta.id}
              docNumber={receiptMeta.receipt_number}
              defaultRecipientName={challanInfo?.job_worker_name}
            />
          </>
        )}
        <SecondaryButton icon={X} onClick={() => navigate("/job-work")}>Cancel</SecondaryButton>
      </div>
    </div>
  );
}
