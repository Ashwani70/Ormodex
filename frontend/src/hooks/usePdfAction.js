import { useState, useCallback } from "react";
import { toast } from "sonner";
import { downloadPdf } from "@/lib/currency";
import { formatApiErrorDetail } from "@/lib/api";

/**
 * Shared state + handler for "Download PDF" buttons across document screens.
 *
 * Tracks which document is currently being fetched so the calling button can
 * disable itself, opens the PDF in a new tab, and shows a toast on failure.
 *
 * Usage:
 *   const { run, busyId } = usePdfAction();
 *   <button disabled={busyId === row.id}
 *           onClick={() => run(`/invoices/${row.id}/pdf`, `${row.number}.pdf`, row.id)}>
 *
 * @returns {{ run: (endpoint: string, filename: string, id?: string) => Promise<void>,
 *            busyId: string|null, busy: boolean }}
 */
export default function usePdfAction() {
  const [busyId, setBusyId] = useState(null);

  const run = useCallback(async (endpoint, filename, id = "__single__") => {
    setBusyId(id);
    try {
      await downloadPdf(endpoint, filename, { newTab: true });
    } catch (err) {
      // With responseType: "blob" the error body is also a Blob, so the JSON
      // {detail} has to be read out of it before formatting.
      let detail;
      const data = err.response?.data;
      if (data instanceof Blob) {
        try { detail = JSON.parse(await data.text())?.detail; } catch { /* not JSON */ }
      } else {
        detail = data?.detail;
      }
      toast.error(formatApiErrorDetail(detail) || "Could not generate PDF.");
    } finally {
      setBusyId(null);
    }
  }, []);

  return { run, busyId, busy: busyId !== null };
}
