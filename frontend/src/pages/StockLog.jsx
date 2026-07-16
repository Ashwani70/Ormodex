import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FixedSizeList as List } from "react-window";
import {
  Search, RefreshCw, Download, FileSpreadsheet, Printer, Calendar,
  Tag, ArrowUpDown,
  X, Package, TrendingUp, TrendingDown, AlertTriangle, Clock3, Boxes,
  ChevronUp, ChevronDown, Trash2,
} from "lucide-react";
import api from "@/lib/api";
import { PageHeader, Skeleton, EmptyState } from "@/components/ui-kit";
import { useAuth } from "@/context/AuthContext";
import { isAdminRole } from "@/lib/navItems";

const ROW_HEIGHT = 34;
const HEADER_HEIGHT = 36;
const PAGE_SIZE = 200;

// [key, label, defaultWidth, align]
const DEFAULT_COLUMNS = [
  ["date", "Date", 92, "left"],
  ["time", "Time", 76, "left"],
  ["voucherNo", "Voucher No", 130, "left"],
  ["voucherTypeLabel", "Voucher Type", 140, "left"],
  ["productCode", "Product Code", 110, "left"],
  ["productName", "Product Name", 220, "left"],
  ["warehouse", "Warehouse", 110, "left"],
  ["batchNo", "Batch No", 90, "left"],
  ["serialNo", "Serial No", 90, "left"],
  ["unit", "Unit", 60, "left"],
  ["inQty", "In Qty", 90, "right"],
  ["outQty", "Out Qty", 90, "right"],
  ["runningBalance", "Running Balance", 120, "right"],
  ["rate", "Rate", 90, "right"],
  ["value", "Value", 110, "right"],
  ["costCentre", "Cost Centre", 100, "left"],
  ["user", "User", 110, "left"],
  ["status", "Status", 70, "left"],
];

const FROZEN_KEY = "productName";

function fmtNum(v, digits = 2) {
  if (v == null) return "—";
  return Number(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function StatCard({ icon: Icon, label, value, tone = "default", loading }) {
  const toneClasses = {
    default: "text-foreground",
    success: "text-emerald-600",
    danger: "text-red-600",
    warning: "text-amber-600",
  }[tone];
  return (
    <div className="bg-card border border-border rounded-md px-3 py-2 flex items-center gap-2.5 min-w-[140px]">
      <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" strokeWidth={1.75} />
      <div className="min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground truncate">{label}</div>
        {loading ? (
          <Skeleton className="h-4 w-16 mt-0.5" />
        ) : (
          <div className={`text-sm font-semibold tabular-nums ${toneClasses}`}>{value}</div>
        )}
      </div>
    </div>
  );
}

export default function StockLog() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = isAdminRole(user?.role);

  const [filters, setFilters] = useState({
    productId: "", warehouseId: "", fromDate: "", toDate: "",
    docType: "", userId: "", status: "all", q: "",
  });
  const [filterOptions, setFilterOptions] = useState({ products: [], warehouses: [], voucherTypes: [], users: [] });
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [summary, setSummary] = useState(null);
  const [sort, setSort] = useState({ by: "created_at", dir: "desc" });
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [columnWidths, setColumnWidths] = useState(() =>
    Object.fromEntries(DEFAULT_COLUMNS.map(([key, , w]) => [key, w]))
  );

  const searchInputRef = useRef(null);
  const listRef = useRef(null);
  const debounceRef = useRef(null);
  const resizingRef = useRef(null);
  const requestSeq = useRef(0);

  // ── Load filter dropdown options once ──────────────────────────────
  useEffect(() => {
    api.get("/stock-log/filters").then((r) => setFilterOptions(r.data)).catch(() => {});
  }, []);

  const queryParams = useMemo(() => {
    const p = {};
    if (filters.productId) p.product_id = filters.productId;
    if (filters.warehouseId) p.warehouse_id = filters.warehouseId;
    if (filters.fromDate) p.from_date = filters.fromDate;
    if (filters.toDate) p.to_date = filters.toDate;
    if (filters.docType) p.doc_type = filters.docType;
    if (filters.userId) p.user_id = filters.userId;
    if (filters.status && filters.status !== "all") p.status = filters.status;
    if (filters.q) p.q = filters.q;
    p.sort_by = sort.by;
    p.sort_dir = sort.dir;
    return p;
  }, [filters, sort]);

  const fetchPage = useCallback(async (pageNum, append) => {
    const seq = ++requestSeq.current;
    if (append) setLoadingMore(true); else setLoading(true);
    try {
      const { data } = await api.get("/stock-log/entries", {
        params: { ...queryParams, page: pageNum, limit: PAGE_SIZE },
      });
      if (seq !== requestSeq.current) return;
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setPage(pageNum);
    } catch {
      if (seq !== requestSeq.current) return;
      if (!append) { setItems([]); setTotal(0); }
    } finally {
      if (seq === requestSeq.current) { setLoading(false); setLoadingMore(false); }
    }
  }, [queryParams]);

  const fetchSummary = useCallback(async () => {
    try {
      const { data } = await api.get("/stock-log/summary", { params: queryParams });
      setSummary(data);
    } catch {
      setSummary(null);
    }
  }, [queryParams]);

  // Debounced re-fetch whenever filters/sort change (250ms, matches the
  // global search palette's convention elsewhere in this app).
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setSelectedIndex(-1);
      fetchPage(1, false);
      fetchSummary();
    }, 250);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryParams]);

  const loadMore = useCallback(() => {
    if (loadingMore || loading || items.length >= total) return;
    fetchPage(page + 1, true);
  }, [loadingMore, loading, items.length, total, page, fetchPage]);

  // ── Row selection / navigation ──────────────────────────────────────
  const openVoucher = useCallback(async (row) => {
    if (!row?.voucherType) return;
    try {
      const { data } = await api.get(`/stock-log/voucher/${row.voucherType}/${row.sourceDocId || row.id}`);
      navigate(data.path);
    } catch {
      // No drill-down route for this voucher type — nothing to open.
    }
  }, [navigate]);

  const toggleSelectRow = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  // ── Delete / bulk delete (admin-only cleanup of junk/test entries) ──────
  // Rows tied to a v2-ledger posting are refused server-side (see
  // stock_log.py) rather than silently corrupting stock_ledger_entries
  // consistency — those come back in `skipped` and are surfaced to the user.
  const deleteSelected = useCallback(async () => {
    if (!isAdmin || selectedIds.size === 0 || deleting) return;
    const ids = Array.from(selectedIds);
    const noun = ids.length === 1 ? "entry" : "entries";
    if (!window.confirm(`Delete ${ids.length} stock log ${noun}? This reverses stock quantity and cannot be undone.`)) return;
    setDeleting(true);
    try {
      const { data } = await api.post("/stock-log/entries/bulk-delete", { ids });
      if (data.skipped?.length) {
        window.alert(`${data.deleted} deleted. ${data.skipped.length} skipped (posted via the v2 ledger — reverse the source voucher instead).`);
      }
      setSelectedIds(new Set());
      setSelectedIndex(-1);
      fetchPage(1, false);
      fetchSummary();
    } catch (err) {
      window.alert(err?.response?.data?.detail || "Failed to delete entries");
    } finally {
      setDeleting(false);
    }
  }, [isAdmin, selectedIds, deleting, fetchPage, fetchSummary]);

  const deleteRow = useCallback(async (row) => {
    if (!isAdmin || deleting) return;
    if (!window.confirm("Delete this stock log entry? This reverses stock quantity and cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.delete(`/stock-log/entries/${row.id}`);
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(row.id); return next; });
      fetchPage(1, false);
      fetchSummary();
    } catch (err) {
      window.alert(err?.response?.data?.detail || "Failed to delete entry");
    } finally {
      setDeleting(false);
    }
  }, [isAdmin, deleting, fetchPage, fetchSummary]);

  // ── Keyboard shortcuts ───────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      const tag = document.activeElement?.tagName;
      const inInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (e.key === "F9") { e.preventDefault(); e.stopPropagation(); fetchPage(1, false); fetchSummary(); return; }
      if (e.key === "F4") { e.preventDefault(); e.stopPropagation(); document.getElementById("stocklog-product-filter")?.focus(); return; }
      if (e.key === "F5") { e.preventDefault(); e.stopPropagation(); document.getElementById("stocklog-warehouse-filter")?.focus(); return; }
      if (e.key === "F6") { e.preventDefault(); e.stopPropagation(); document.getElementById("stocklog-voucher-filter")?.focus(); return; }
      if (e.key === "F8") { e.preventDefault(); e.stopPropagation(); navigate("/inventory-reports"); return; }
      if (e.altKey && e.key === "F2") { e.preventDefault(); e.stopPropagation(); document.getElementById("stocklog-from-date")?.focus(); return; }
      // Shift variant must be checked BEFORE the plain Ctrl+F branch — both
      // match e.key === "f" (case-insensitively), so the more specific
      // (Shift-held) combo has to win or it's unreachable.
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "f") { e.preventDefault(); e.stopPropagation(); setShowAdvanced((v) => !v); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") { e.preventDefault(); e.stopPropagation(); searchInputRef.current?.focus(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "e") { e.preventDefault(); e.stopPropagation(); window.open(`${api.defaults.baseURL}/stock-log/export/excel?${new URLSearchParams(queryParams)}`, "_blank"); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") { e.preventDefault(); e.stopPropagation(); window.open(`${api.defaults.baseURL}/stock-log/export/pdf?${new URLSearchParams(queryParams)}`, "_blank"); return; }

      if (inInput) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIndex((i) => Math.min(i + 1, items.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIndex((i) => Math.max(i - 1, 0)); }
      if (e.key === "Enter" && selectedIndex >= 0) { e.preventDefault(); openVoucher(items[selectedIndex]); }
      if (e.key === " " && selectedIndex >= 0) { e.preventDefault(); toggleSelectRow(items[selectedIndex].id); }
      if (e.key === "Delete" && isAdmin) {
        e.preventDefault();
        if (selectedIds.size > 0) deleteSelected();
        else if (selectedIndex >= 0) deleteRow(items[selectedIndex]);
      }
      if (e.key === "Escape") { e.preventDefault(); navigate(-1); }
    };
    // Capture phase so this page's own F4/F5/F6/F8/F9 filter-focus shortcuts
    // win over the app-wide F-key voucher/module navigation registered in
    // Layout (useKeyboardShortcuts) — see that hook's docstring for the
    // capture-phase-wins precedence rule shared with useModuleShortcuts.
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [items, selectedIndex, selectedIds, isAdmin, openVoucher, toggleSelectRow, deleteSelected, deleteRow, queryParams, fetchPage, fetchSummary, navigate]);

  // Keep the virtualized list scrolled to the selected row.
  useEffect(() => {
    if (selectedIndex >= 0) listRef.current?.scrollToItem(selectedIndex, "smart");
  }, [selectedIndex]);

  const selectedRow = selectedIndex >= 0 ? items[selectedIndex] : null;

  // ── Column resize ─────────────────────────────────────────────────────
  const startResize = (key, e) => {
    e.preventDefault();
    resizingRef.current = { key, startX: e.clientX, startWidth: columnWidths[key] };
    const onMove = (ev) => {
      if (!resizingRef.current) return;
      const { key: k, startX, startWidth } = resizingRef.current;
      const next = Math.max(50, startWidth + (ev.clientX - startX));
      setColumnWidths((prev) => ({ ...prev, [k]: next }));
    };
    const onUp = () => {
      resizingRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const toggleSort = (key) => {
    setSort((prev) => (prev.by === key ? { by: key, dir: prev.dir === "asc" ? "desc" : "asc" } : { by: key, dir: "asc" }));
  };

  const totalWidth = DEFAULT_COLUMNS.reduce((s, [key]) => s + columnWidths[key], 0) + (isAdmin ? 44 : 0);

  return (
    <div data-testid="stocklog-page" className="flex flex-col h-[calc(100vh-6rem)]">
      <PageHeader
        eyebrow="Inventory"
        title="Stock Log"
        description="Real-time stock ledger — every inward and outward movement, with running balance."
      />

      {/* ── Header: filters + actions ─────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 mb-3 flex-shrink-0">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            ref={searchInputRef}
            value={filters.q}
            onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
            placeholder="Search everything… (Ctrl+F)"
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted/40 border border-border rounded-md focus:outline-none focus:border-primary"
          />
        </div>

        <select
          id="stocklog-product-filter"
          value={filters.productId}
          onChange={(e) => setFilters((f) => ({ ...f, productId: e.target.value }))}
          title="Product filter (F4)"
          className="text-xs border border-border rounded-md px-2 py-1.5 bg-card max-w-[160px]"
        >
          <option value="">All Products (F4)</option>
          {filterOptions.products.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <select
          id="stocklog-warehouse-filter"
          value={filters.warehouseId}
          onChange={(e) => setFilters((f) => ({ ...f, warehouseId: e.target.value }))}
          title="Warehouse filter (F5)"
          className="text-xs border border-border rounded-md px-2 py-1.5 bg-card max-w-[150px]"
        >
          <option value="">All Warehouses (F5)</option>
          {filterOptions.warehouses.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>

        <select
          id="stocklog-voucher-filter"
          value={filters.docType}
          onChange={(e) => setFilters((f) => ({ ...f, docType: e.target.value }))}
          title="Voucher type filter (F6)"
          className="text-xs border border-border rounded-md px-2 py-1.5 bg-card max-w-[150px]"
        >
          <option value="">All Voucher Types (F6)</option>
          {filterOptions.voucherTypes.map((v) => (
            <option key={v.value} value={v.value}>{v.label}</option>
          ))}
        </select>

        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          className="text-xs border border-border rounded-md px-2 py-1.5 bg-card"
        >
          <option value="all">All Movement</option>
          <option value="inward">Inward only</option>
          <option value="outward">Outward only</option>
        </select>

        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className={`flex items-center gap-1 text-xs px-2 py-1.5 border rounded-md ${showAdvanced ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground"}`}
          title="Advanced filters (Ctrl+Shift+F)"
        >
          <Calendar className="w-3.5 h-3.5" /> Date
        </button>

        <div className="flex items-center gap-1 ml-auto">
          <button onClick={() => { fetchPage(1, false); fetchSummary(); }} title="Refresh (F9)" className="p-1.5 border border-border rounded-md text-muted-foreground hover:text-primary hover:border-primary">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => window.open(`${api.defaults.baseURL}/stock-log/export/excel?${new URLSearchParams(queryParams)}`, "_blank")}
            title="Export Excel (Ctrl+E)" className="p-1.5 border border-border rounded-md text-muted-foreground hover:text-primary hover:border-primary"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => window.open(`${api.defaults.baseURL}/stock-log/export/pdf?${new URLSearchParams(queryParams)}`, "_blank")}
            title="Export PDF" className="p-1.5 border border-border rounded-md text-muted-foreground hover:text-primary hover:border-primary"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => window.print()}
            title="Print (Ctrl+P)" className="p-1.5 border border-border rounded-md text-muted-foreground hover:text-primary hover:border-primary"
          >
            <Printer className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div className="flex flex-wrap items-center gap-2 mb-3 p-2.5 bg-muted/30 border border-border rounded-md flex-shrink-0">
          <label className="text-[10px] font-mono uppercase text-muted-foreground">From</label>
          <input id="stocklog-from-date" type="date" value={filters.fromDate} onChange={(e) => setFilters((f) => ({ ...f, fromDate: e.target.value }))} className="text-xs border border-border rounded-md px-2 py-1 bg-card" />
          <label className="text-[10px] font-mono uppercase text-muted-foreground">To</label>
          <input type="date" value={filters.toDate} onChange={(e) => setFilters((f) => ({ ...f, toDate: e.target.value }))} className="text-xs border border-border rounded-md px-2 py-1 bg-card" />
          <button onClick={() => setFilters((f) => ({ ...f, fromDate: todayIso(), toDate: todayIso() }))} className="text-xs px-2 py-1 border border-border rounded-md text-muted-foreground hover:text-primary">Today</button>
          <select
            value={filters.userId}
            onChange={(e) => setFilters((f) => ({ ...f, userId: e.target.value }))}
            className="text-xs border border-border rounded-md px-2 py-1 bg-card"
          >
            <option value="">All Users</option>
            {filterOptions.users.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
          {(filters.fromDate || filters.toDate || filters.userId) && (
            <button
              onClick={() => setFilters((f) => ({ ...f, fromDate: "", toDate: "", userId: "" }))}
              className="text-xs px-2 py-1 text-muted-foreground hover:text-destructive flex items-center gap-1"
            >
              <X className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
      )}

      {/* ── Summary cards ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 mb-3 flex-shrink-0">
        <StatCard icon={Boxes} label="Opening Stock" value={fmtNum(summary?.openingStock, 0)} loading={!summary} />
        <StatCard icon={TrendingUp} label="Total Inward" value={fmtNum(summary?.totalInward, 0)} tone="success" loading={!summary} />
        <StatCard icon={TrendingDown} label="Total Outward" value={fmtNum(summary?.totalOutward, 0)} tone="danger" loading={!summary} />
        <StatCard icon={Package} label="Closing Stock" value={fmtNum(summary?.closingStock, 0)} loading={!summary} />
        <StatCard icon={Tag} label="Stock Value" value={`₹${fmtNum(summary?.stockValue, 0)}`} loading={!summary} />
        <StatCard icon={ArrowUpDown} label="Average Cost" value={`₹${fmtNum(summary?.averageCost)}`} loading={!summary} />
        <StatCard icon={AlertTriangle} label="Negative Stock" value={summary?.negativeStockCount ?? "—"} tone={summary?.negativeStockCount > 0 ? "warning" : "default"} loading={!summary} />
        <StatCard icon={Clock3} label="Pending Transfers" value={summary?.pendingTransfers ?? "—"} loading={!summary} />
      </div>

      {/* ── Grid + right panel ─────────────────────────────────────────── */}
      <div className="flex-1 flex gap-3 min-h-0">
        <div className="flex-1 min-w-0 border border-border rounded-md bg-card overflow-hidden flex flex-col">
          {loading && items.length === 0 ? (
            <div className="p-3"><Skeleton className="h-8 w-full mb-2" />{Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-[34px] w-full mb-px" />)}</div>
          ) : items.length === 0 ? (
            <EmptyState message="No stock movements match these filters" />
          ) : (
            <div className="flex-1 overflow-auto" style={{ minWidth: 0 }}>
              <div style={{ width: Math.max(totalWidth, 100), minWidth: "100%" }}>
                {/* Sticky header row */}
                <div
                  className="flex sticky top-0 z-10 bg-[#f8fafc] border-b border-border text-[11px] font-semibold text-muted-foreground select-none"
                  style={{ height: HEADER_HEIGHT }}
                >
                  {DEFAULT_COLUMNS.map(([key, label, , align], colIdx) => (
                    <div
                      key={key}
                      onClick={() => toggleSort(key)}
                      className={`relative flex items-center gap-1 px-2 cursor-pointer hover:bg-muted/60 flex-shrink-0 ${align === "right" ? "justify-end" : "justify-start"} ${key === FROZEN_KEY ? "sticky left-0 z-20 bg-[#f8fafc]" : ""}`}
                      style={{ width: columnWidths[key] }}
                    >
                      <span className="truncate">{label}</span>
                      {sort.by === key && (sort.dir === "asc" ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                      <div
                        onMouseDown={(e) => { e.stopPropagation(); startResize(key, e); }}
                        className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-primary/40"
                      />
                    </div>
                  ))}
                  {isAdmin && (
                    <div className="flex items-center justify-center px-2 flex-shrink-0" style={{ width: 44 }}>
                      <span className="truncate">Del</span>
                    </div>
                  )}
                </div>

                {/* Virtualized rows */}
                <List
                  ref={listRef}
                  height={Math.max(200, window.innerHeight - 420)}
                  itemCount={items.length}
                  itemSize={ROW_HEIGHT}
                  width={Math.max(totalWidth, 100)}
                  onItemsRendered={({ visibleStopIndex }) => {
                    if (visibleStopIndex >= items.length - 20) loadMore();
                  }}
                >
                  {({ index, style }) => {
                    const row = items[index];
                    const isSelected = index === selectedIndex;
                    const isChecked = selectedIds.has(row.id);
                    return (
                      <div
                        style={style}
                        onClick={() => setSelectedIndex(index)}
                        onDoubleClick={() => openVoucher(row)}
                        className={`flex text-[12px] border-b border-border/60 cursor-default
                          ${isSelected ? "bg-primary/10" : index % 2 === 0 ? "bg-card" : "bg-[#fafbfc]"}
                          hover:bg-[#f0fdfa]`}
                      >
                        {DEFAULT_COLUMNS.map(([key, , , align]) => {
                          let content = row[key];
                          if (key === "inQty") content = row.inQty > 0 ? fmtNum(row.inQty) : "";
                          else if (key === "outQty") content = row.outQty > 0 ? fmtNum(row.outQty) : "";
                          else if (key === "runningBalance") content = fmtNum(row.runningBalance, 2);
                          else if (key === "rate") content = row.rate != null ? fmtNum(row.rate) : "—";
                          else if (key === "value") content = row.value != null ? fmtNum(row.value) : "—";
                          else if (key === "status") {
                            content = (
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded-sm text-[9px] font-mono uppercase ${row.status === "IN" ? "bg-emerald-500/15 text-emerald-700" : "bg-red-500/15 text-red-700"}`}>
                                {row.status}
                              </span>
                            );
                          } else if (!content) content = "—";
                          return (
                            <div
                              key={key}
                              className={`flex items-center px-2 flex-shrink-0 truncate ${align === "right" ? "justify-end tabular-nums" : ""} ${key === FROZEN_KEY ? `sticky left-0 z-[5] ${isSelected ? "bg-primary/10" : index % 2 === 0 ? "bg-card" : "bg-[#fafbfc]"}` : ""}`}
                              style={{ width: columnWidths[key] }}
                              title={key === "productName" ? row.productName : undefined}
                            >
                              {key === "productName" && (
                                <input
                                  type="checkbox"
                                  checked={isChecked}
                                  onClick={(e) => e.stopPropagation()}
                                  onChange={() => toggleSelectRow(row.id)}
                                  className="mr-1.5 flex-shrink-0"
                                />
                              )}
                              {content}
                            </div>
                          );
                        })}
                        {isAdmin && (
                          <div className="flex items-center justify-center px-2 flex-shrink-0" style={{ width: 44 }}>
                            <button
                              onClick={(e) => { e.stopPropagation(); deleteRow(row); }}
                              disabled={deleting}
                              title="Delete entry (Del)"
                              className="p-1 text-muted-foreground hover:text-destructive disabled:opacity-40"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  }}
                </List>
              </div>
            </div>
          )}
        </div>

        {/* ── Right info panel ─────────────────────────────────────────── */}
        <RightPanel row={selectedRow} />
      </div>

      {/* ── Bottom status bar ────────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center gap-4 mt-2 px-3 py-1.5 border border-border rounded-md bg-muted/30 text-[10px] font-mono text-muted-foreground overflow-x-auto whitespace-nowrap">
        <span>Records: <b className="text-foreground">{total}</b></span>
        <span>Opening: <b className="text-foreground">{fmtNum(summary?.openingStock, 0)}</b></span>
        <span className="text-emerald-600">In: <b>{fmtNum(summary?.totalInward, 0)}</b></span>
        <span className="text-red-600">Out: <b>{fmtNum(summary?.totalOutward, 0)}</b></span>
        <span>Closing: <b className="text-foreground">{fmtNum(summary?.closingStock, 0)}</b></span>
        <span>Value: <b className="text-foreground">₹{fmtNum(summary?.stockValue, 0)}</b></span>
        <span>Selected: <b className="text-foreground">{selectedIds.size}</b></span>
        {isAdmin && selectedIds.size > 0 && (
          <button
            onClick={deleteSelected}
            disabled={deleting}
            title="Delete selected (Del)"
            className="flex items-center gap-1 px-2 py-0.5 border border-destructive/40 rounded-md text-destructive hover:bg-destructive/10 disabled:opacity-40 font-mono normal-case"
          >
            <Trash2 className="w-3 h-3" /> {deleting ? "Deleting…" : `Delete ${selectedIds.size}`}
          </button>
        )}
        <span className="ml-auto">{user?.name || "—"}</span>
        <span>FY 2026-27</span>
      </div>
    </div>
  );
}

function RightPanel({ row }) {
  const [panel, setPanel] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!row?.productId) { setPanel(null); return; }
    setLoading(true);
    api.get(`/stock-log/product-panel/${row.productId}`)
      .then((r) => setPanel(r.data))
      .catch(() => setPanel(null))
      .finally(() => setLoading(false));
  }, [row?.productId]);

  if (!row) {
    return (
      <div className="w-[260px] flex-shrink-0 border border-border rounded-md bg-card p-4 text-xs text-muted-foreground flex items-center justify-center text-center">
        Select a row to see product details
      </div>
    );
  }

  return (
    <div className="w-[260px] flex-shrink-0 border border-border rounded-md bg-card overflow-y-auto">
      <div className="p-3 border-b border-border">
        <div className="w-full h-24 bg-muted rounded-md flex items-center justify-center mb-2 overflow-hidden">
          {panel?.imageUrl ? (
            <img src={panel.imageUrl} alt={panel?.name} className="w-full h-full object-cover" />
          ) : (
            <Package className="w-8 h-8 text-muted-foreground/40" />
          )}
        </div>
        <div className="text-sm font-semibold text-foreground truncate">{row.productName}</div>
        <div className="text-[10px] font-mono text-muted-foreground">{row.productCode || "—"}</div>
      </div>

      {loading ? (
        <div className="p-3 space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-3 w-full" />)}</div>
      ) : panel ? (
        <div className="p-3 space-y-1.5 text-[11px]">
          <PanelRow label="Current Stock" value={fmtNum(panel.currentStock, 2)} />
          <PanelRow label="Reserved Stock" value={fmtNum(panel.reservedStock, 2)} />
          <PanelRow label="Available Stock" value={fmtNum(panel.availableStock, 2)} />
          <PanelRow label="Closing Balance" value={fmtNum(panel.closingBalance, 2)} />
          <PanelRow label="Average Cost" value={`₹${fmtNum(panel.averageCost)}`} />
          <PanelRow label="Stock Value" value={`₹${fmtNum(panel.stockValue, 0)}`} />
          <PanelRow label="Last Purchase" value={panel.lastPurchase ? (panel.lastPurchase.created_at || "").slice(0, 10) : "—"} />
          <PanelRow label="Last Sale" value={panel.lastSale ? (panel.lastSale.created_at || "").slice(0, 10) : "—"} />
          <PanelRow label="Warehouse Location" value={panel.warehouseLocation || "—"} />
          <PanelRow label="Batch" value={row.batchNo || "—"} />
          <PanelRow label="Serial Number" value={row.serialNo || "—"} />
          <PanelRow label="Minimum Stock" value={fmtNum(panel.minimumStock, 0)} />
          <PanelRow label="Reorder Level" value={fmtNum(panel.reorderLevel, 0)} />
          <PanelRow label="HSN Code" value={panel.hsnCode || "—"} />
          <PanelRow label="Unit" value={panel.unit || "—"} />
        </div>
      ) : null}
    </div>
  );
}

function PanelRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5 border-b border-border/40">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground text-right truncate">{value}</span>
    </div>
  );
}
