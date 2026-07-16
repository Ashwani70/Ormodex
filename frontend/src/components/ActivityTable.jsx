import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui-kit";
import {
  Search,
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ChevronLeft,
  ChevronRight,
  Eye,
} from "lucide-react";

// Activity table for the dashboard. Ships with sortable columns, status
// filtering, free-text search, client-side pagination, status badges, a
// sticky header and hover elevation — built on the Aurora tokens so it
// re-skins with the rest of the app.
//
// Data is mock placeholder for now; the row shape mirrors what a future
// /dashboard/activity endpoint would return so it can be wired without
// touching the markup.

const MOCK_ROWS = [
  { id: "ORD-1042", status: "PROCESSING", pendingApprovals: 2, approvalStatus: "PENDING", task: "Confirm dispatch slot", dueDate: "2026-06-21" },
  { id: "ORD-1041", status: "COMPLETED", pendingApprovals: 0, approvalStatus: "APPROVED", task: "Generate e-invoice", dueDate: "2026-06-19" },
  { id: "ORD-1040", status: "ON_HOLD", pendingApprovals: 1, approvalStatus: "PENDING", task: "Resolve credit limit", dueDate: "2026-06-20" },
  { id: "ORD-1039", status: "PROCESSING", pendingApprovals: 3, approvalStatus: "PENDING", task: "QC inspection", dueDate: "2026-06-22" },
  { id: "ORD-1038", status: "CANCELLED", pendingApprovals: 0, approvalStatus: "REJECTED", task: "Refund processing", dueDate: "2026-06-18" },
  { id: "ORD-1037", status: "COMPLETED", pendingApprovals: 0, approvalStatus: "APPROVED", task: "Update stock ledger", dueDate: "2026-06-17" },
  { id: "ORD-1036", status: "PROCESSING", pendingApprovals: 1, approvalStatus: "PENDING", task: "Pack & label", dueDate: "2026-06-23" },
  { id: "ORD-1035", status: "ON_HOLD", pendingApprovals: 2, approvalStatus: "PENDING", task: "Vendor confirmation", dueDate: "2026-06-24" },
  { id: "ORD-1034", status: "COMPLETED", pendingApprovals: 0, approvalStatus: "APPROVED", task: "Close work order", dueDate: "2026-06-16" },
  { id: "ORD-1033", status: "PROCESSING", pendingApprovals: 1, approvalStatus: "PENDING", task: "Raise GRN", dueDate: "2026-06-25" },
];

const STATUS_TONE = {
  PROCESSING: "info",
  COMPLETED: "success",
  ON_HOLD: "warning",
  CANCELLED: "danger",
};
const APPROVAL_TONE = {
  PENDING: "warning",
  APPROVED: "success",
  REJECTED: "danger",
};

const STATUS_OPTIONS = ["ALL", "PROCESSING", "COMPLETED", "ON_HOLD", "CANCELLED"];
const PAGE_SIZE = 5;

const pretty = (s) => s.replace(/_/g, " ");

function SortHeader({ label, field, sort, onSort, align = "left" }) {
  const active = sort.field === field;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ChevronUp : ChevronDown;
  return (
    <th className={`px-4 py-3 ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className={`inline-flex items-center gap-1 label-overline transition-colors hover:text-primary ${
          active ? "text-primary" : ""
        } ${align === "right" ? "flex-row-reverse" : ""}`}
      >
        {label}
        <Icon className="w-3 h-3" />
      </button>
    </th>
  );
}

export default function ActivityTable({ rows = MOCK_ROWS, loading = false }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sort, setSort] = useState({ field: "dueDate", dir: "asc" });
  const [page, setPage] = useState(0);

  const onSort = (field) => {
    setSort((s) =>
      s.field === field ? { field, dir: s.dir === "asc" ? "desc" : "asc" } : { field, dir: "asc" }
    );
    setPage(0);
  };

  const filtered = useMemo(() => {
    let out = rows;
    if (statusFilter !== "ALL") out = out.filter((r) => r.status === statusFilter);
    if (query.trim()) {
      const q = query.toLowerCase();
      out = out.filter(
        (r) => r.id.toLowerCase().includes(q) || r.task.toLowerCase().includes(q)
      );
    }
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...out].sort((a, b) => {
      const av = a[sort.field];
      const bv = b[sort.field];
      if (av === bv) return 0;
      return av > bv ? dir : -dir;
    });
  }, [rows, statusFilter, query, sort]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  return (
    <div
      className="bg-card border border-border overflow-hidden"
      style={{ borderRadius: "var(--radius)", boxShadow: "var(--shadow-md)" }}
    >
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground">Recent Activity</h3>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
              placeholder="Search orders or tasks…"
              aria-label="Search activity"
              className="h-9 w-48 sm:w-56 pl-8 pr-3 text-sm bg-background border border-input text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none transition-colors"
              style={{ borderRadius: "var(--radius-sm)" }}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(0);
            }}
            aria-label="Filter by status"
            className="h-9 px-3 text-sm bg-background border border-input text-foreground focus:border-primary focus:outline-none transition-colors"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === "ALL" ? "All statuses" : pretty(s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-muted text-muted-foreground">
            <tr className="border-b border-border">
              <SortHeader label="Order #" field="id" sort={sort} onSort={onSort} />
              <SortHeader label="Status" field="status" sort={sort} onSort={onSort} />
              <SortHeader label="Pending Approvals" field="pendingApprovals" sort={sort} onSort={onSort} align="right" />
              <SortHeader label="Approval Status" field="approvalStatus" sort={sort} onSort={onSort} />
              <th className="px-4 py-3 text-left label-overline">Upcoming Task</th>
              <SortHeader label="Due Date" field="dueDate" sort={sort} onSort={onSort} />
              <th className="px-4 py-3 text-right label-overline">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Loading skeleton rows
              Array.from({ length: PAGE_SIZE }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  {Array.from({ length: 7 }).map((__, j) => (
                    <td key={j} className="px-4 py-3.5">
                      <div className="h-4 bg-muted rounded animate-pulse" style={{ width: `${50 + ((i + j) % 4) * 12}%` }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : pageRows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground font-mono text-xs uppercase">
                  No matching activity
                </td>
              </tr>
            ) : (
              pageRows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-border last:border-0 hover:bg-muted/50 hover:shadow-[inset_3px_0_0_hsl(var(--primary))] transition-all duration-200 text-foreground"
                >
                  <td className="px-4 py-3.5 font-mono font-semibold text-primary">{r.id}</td>
                  <td className="px-4 py-3.5">
                    <Badge tone={STATUS_TONE[r.status] || "neutral"}>{pretty(r.status)}</Badge>
                  </td>
                  <td className="px-4 py-3.5 text-right tabular-nums">
                    {r.pendingApprovals > 0 ? (
                      <span className="font-semibold text-foreground">{r.pendingApprovals}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <Badge tone={APPROVAL_TONE[r.approvalStatus] || "neutral"}>{pretty(r.approvalStatus)}</Badge>
                  </td>
                  <td className="px-4 py-3.5 text-muted-foreground truncate max-w-[200px]" title={r.task}>{r.task}</td>
                  <td className="px-4 py-3.5 font-mono text-xs text-muted-foreground">{r.dueDate}</td>
                  <td className="px-4 py-3.5 text-right">
                    <button
                      type="button"
                      onClick={() => navigate("/sales-orders")}
                      title="View order"
                      aria-label={`View ${r.id}`}
                      className="w-7 h-7 inline-flex items-center justify-center border border-border bg-background text-muted-foreground hover:border-primary hover:text-primary transition-colors"
                      style={{ borderRadius: "var(--radius-sm)" }}
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && filtered.length > 0 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-border">
          <span className="text-xs text-muted-foreground font-mono">
            {safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              aria-label="Previous page"
              className="w-8 h-8 inline-flex items-center justify-center border border-border bg-background text-muted-foreground hover:border-primary hover:text-primary disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted-foreground transition-colors"
              style={{ borderRadius: "var(--radius-sm)" }}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs font-mono text-foreground px-2">
              {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              aria-label="Next page"
              className="w-8 h-8 inline-flex items-center justify-center border border-border bg-background text-muted-foreground hover:border-primary hover:text-primary disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted-foreground transition-colors"
              style={{ borderRadius: "var(--radius-sm)" }}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
