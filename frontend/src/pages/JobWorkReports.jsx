import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, Card, StatusBadge, Spinner, EmptyState, SecondaryButton } from "@/components/ui-kit";
import { FileText, ArrowDownToLine, ClipboardList, CheckCircle2, AlertTriangle } from "lucide-react";

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
              job_worker_name: c.job_worker_name,
              product_name: it.product_name,
              quantity_sent: it.quantity,
              quantity_received: it.quantity_received,
              quantity_pending: it.quantity_pending,
              unit: it.uom,
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

  useEffect(() => { load(); }, [load]);

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
            onClick={() => navigate(`/job-work/reports/${t.key}`)}
          >
            {t.label}
          </SecondaryButton>
        ))}
      </div>

      <Card padded={false}>
        {loading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : rows.length === 0 ? (
          <EmptyState message="No records found" />
        ) : tab === "challans" ? (
          <ChallansTable rows={rows} navigate={navigate} />
        ) : tab === "receipts" ? (
          <ReceiptsTable rows={rows} navigate={navigate} />
        ) : (
          <MaterialTable rows={rows} showOverdue={tab !== "completed"} />
        )}
      </Card>
    </div>
  );
}

function Th({ children, right }) {
  return <th className={`p-3 text-xs font-mono uppercase tracking-wide text-muted-foreground ${right ? "text-right" : "text-left"}`}>{children}</th>;
}
function Td({ children, right, className = "" }) {
  return <td className={`p-3 text-sm ${right ? "text-right font-mono tabular" : ""} ${className}`}>{children}</td>;
}

function ChallansTable({ rows, navigate }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          <Th>Challan #</Th><Th>Date</Th><Th>Job Worker</Th><Th right>Items</Th><Th>Status</Th>
        </tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className="border-b border-border/60 hover:bg-muted/40 cursor-pointer"
              onClick={() => navigate(`/job-work/challans/${c.id}`)}>
              <Td className="font-medium text-foreground">{c.challan_number}</Td>
              <Td>{c.date}</Td>
              <Td>{c.job_worker_name}</Td>
              <Td right>{(c.items || []).length}</Td>
              <Td><StatusBadge status={c.status} /></Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReceiptsTable({ rows, navigate }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          <Th>Receipt #</Th><Th>Date</Th><Th>Against Challan</Th><Th>Job Worker</Th><Th>Status</Th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border/60 hover:bg-muted/40 cursor-pointer"
              onClick={() => navigate(`/job-work/receipts/${r.id}`)}>
              <Td className="font-medium text-foreground">{r.receipt_number}</Td>
              <Td>{r.date}</Td>
              <Td>{r.challan_number}</Td>
              <Td>{r.job_worker_name}</Td>
              <Td><StatusBadge status={r.status} /></Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MaterialTable({ rows, showOverdue }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead><tr className="border-b border-border">
          <Th>Challan #</Th><Th>Job Worker</Th><Th>Item</Th>
          <Th right>Sent</Th><Th right>Received</Th><Th right>Pending</Th>
          {showOverdue && <Th>Status</Th>}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.challan_id || r.id}-${i}`} className="border-b border-border/60">
              <Td className="font-medium text-foreground">{r.challan_number}</Td>
              <Td>{r.job_worker_name}</Td>
              <Td>{r.product_name}</Td>
              <Td right>{inr(r.quantity_sent)} {r.unit || ""}</Td>
              <Td right>{inr(r.quantity_received)}</Td>
              <Td right className="font-semibold text-foreground">{inr(r.quantity_pending)}</Td>
              {showOverdue && (
                <Td>{r.is_overdue ? <StatusBadge status="OVERDUE" /> : <StatusBadge status="PENDING" />}</Td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
