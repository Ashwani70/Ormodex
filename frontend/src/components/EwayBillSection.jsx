import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import QRCode from "react-qr-code";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PrimaryButton, SecondaryButton, Field, Input, Select, Spinner,
} from "@/components/ui-kit";
import usePdfAction from "@/hooks/usePdfAction";
import {
  Truck, QrCode, Download, Printer, RefreshCw, Pencil, ShieldAlert,
  AlertTriangle, CheckCircle2, Clock, FileWarning,
} from "lucide-react";

// e-Way Bill is mandatory above this consignment value (mirrors the backend).
const EWB_THRESHOLD = 50000;

const STATE_META = {
  GENERATED:     { label: "Generated",     cls: "bg-[#DCFCE7] text-[#166534]", Icon: CheckCircle2 },
  CANCELLED:     { label: "Cancelled",     cls: "bg-[#FEE2E2] text-[#991B1B]", Icon: ShieldAlert },
  EXPIRED:       { label: "Expired",       cls: "bg-[#FEF3C7] text-[#92400E]", Icon: FileWarning },
  NOT_GENERATED: { label: "Not Generated", cls: "bg-[#E4E4E7] text-[#3F3F46]", Icon: Truck },
};

const blankGenerate = () => ({
  transport_mode: "ROAD",
  distance_km: 100,
  vehicle_number: "",
  transporter_id: "",
  transporter_name: "",
  trans_doc_no: "",
});

/**
 * e-Way Bill section for the Sales Invoice page.
 *
 * Self-contained: given an `invoice`, it loads the latest e-Way Bill for that
 * invoice and renders the correct UI state (Not Generated / Processing /
 * Generated / Cancelled / Expired / Error) with the appropriate actions.
 * All calls go to the server-side /ewaybill/* endpoints (never NIC directly).
 */
export default function EwayBillSection({ invoice, onChanged }) {
  const { run: downloadEwbPdf, busy: pdfBusy } = usePdfAction();
  const [ewb, setEwb] = useState(null);          // current EWB doc or {status:"NOT_GENERATED"}
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);      // load/action error message
  const [processing, setProcessing] = useState(false);
  const [cfg, setCfg] = useState({ configured: false, environment: "sandbox" });

  const [genForm, setGenForm] = useState(blankGenerate);
  const [showGen, setShowGen] = useState(false);
  const [vehicleForm, setVehicleForm] = useState({ vehicle_number: "", from_place: "" });
  const [showVehicle, setShowVehicle] = useState(false);

  const invoiceId = invoice?.id;
  const invoiceValue = Number(invoice?.total ?? invoice?.subtotal ?? 0);
  const belowThreshold = invoiceValue <= EWB_THRESHOLD;

  const load = useCallback(async () => {
    if (!invoiceId) return;
    setLoading(true);
    setError(null);
    try {
      const [ewbRes, cfgRes] = await Promise.allSettled([
        api.get(`/ewaybill/by-invoice/${invoiceId}`),
        api.get(`/ewaybill/status`),
      ]);
      if (ewbRes.status === "fulfilled") setEwb(ewbRes.value.data);
      else setError(formatApiErrorDetail(ewbRes.reason?.response?.data?.detail) || "Failed to load e-Way Bill.");
      if (cfgRes.status === "fulfilled") setCfg(cfgRes.value.data);
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => { load(); }, [load]);

  const status = ewb?.status || "NOT_GENERATED";
  const meta = STATE_META[status] || STATE_META.NOT_GENERATED;

  const refreshAll = async () => { await load(); onChanged?.(); };

  // ── Actions ────────────────────────────────────────────────────────────────
  const handleGenerate = async (e) => {
    e?.preventDefault?.();
    if (genForm.transport_mode === "ROAD" && !genForm.vehicle_number.trim()) {
      return toast.error("Vehicle number is required for road transport.");
    }
    if (!(Number(genForm.distance_km) > 0)) return toast.error("Distance must be greater than 0.");
    setProcessing(true);
    setError(null);
    try {
      const { data } = await api.post(`/ewaybill/generate`, {
        invoice_id: invoiceId,
        transport_mode: genForm.transport_mode,
        distance_km: Number(genForm.distance_km),
        vehicle_number: genForm.vehicle_number.trim() || null,
        transporter_id: genForm.transporter_id.trim() || null,
        transporter_name: genForm.transporter_name.trim() || null,
        trans_doc_no: genForm.trans_doc_no.trim() || null,
      });
      setEwb(data);
      setShowGen(false);
      setGenForm(blankGenerate());
      toast.success(`e-Way Bill ${data.ewb_number} generated${data.simulated ? " (sandbox)" : ""}.`);
      onChanged?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      // The generate endpoint returns {message, errors:[...]} for validation.
      if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
        setError(`${detail.message}: ${detail.errors.join("; ")}`);
        toast.error(detail.message);
      } else {
        const msg = formatApiErrorDetail(detail) || "Failed to generate e-Way Bill.";
        setError(msg);
        toast.error(msg);
      }
    } finally {
      setProcessing(false);
    }
  };

  const handleUpdateVehicle = async (e) => {
    e?.preventDefault?.();
    if (!vehicleForm.vehicle_number.trim()) return toast.error("Enter the new vehicle number.");
    if (!vehicleForm.from_place.trim()) return toast.error("Enter the current place.");
    setProcessing(true);
    try {
      await api.post(`/ewaybill/update-vehicle`, {
        ewb_number: ewb.ewb_number,
        vehicle_number: vehicleForm.vehicle_number.trim(),
        from_place: vehicleForm.from_place.trim(),
        transport_mode: ewb.transport_mode || "ROAD",
      });
      toast.success("Vehicle number updated.");
      setShowVehicle(false);
      setVehicleForm({ vehicle_number: "", from_place: "" });
      await refreshAll();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to update vehicle.");
    } finally {
      setProcessing(false);
    }
  };

  const handleExtend = async () => {
    const place = window.prompt("Current place of the consignment (for validity extension):");
    if (!place) return;
    setProcessing(true);
    try {
      await api.post(`/ewaybill/extend-validity`, {
        ewb_number: ewb.ewb_number,
        remaining_distance_km: Number(ewb.distance_km) || 10,
        from_place: place.trim(),
        transport_mode: ewb.transport_mode || "ROAD",
        reason_remark: "In transit",
      });
      toast.success("Validity extended.");
      await refreshAll();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to extend validity.");
    } finally {
      setProcessing(false);
    }
  };

  const handleCancel = async () => {
    if (!window.confirm(`Cancel e-Way Bill ${ewb.ewb_number}? This cannot be undone.`)) return;
    const remark = window.prompt("Reason for cancellation:", "Order cancelled") || "Cancelled by supplier";
    setProcessing(true);
    try {
      await api.post(`/ewaybill/cancel`, {
        ewb_number: ewb.ewb_number,
        reason_code: 2,
        reason_remark: remark,
      });
      toast.success("e-Way Bill cancelled.");
      await refreshAll();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to cancel e-Way Bill.");
    } finally {
      setProcessing(false);
    }
  };

  const downloadPdf = () => downloadEwbPdf(`/ewaybill/${ewb.ewb_number}/pdf`, `EWB-${ewb.ewb_number}.pdf`, ewb.ewb_number);
  const printPdf = () => window.open(`/api/ewaybill/${ewb.ewb_number}/pdf`, "_blank", "noopener");

  // ── Render ─────────────────────────────────────────────────────────────────
  const Header = (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <Truck className="w-4 h-4 text-primary" />
        <span className="font-mono text-xs uppercase tracking-wider font-bold text-foreground">e-Way Bill</span>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${meta.cls}`}>
          <meta.Icon className="w-3 h-3" /> {meta.label}
        </span>
        {!cfg.configured && (
          <span className="text-[10px] font-mono text-amber-600 uppercase">{cfg.environment} · simulated</span>
        )}
      </div>
      {ewb?.ewb_number && (
        <button onClick={refreshAll} title="Refresh" className="text-muted-foreground hover:text-foreground">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );

  return (
    <div className="border border-border rounded-md bg-card p-4 space-y-3 text-card-foreground">
      {Header}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground font-mono text-xs py-4">
          <Spinner className="w-4 h-4" /> Loading e-Way Bill…
        </div>
      ) : error && status === "NOT_GENERATED" ? (
        <div className="flex items-start gap-2 text-red-600 font-mono text-xs">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-px" /> {error}
        </div>
      ) : status === "NOT_GENERATED" ? (
        // ── Not Generated ──────────────────────────────────────────────────
        <div className="space-y-3">
          {belowThreshold ? (
            <p className="font-mono text-xs text-muted-foreground">
              Invoice value ₹{invoiceValue.toLocaleString("en-IN")} is at or below the ₹50,000 threshold —
              an e-Way Bill is not required.
            </p>
          ) : !showGen ? (
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono text-xs text-muted-foreground">
                No e-Way Bill generated for this invoice yet.
              </p>
              <PrimaryButton icon={Truck} onClick={() => setShowGen(true)}>Generate e-Way Bill</PrimaryButton>
            </div>
          ) : (
            <form onSubmit={handleGenerate} className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Transport Mode" required>
                  <Select value={genForm.transport_mode} onChange={(e) => setGenForm((p) => ({ ...p, transport_mode: e.target.value }))}>
                    <option value="ROAD">Road</option>
                    <option value="RAIL">Rail</option>
                    <option value="AIR">Air</option>
                    <option value="SHIP">Ship</option>
                  </Select>
                </Field>
                <Field label="Distance (km)" required>
                  <Input type="text" inputMode="decimal" min="1" step="1" value={genForm.distance_km}
                    onChange={(e) => setGenForm((p) => ({ ...p, distance_km: e.target.value }))} required />
                </Field>
                <Field label="Vehicle Number" required={genForm.transport_mode === "ROAD"} hint="e.g. MH12AB1234">
                  <Input value={genForm.vehicle_number} placeholder="MH12AB1234"
                    onChange={(e) => setGenForm((p) => ({ ...p, vehicle_number: e.target.value.toUpperCase() }))} />
                </Field>
                <Field label="Transporter Name">
                  <Input value={genForm.transporter_name} placeholder="e.g. VRL Logistics"
                    onChange={(e) => setGenForm((p) => ({ ...p, transporter_name: e.target.value }))} />
                </Field>
                <Field label="Transporter ID (GSTIN)">
                  <Input value={genForm.transporter_id} placeholder="15-char GSTIN / TRANSIN"
                    onChange={(e) => setGenForm((p) => ({ ...p, transporter_id: e.target.value.toUpperCase() }))} />
                </Field>
                <Field label="Transport Doc No.">
                  <Input value={genForm.trans_doc_no} placeholder="LR / RR / Airway no."
                    onChange={(e) => setGenForm((p) => ({ ...p, trans_doc_no: e.target.value }))} />
                </Field>
              </div>
              {error && (
                <div className="flex items-start gap-2 text-red-600 font-mono text-[11px]">
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-px" /> {error}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <SecondaryButton type="button" onClick={() => { setShowGen(false); setError(null); }}>Cancel</SecondaryButton>
                <PrimaryButton type="submit" icon={Truck} loading={processing}>
                  {processing ? "Generating…" : "Generate"}
                </PrimaryButton>
              </div>
            </form>
          )}
        </div>
      ) : (
        // ── Generated / Cancelled / Expired ───────────────────────────────
        <div className="space-y-3">
          {processing && (
            <div className="flex items-center gap-2 text-muted-foreground font-mono text-xs">
              <Spinner className="w-4 h-4" /> Processing…
            </div>
          )}
          <div className="flex flex-col sm:flex-row gap-4">
            {/* QR */}
            {ewb.qr_value && (
              <div className="flex flex-col items-center gap-1 flex-shrink-0">
                <div className="bg-white p-2 rounded-md border border-border">
                  <QRCode value={ewb.qr_value} size={96} />
                </div>
                <span className="text-[9px] font-mono uppercase text-muted-foreground flex items-center gap-1">
                  <QrCode className="w-3 h-3" /> Scan to verify
                </span>
              </div>
            )}
            {/* Details */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 font-mono text-xs flex-1">
              <Detail label="EWB Number" value={ewb.ewb_number} strong />
              <Detail label="Generated" value={ewb.ewb_date} />
              <Detail label="Valid Until" value={ewb.valid_until} danger={status === "EXPIRED"} />
              <Detail label="Distance" value={ewb.distance_km ? `${ewb.distance_km} km` : "—"} />
              <Detail label="Vehicle" value={ewb.vehicle_number || "—"} />
              <Detail label="Transport Mode" value={ewb.transport_mode || "—"} />
              <Detail label="Transporter" value={ewb.transporter_name || "—"} />
              <Detail label="Transporter ID" value={ewb.transporter_id || "—"} />
            </div>
          </div>

          {status === "EXPIRED" && (
            <div className="flex items-center gap-2 text-amber-700 font-mono text-[11px]">
              <Clock className="w-3.5 h-3.5" /> This e-Way Bill has expired. Extend its validity if the consignment is still in transit.
            </div>
          )}
          {status === "CANCELLED" && ewb.cancel_reason_remark && (
            <div className="flex items-center gap-2 text-red-600 font-mono text-[11px]">
              <ShieldAlert className="w-3.5 h-3.5" /> Cancelled: {ewb.cancel_reason_remark}
            </div>
          )}

          {/* Update-vehicle inline form */}
          {showVehicle && status === "GENERATED" && (
            <form onSubmit={handleUpdateVehicle} className="border-t border-border pt-3 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="New Vehicle Number" required hint="e.g. MH12AB1234">
                  <Input value={vehicleForm.vehicle_number} placeholder="MH12AB1234"
                    onChange={(e) => setVehicleForm((p) => ({ ...p, vehicle_number: e.target.value.toUpperCase() }))} required />
                </Field>
                <Field label="Current Place" required>
                  <Input value={vehicleForm.from_place} placeholder="e.g. Nashik"
                    onChange={(e) => setVehicleForm((p) => ({ ...p, from_place: e.target.value }))} required />
                </Field>
              </div>
              <div className="flex justify-end gap-2">
                <SecondaryButton type="button" onClick={() => setShowVehicle(false)}>Cancel</SecondaryButton>
                <PrimaryButton type="submit" icon={Pencil} loading={processing}>Update Vehicle</PrimaryButton>
              </div>
            </form>
          )}

          {/* Action bar */}
          {!showVehicle && (
            <div className="flex flex-wrap gap-2 border-t border-border pt-3">
              <SecondaryButton icon={Download} disabled={pdfBusy} onClick={downloadPdf}>Download PDF</SecondaryButton>
              <SecondaryButton icon={Printer} onClick={printPdf}>Print</SecondaryButton>
              {status === "GENERATED" && (
                <>
                  <SecondaryButton icon={Pencil} onClick={() => setShowVehicle(true)}>Update Vehicle</SecondaryButton>
                  <SecondaryButton icon={ShieldAlert} danger onClick={handleCancel}>Cancel EWB</SecondaryButton>
                </>
              )}
              {status === "EXPIRED" && (
                <SecondaryButton icon={Clock} onClick={handleExtend}>Extend Validity</SecondaryButton>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Detail({ label, value, strong, danger }) {
  return (
    <div className="flex justify-between gap-2 min-w-0">
      <span className="text-muted-foreground whitespace-nowrap">{label}</span>
      <span className={`truncate text-right ${danger ? "text-red-600 font-bold" : strong ? "text-foreground font-bold" : "text-foreground"}`}>
        {value || "—"}
      </span>
    </div>
  );
}
