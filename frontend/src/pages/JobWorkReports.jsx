import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, Card, StatusBadge, Spinner, EmptyState, SecondaryButton } from "@/components/ui-kit";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import Modal from "@/components/Modal";
import useBulkSelect from "@/hooks/useBulkSelect";
import usePdfAction from "@/hooks/usePdfAction";
import {
  FileText, ArrowDownToLine, ClipboardList, CheckCircle2, AlertTriangle, Trash2, Download, Pencil,
  Search, Paperclip, Upload, X, Loader2,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const TABS = [
  { key: "challans", label: "Job Work Challans", icon: FileText },
  { key: "receipts", label: "Job Work Receipts", icon: ArrowDownToLine },
  { key: "pending", label: "Pending Job Work", icon: ClipboardList },
  { key: "completed", label: "Completed Job Work", icon: CheckCircle2 },
  { key: "overdue", label: "Overdue Job Work", icon: AlertTriangle },
];

export default function JobWorkReports() {
  const { tab = "challans" } = useParams();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const { run: runPdf, busyId: pdfBusyId } = usePdfAction();
  const [attachTarget, setAttachTarget] = useState(null); // { kind: 'challans'|'receipts', id, label }

  const [filters, setFilters] = useState({ q: "", jobWorkerId: "", productId: "", fromDate: "", toDate: "" });
  const resetFilters = () => setFilters({ q: "", jobWorkerId: "", productId: "", fromDate: "", toDate: "" });

  const load = useCallback(() => {
    setLoading(true);
    const endpoints = {
      challans: "/job-work/challans?limit=500",
      receipts: "/job-work/receipts?limit=500",
      pending: "/job-work/reports/pending",
      completed: "/job-work/reports/completed",
      overdue: "/job-work/reports/overdue",
    };
    api.get(endpoints[tab] || endpoints.challans)
      .then((res) => {
        const data = res.data;
        if (tab === "completed") {
          // Completed challans come back as headers with a nested `items`
          // array (like /challans), not flat sent/received/pending rows —
          // flatten to one row per line item to match the other material tabs.
          const flat = (Array.isArray(data) ? data : []).flatMap((c) =>
            (c.items || []).map((it) => ({
              challan_id: c.id,
              challan_number: c.challan_number,
              date: c.date,
              job_worker_id: c.job_worker_id,
              job_worker_name: c.job_worker_name,
              product_id: it.product_id,
              product_name: it.product_name,
              quantity_sent: it.quantity,
              quantity_received: it.quantity_received,
              quantity_pending: it.quantity_pending,
              unit: it.uom,
              rate: it.rate,
            }))
          );
          setRows(flat);
        } else {
          setRows(Array.isArray(data) ? data : data.items || []);
        }
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [tab]);

  useEffect(() => { load(); resetFilters(); }, [load]);

  // Dropdown options are derived straight from the currently loaded rows
  // (not a separate API call) so they always match what's actually on
  // screen for this tab and never drift from server-side master data.
  const jobWorkerOptions = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      if (r.job_worker_id && !map.has(r.job_worker_id)) map.set(r.job_worker_id, r.job_worker_name);
    }
    return Array.from(map, ([id, name]) => ({ id, name })).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [rows]);

  const productOptions = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const items = r.items || [r];
      for (const it of items) {
        if (it.product_id && !map.has(it.product_id)) map.set(it.product_id, it.product_name);
      }
    }
    return Array.from(map, ([id, name]) => ({ id, name })).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [rows]);

  const filteredRows = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filters.jobWorkerId && r.job_worker_id !== filters.jobWorkerId) return false;
      if (filters.productId) {
        const items = r.items || [r];
        if (!items.some((it) => it.product_id === filters.productId)) return false;
      }
      if (filters.fromDate && (!r.date || r.date < filters.fromDate)) return false;
      if (filters.toDate && (!r.date || r.date > filters.toDate)) return false;
      if (q) {
        const items = r.items || [r];
        const haystack = [
          r.challan_number, r.receipt_number, r.job_worker_name,
          ...items.map((it) => it.product_name),
        ].filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [rows, filters]);

  // Bulk selection only makes sense on Challans/Receipts (real records) and
  // Pending (one row per challan line-item, but each still traces back to a
  // real challan via challan_id) — Completed/Overdue stay derived-only.
  // Pending rows have no row-level `id`, so select by challan_id instead and
  // dedupe: a challan with several pending line items produces several rows
  // here, all pointing at the same challan.
  const selectableRows =
    tab === "pending"
      ? Array.from(new Map(filteredRows.map((r) => [r.challan_id, { id: r.challan_id, challan_number: r.challan_number }])).values())
      : tab === "challans" || tab === "receipts"
      ? filteredRows
      : [];
  const sel = useBulkSelect(selectableRows);

  // Cancel is still offered as a fallback for the one status delete_challan
  // still refuses: an already-CANCELLED challan (409 — nothing left to
  // reverse/cancel again). Everything else (Draft/Pending/Partial/Completed)
  // now deletes directly — a Partial/Completed challan cascades: every
  // receipt logged against it is deleted first (each reversing its own
  // inward return), then the challan's full original outward movement is
  // reversed, then the challan itself. See backend delete_challan.
  const downloadChallanPdf = (row) =>
    runPdf(`/job-work/challans/${row.id}/pdf`, `${row.challan_number}.pdf`, row.id);

  const downloadReceiptPdf = (row) =>
    runPdf(`/job-work/receipts/${row.id}/pdf`, `${row.receipt_number}.pdf`, row.id);

  const cancelChallan = async (id, label) => {
    try {
      await api.post(`/job-work/challans/${id}/cancel`);
      toast.success(`${label} cancelled`);
      sel.clear();
      load();
    } catch (e) {
      console.error("Cancel failure:", e);
      toast.error(formatApiErrorDetail(null, e));
    }
  };

  const deleteOne = async (row) => {
    const challanBased = tab === "challans" || tab === "pending";
    const id = challanBased ? (row.challan_id || row.id) : row.id;
    const endpoint = challanBased ? `/job-work/challans/${id}` : `/job-work/receipts/${row.id}`;
    const label = challanBased ? row.challan_number : row.receipt_number;
    const warning = challanBased
      ? `Delete ${label}? If material receipts have already been logged against it, they'll be deleted too and all stock movements reversed. This cannot be undone.`
      : `Delete ${label}? This cannot be undone.`;
    if (!window.confirm(warning)) return;
    try {
      const { data } = await api.delete(endpoint);
      const skipped = data?._stock_reversal_skipped;
      if (skipped?.length) {
        toast.warning(`${label} deleted, but stock could not be reversed for ${skipped.length} line(s) — the linked product no longer exists.`);
      } else {
        toast.success(`${label} deleted`);
      }
      sel.clear();
      load();
    } catch (e) {
      if (challanBased && e.response?.status === 409) {
        console.error("Delete failure (offering cancel):", e);
        if (window.confirm(`${formatApiErrorDetail(null, e)}\n\nCancel it instead?`)) {
          await cancelChallan(id, label);
        }
        return;
      }
      console.error("Delete failure:", e);
      toast.error(formatApiErrorDetail(null, e));
    }
  };

  // Confirmation already happens once in BulkDeleteBar before onDelete (this
  // function) is even called — no second confirm() here, that would double-prompt.
  const bulkDelete = async () => {
    const challanBased = tab === "challans" || tab === "pending";
    const endpoint = challanBased ? "/job-work/challans" : "/job-work/receipts";
    let skippedLineCount = 0;
    const { ok, failed, firstError, failedIds } = await sel.runDelete(
      (id) => api.delete(`${endpoint}/${id}`).then(({ data }) => {
        if (data?._stock_reversal_skipped?.length) skippedLineCount += data._stock_reversal_skipped.length;
      }),
      { reload: load }
    );
    const noun = challanBased ? "challan" : "receipt";
    if (skippedLineCount) {
      toast.warning(`Stock could not be reversed for ${skippedLineCount} line(s) across the deleted challans — the linked product no longer exists.`);
    }
    if (failed) {
      if (firstError) console.error("Bulk delete failure:", firstError);
      if (challanBased && firstError?.response?.status === 409) {
        if (window.confirm(`Deleted ${ok}, failed ${failed} — ${formatApiErrorDetail(null, firstError)}\n\nCancel the ${failed} that couldn't be deleted instead?`)) {
          const results = await Promise.allSettled(failedIds.map((id) => api.post(`/job-work/challans/${id}/cancel`)));
          const cancelled = results.filter((r) => r.status === "fulfilled").length;
          toast.success(`Cancelled ${cancelled} of ${failedIds.length} remaining challan${failedIds.length === 1 ? "" : "s"}`);
          load();
        }
      } else {
        toast.error(`Deleted ${ok}, failed ${failed} — ${formatApiErrorDetail(null, firstError)}`);
      }
    } else {
      toast.success(`Deleted ${ok} ${noun}${ok === 1 ? "" : "s"}`);
    }
  };

  return (
    <div data-testid="job-work-reports-page">
      <PageHeader
        eyebrow="Job Work · Reports"
        title="Job Work Reports"
        description="Separate menus — challans, receipts, and material status are never mixed in one table."
      />

      <div className="flex flex-wrap gap-2 mb-4">
        {TABS.map((t) => (
          <SecondaryButton
            key={t.key}
            icon={t.icon}
            className={tab === t.key ? "!border-primary !text-primary" : ""}
            onClick={() => { sel.clear(); navigate(`/job-work/reports/${t.key}`); }}
          >
            {t.label}
          </SecondaryButton>
        ))}
      </div>

      <FilterBar
        filters={filters}
        setFilters={setFilters}
        jobWorkerOptions={jobWorkerOptions}
        productOptions={productOptions}
        onClear={resetFilters}
      />

      <Card padded={false}>
        {loading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : filteredRows.length === 0 ? (
          <EmptyState message={rows.length === 0 ? "No records found" : "No records match these filters"} />
        ) : tab === "challans" ? (
          <ChallansTable rows={filteredRows} navigate={navigate} sel={sel} onDeleteOne={deleteOne} onDownloadPdf={downloadChallanPdf} pdfBusyId={pdfBusyId}
            onAttach={(c) => setAttachTarget({ kind: "challans", id: c.id, label: c.challan_number })} />
        ) : tab === "receipts" ? (
          <ReceiptsTable rows={filteredRows} navigate={navigate} sel={sel} onDeleteOne={deleteOne} onDownloadPdf={downloadReceiptPdf} pdfBusyId={pdfBusyId}
            onAttach={(r) => setAttachTarget({ kind: "receipts", id: r.id, label: r.receipt_number })} />
        ) : (
          <MaterialTable
            rows={filteredRows}
            showOverdue={tab !== "completed"}
            sel={tab === "pending" ? sel : null}
            onDeleteOne={tab === "pending" ? deleteOne : null}
            navigate={navigate}
          />
        )}
      </Card>

      {attachTarget && (
        <AttachmentsModal
          kind={attachTarget.kind}
          id={attachTarget.id}
          label={attachTarget.label}
          onClose={() => setAttachTarget(null)}
        />
      )}

      {(tab === "challans" || tab === "receipts" || tab === "pending") && (
        <BulkDeleteBar
          count={sel.count}
          deleting={sel.deleting}
          onClear={sel.clear}
          onDelete={bulkDelete}
          noun={tab === "receipts" ? "receipt" : "challan"}
        />
      )}
    </div>
  );
}

function Th({ children, right }) {
  return <th className={`p-3 text-xs font-mono uppercase tracking-wide text-muted-foreground ${right ? "text-right" : "text-left"}`}>{children}</th>;
}
function Td({ children, right, className = "" }) {
  return <td className={`p-3 text-sm ${right ? "text-right font-mono tabular" : ""} ${className}`}>{children}</td>;
}

function FilterBar({ filters, setFilters, jobWorkerOptions, productOptions, onClear }) {
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }));
  const active = filters.q || filters.jobWorkerId || filters.productId || filters.fromDate || filters.toDate;
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <div className="relative flex-1 min-w-[220px] max-w-md">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
        <input
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder="Search challan #, job worker, item…"
          className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted/40 border border-border rounded-md focus:outline-none focus:border-primary"
        />
      </div>
      <select
        value={filters.jobWorkerId}
        onChange={(e) => set({ jobWorkerId: e.target.value })}
        className="text-xs border border-border rounded-md px-2 py-1.5 bg-card max-w-[170px]"
      >
        <option value="">All Job Workers</option>
        {jobWorkerOptions.map((jw) => <option key={jw.id} value={jw.id}>{jw.name}</option>)}
      </select>
      <select
        value={filters.productId}
        onChange={(e) => set({ productId: e.target.value })}
        className="text-xs border border-border rounded-md px-2 py-1.5 bg-card max-w-[170px]"
      >
        <option value="">All Products</option>
        {productOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <input
        type="date" value={filters.fromDate} onChange={(e) => set({ fromDate: e.target.value })}
        title="From date" className="text-xs border border-border rounded-md px-2 py-1.5 bg-card"
      />
      <span className="text-xs text-muted-foreground">to</span>
      <input
        type="date" value={filters.toDate} onChange={(e) => set({ toDate: e.target.value })}
        title="To date" className="text-xs border border-border rounded-md px-2 py-1.5 bg-card"
      />
      {active && (
        <button onClick={onClear} className="flex items-center gap-1 text-xs px-2 py-1.5 text-muted-foreground hover:text-destructive">
          <X className="w-3.5 h-3.5" /> Clear
        </button>
      )}
    </div>
  );
}

function ChallansTable({ rows, navigate, sel, onDeleteOne, onDownloadPdf, pdfBusyId, onAttach }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          <th className="p-3 w-10">
            <SelectCheckbox checked={sel.allSelected} indeterminate={sel.someSelected} onChange={sel.toggleAll} label="Select all challans" />
          </th>
          <Th>Challan #</Th><Th>Date</Th><Th>Job Worker</Th><Th right>Qty</Th><Th right>Rate</Th><Th>Status</Th><Th right>Actions</Th>
        </tr></thead>
        <tbody>
          {rows.map((c) => {
            const items = c.items || [];
            const totalQty = items.reduce((s, it) => s + Number(it.quantity || 0), 0);
            const rates = items.map((it) => Number(it.rate || 0)).filter((r) => r > 0);
            const rateDisplay = rates.length === 0 ? "-" : rates.length === 1 || rates.every((r) => r === rates[0])
              ? inr(rates[0])
              : `${inr(Math.min(...rates))} - ${inr(Math.max(...rates))}`;
            return (
              <tr key={c.id} className="border-b border-border/60 hover:bg-muted/40 cursor-pointer"
                onClick={() => navigate(`/job-work/challans/${c.id}`)}>
                <td className="p-3" onClick={(e) => e.stopPropagation()}>
                  <SelectCheckbox checked={sel.isSelected(c.id)} onChange={() => sel.toggle(c.id)} label={`Select ${c.challan_number}`} />
                </td>
                <Td className="font-medium text-foreground">{c.challan_number}</Td>
                <Td>{c.date}</Td>
                <Td>{c.job_worker_name}</Td>
                <Td right>{inr(totalQty)}</Td>
                <Td right>{rateDisplay}</Td>
                <Td><StatusBadge status={c.status} /></Td>
                <Td right>
                  <div className="flex items-center justify-end gap-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/job-work/challans/${c.id}`); }}
                      title="Edit challan"
                      className="text-muted-foreground hover:text-primary"
                    >
                      <Pencil className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDownloadPdf(c); }}
                      title="Download PDF"
                      disabled={pdfBusyId === c.id}
                      className="text-muted-foreground hover:text-primary disabled:opacity-50"
                    >
                      <Download className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onAttach(c); }}
                      title="Attachments"
                      className="relative text-muted-foreground hover:text-primary"
                    >
                      <Paperclip className="w-4 h-4 inline" />
                      {(c.attachments || []).length > 0 && (
                        <span className="absolute -top-1.5 -right-1.5 bg-primary text-primary-foreground text-[9px] leading-none rounded-full w-3.5 h-3.5 flex items-center justify-center">
                          {c.attachments.length}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteOne(c); }}
                      title="Delete challan"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 inline" />
                    </button>
                  </div>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ReceiptsTable({ rows, navigate, sel, onDeleteOne, onDownloadPdf, pdfBusyId, onAttach }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          <th className="p-3 w-10">
            <SelectCheckbox checked={sel.allSelected} indeterminate={sel.someSelected} onChange={sel.toggleAll} label="Select all receipts" />
          </th>
          <Th>Receipt #</Th><Th>Date</Th><Th>Against Challan</Th><Th>Job Worker</Th>
          <Th right>Qty Received</Th><Th right>Rate</Th><Th>Status</Th><Th right>Actions</Th>
        </tr></thead>
        <tbody>
          {rows.map((r) => {
            const items = r.items || [];
            const totalQty = items.reduce((s, it) => s + Number(it.quantity_received || 0), 0);
            const rates = items.map((it) => Number(it.rate || 0)).filter((v) => v > 0);
            const rateDisplay = rates.length === 0 ? "-" : rates.every((v) => v === rates[0])
              ? inr(rates[0])
              : `${inr(Math.min(...rates))} - ${inr(Math.max(...rates))}`;
            return (
              <tr key={r.id} className="border-b border-border/60 hover:bg-muted/40 cursor-pointer"
                onClick={() => navigate(`/job-work/receipts/${r.id}`)}>
                <td className="p-3" onClick={(e) => e.stopPropagation()}>
                  <SelectCheckbox checked={sel.isSelected(r.id)} onChange={() => sel.toggle(r.id)} label={`Select ${r.receipt_number}`} />
                </td>
                <Td className="font-medium text-foreground">{r.receipt_number}</Td>
                <Td>{r.date}</Td>
                <Td>{r.challan_number}</Td>
                <Td>{r.job_worker_name}</Td>
                <Td right>{inr(totalQty)}</Td>
                <Td right>{rateDisplay}</Td>
                <Td><StatusBadge status={r.status} /></Td>
                <Td right>
                  <div className="flex items-center justify-end gap-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/job-work/receipts/${r.id}`); }}
                      title="Edit receipt"
                      className="text-muted-foreground hover:text-primary"
                    >
                      <Pencil className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDownloadPdf(r); }}
                      title="Download PDF"
                      disabled={pdfBusyId === r.id}
                      className="text-muted-foreground hover:text-primary disabled:opacity-50"
                    >
                      <Download className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onAttach(r); }}
                      title="Attachments"
                      className="relative text-muted-foreground hover:text-primary"
                    >
                      <Paperclip className="w-4 h-4 inline" />
                      {(r.attachments || []).length > 0 && (
                        <span className="absolute -top-1.5 -right-1.5 bg-primary text-primary-foreground text-[9px] leading-none rounded-full w-3.5 h-3.5 flex items-center justify-center">
                          {r.attachments.length}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteOne(r); }}
                      title="Delete receipt"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 inline" />
                    </button>
                  </div>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MaterialTable({ rows, showOverdue, sel, onDeleteOne, navigate }) {
  const selectable = !!sel;
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          {selectable && (
            <th className="p-3 w-10">
              <SelectCheckbox checked={sel.allSelected} indeterminate={sel.someSelected} onChange={sel.toggleAll} label="Select all challans" />
            </th>
          )}
          <Th>Challan #</Th><Th>Job Worker</Th><Th>Item</Th>
          <Th right>Sent</Th><Th right>Received</Th><Th right>Pending</Th><Th right>Rate</Th>
          {showOverdue && <Th>Status</Th>}
          {selectable && <Th right>Actions</Th>}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.challan_id || r.id}-${i}`} className="border-b border-border/60">
              {selectable && (
                <td className="p-3">
                  <SelectCheckbox checked={sel.isSelected(r.challan_id)} onChange={() => sel.toggle(r.challan_id)} label={`Select ${r.challan_number}`} />
                </td>
              )}
              <Td className="font-medium text-foreground">{r.challan_number}</Td>
              <Td>{r.job_worker_name}</Td>
              <Td>{r.product_name}</Td>
              <Td right>{inr(r.quantity_sent)} {r.unit || ""}</Td>
              <Td right>{inr(r.quantity_received)}</Td>
              <Td right className="font-semibold text-foreground">{inr(r.quantity_pending)}</Td>
              <Td right>{r.rate ? inr(r.rate) : "-"}</Td>
              {showOverdue && (
                <Td>{r.is_overdue ? <StatusBadge status="OVERDUE" /> : <StatusBadge status="PENDING" />}</Td>
              )}
              {selectable && (
                <Td right>
                  <div className="flex items-center justify-end gap-3">
                    <button
                      onClick={() => navigate(`/job-work/challans/${r.challan_id}`)}
                      title="Edit challan"
                      className="text-muted-foreground hover:text-primary"
                    >
                      <Pencil className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={() => onDeleteOne({ challan_id: r.challan_id, challan_number: r.challan_number })}
                      title="Delete challan"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 inline" />
                    </button>
                  </div>
                </Td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Attach scanned/signed acknowledgement copies (or any supporting document)
// to a challan or receipt. Reuses the same generic /uploads/document
// endpoint the Warehouse module uses, then links the returned path onto the
// challan/receipt row via /job-work/<kind>/<id>/attachments.
function AttachmentsModal({ kind, id, label, onClose }) {
  const [attachments, setAttachments] = useState(null); // null = loading
  const [uploading, setUploading] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const path = kind === "challans" ? `/job-work/challans/${id}` : `/job-work/receipts/${id}`;
    api.get(path).then((res) => {
      const data = kind === "challans" ? res.data : (res.data.items || []).find((r) => r.id === id) || res.data;
      setAttachments(data.attachments || []);
    }).catch(() => setAttachments([]));
  }, [kind, id]);

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/uploads/document", fd);
      const { data: attachment } = await api.post(`/job-work/${kind}/${id}/attachments`, {
        path: data.path, name: data.name || file.name, size: data.size, content_type: data.content_type,
      });
      setAttachments((prev) => [...(prev || []), attachment]);
      toast.success("Attachment uploaded");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const removeAttachment = async (attachmentId) => {
    if (!window.confirm("Remove this attachment?")) return;
    try {
      await api.delete(`/job-work/${kind}/${id}/attachments/${attachmentId}`);
      setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not remove attachment");
    }
  };

  const downloadAttachment = async (a) => {
    setDownloadingId(a.id);
    try {
      const res = await api.get(`/files/${a.path}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.name || "document";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Could not download file");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <Modal open onClose={onClose} title={`Attachments — ${label}`} icon={Paperclip} size="sm">
      <div className="space-y-3">
        <label className={`flex items-center justify-center gap-2 rounded-md border border-dashed border-border px-3.5 py-3 text-sm font-medium text-foreground cursor-pointer hover:border-primary hover:bg-primary/5 ${uploading ? "pointer-events-none opacity-60" : ""}`}>
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4 text-muted-foreground" />}
          {uploading ? "Uploading…" : "Upload scanned/signed PDF or photo"}
          <input ref={fileInputRef} type="file" accept="image/*,application/pdf" className="hidden" onChange={onPickFile} disabled={uploading} />
        </label>

        {attachments === null ? (
          <div className="flex justify-center py-6"><Spinner /></div>
        ) : attachments.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-4">No attachments yet</div>
        ) : (
          <ul className="divide-y divide-border border border-border rounded-md">
            {attachments.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm text-foreground truncate">{a.name}</div>
                  <div className="text-xs text-muted-foreground">{fmtSize(a.size)}</div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => downloadAttachment(a)}
                    disabled={downloadingId === a.id}
                    title="Download"
                    className="text-muted-foreground hover:text-primary disabled:opacity-50"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => removeAttachment(a.id)}
                    title="Remove"
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
