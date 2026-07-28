import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Badge, SkeletonTable, EmptyState,
} from "@/components/ui-kit";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { useAuth } from "@/context/AuthContext";
import { isAdminRole } from "@/lib/navItems";
import WarehouseForm from "@/components/warehouse/WarehouseForm";
import { FixedSizeList } from "react-window";
import {
  Warehouse as WarehouseIcon, Plus, Search, SlidersHorizontal, Pencil, Trash2,
  Printer, FileSpreadsheet, Package, TrendingDown, PackageX,
  Truck, ArrowDownToLine, ArrowUpFromLine, Gauge, Layers, RefreshCw, X, AlertTriangle,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar, Cell,
} from "recharts";

// ── Type / status metadata ───────────────────────────────────────────
const TYPE_LABELS = {
  MAIN: "Main", BRANCH: "Branch", RAW_MATERIAL: "Raw Material", FINISHED_GOODS: "Finished Goods",
  WIP: "WIP", SCRAP: "Scrap", TRANSIT: "Transit", CONSIGNMENT: "Consignment",
};
const TYPE_TONE = {
  MAIN: "info", BRANCH: "neutral", RAW_MATERIAL: "warning", FINISHED_GOODS: "success",
  WIP: "info", SCRAP: "danger", TRANSIT: "neutral", CONSIGNMENT: "warning",
};

const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

// Debounce a fast-changing value (search box).
function useDebounced(value, delay = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export default function Godowns() {
  const online = useOnline();
  const { user } = useAuth();
  const isAdmin = isAdminRole(user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filterType, setFilterType] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const debSearch = useDebounced(search, 300);

  const load = useCallback(async (soft) => {
    if (soft) setRefreshing(true); else setLoading(true);
    setLoadError(null);
    try {
      const [listRes, dashRes] = await Promise.all([
        api.get("/inventory/v2/godowns"),
        api.get("/inventory/v2/warehouses/dashboard"),
      ]);
      const list = Array.isArray(listRes.data) ? listRes.data : listRes.data?.items || [];
      setItems(list);
      setDash(dashRes.data);
    } catch (err) {
      const detail = formatApiErrorDetail(err.response?.data?.detail) || err.message;
      setLoadError(detail);
      toast.error(detail || "Failed to load warehouses");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const valueById = useMemo(() => {
    const m = {};
    (dash?.heat_map || []).forEach((c) => { m[c.id] = c; });
    return m;
  }, [dash]);

  const nameById = (id) => items.find((g) => g.id === id)?.name || "—";

  const filtered = useMemo(() => {
    const q = debSearch.trim().toLowerCase();
    return items.filter((w) => {
      if (filterType && (w.warehouse_type || "MAIN") !== filterType) return false;
      if (filterStatus && (w.status || "ACTIVE") !== filterStatus) return false;
      if (!q) return true;
      return [w.name, w.code, w.short_name, w.city, w.address]
        .filter(Boolean).some((s) => String(s).toLowerCase().includes(q));
    });
  }, [items, debSearch, filterType, filterStatus]);

  const openNew = () => { setEditId(null); setFormOpen(true); };
  const openEdit = (id) => { setEditId(id); setFormOpen(true); };

  // Auto-open a warehouse's detail form via ?detail=<id> — the same
  // convention Customers/Products use (Ctrl+K search, or the global Alt+W
  // Warehouse Picker) so "Enter" on a picked result needs no second click.
  useEffect(() => {
    const detailId = searchParams.get("detail");
    if (!detailId || items.length === 0) return;
    if (items.some((w) => w.id === detailId)) {
      openEdit(detailId);
      const next = new URLSearchParams(searchParams);
      next.delete("detail");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, items]);

  const onDelete = async (item) => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (!window.confirm(`Delete warehouse "${item.name}"?`)) return;
    try {
      await api.delete(`/inventory/v2/godowns/${item.id}`);
      toast.success("Deleted");
      load(true);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail === "Cannot delete a warehouse with stock movements") {
        if (window.confirm(`"${item.name}" has stock movements. Force delete it and all related movements/transfers? This is irreversible.`)) {
          try {
            await api.delete(`/inventory/v2/godowns/${item.id}`, { params: { force: true } });
            toast.success("Warehouse and movements deleted");
            load(true);
          } catch (fe) { toast.error(formatApiErrorDetail(fe.response?.data?.detail)); }
        }
      } else {
        toast.error(formatApiErrorDetail(detail));
      }
    }
  };

  // ── Export helpers ──────────────────────────────────────────────────
  const exportCsv = () => {
    const cols = ["Code", "Name", "Type", "Status", "City", "State", "Stock Value", "Items", "Low Stock"];
    const rows = filtered.map((w) => {
      const c = valueById[w.id] || {};
      return [
        w.code || "", w.name || "", TYPE_LABELS[w.warehouse_type] || w.warehouse_type || "Main",
        w.status || "ACTIVE", w.city || "", w.state || "",
        c.value ?? 0, c.item_count ?? 0, c.low_stock ?? 0,
      ];
    });
    const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const csv = [cols, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `warehouses-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div data-testid="warehouses-page">
      <PageHeader
        eyebrow="Inventory / Warehouses"
        title="Warehouses"
        description="Enterprise warehouse master — locations, bins, inventory rules, security and AI insights."
        actions={
          <>
            <SecondaryButton icon={RefreshCw} onClick={() => load(true)} loading={refreshing}>Refresh</SecondaryButton>
            <SecondaryButton icon={FileSpreadsheet} onClick={exportCsv}>Export</SecondaryButton>
            <SecondaryButton icon={Printer} onClick={() => window.print()}>Print</SecondaryButton>
            <PrimaryButton testid="new-warehouse" icon={Plus} disabled={!online} onClick={openNew}>
              New Warehouse
            </PrimaryButton>
          </>
        }
      />
      <OfflineBanner online={online} />

      {/* Dashboard */}
      {loading ? (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-[92px] animate-pulse rounded-[10px] border border-border bg-muted/40" />
          ))}
        </div>
      ) : loadError ? (
        <div
          data-testid="warehouses-error"
          className="border border-red-800/60 bg-red-950/30 rounded-lg p-6 flex flex-col items-center text-center gap-3 my-4"
        >
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div className="font-semibold text-red-200">Couldn't load warehouses</div>
          <div className="text-sm text-red-300/90 font-mono max-w-lg break-words">{loadError}</div>
          <SecondaryButton onClick={() => load(false)} icon={RefreshCw}>Retry</SecondaryButton>
        </div>
      ) : dash && (
        <Dashboard dash={dash} onPickWarehouse={openEdit} />
      )}

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search by name, code, city…" value={search}
            onChange={(e) => setSearch(e.target.value)} data-testid="wh-search" />
        </div>
        <SecondaryButton icon={SlidersHorizontal} onClick={() => setShowFilters((s) => !s)}>
          Filters {(filterType || filterStatus) ? "•" : ""}
        </SecondaryButton>
      </div>

      {showFilters && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-[10px] border border-border bg-card p-3.5">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Type</span>
            <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
              className="rounded-md border border-input bg-surface px-2 py-1.5 text-sm">
              <option value="">All</option>
              {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Status</span>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
              className="rounded-md border border-input bg-surface px-2 py-1.5 text-sm">
              <option value="">All</option>
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </select>
          </label>
          {(filterType || filterStatus) && (
            <button onClick={() => { setFilterType(""); setFilterStatus(""); }}
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" /> Clear
            </button>
          )}
          <span className="ml-auto text-sm text-muted-foreground">{filtered.length} of {items.length}</span>
        </div>
      )}

      {/* List */}
      {loading ? (
        <SkeletonTable rows={6} cols={6} />
      ) : filtered.length === 0 ? (
        <EmptyState message={items.length ? "No warehouses match your filters" : "No warehouses yet"}
          action={items.length ? undefined : <PrimaryButton icon={Plus} onClick={openNew}>New Warehouse</PrimaryButton>} />
      ) : (
        <WarehouseTable rows={filtered} valueById={valueById} nameById={nameById}
          onEdit={openEdit} onDelete={onDelete} isAdmin={isAdmin} />
      )}

      <WarehouseForm
        open={formOpen}
        isAdmin={isAdmin}
        warehouseId={editId}
        warehouses={items}
        onClose={() => setFormOpen(false)}
        onSaved={() => load(true)}
      />
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────
function Dashboard({ dash, onPickWarehouse }) {
  const kpis = [
    { label: "Total Warehouses", value: dash.total_warehouses, icon: WarehouseIcon, sub: `${dash.active_warehouses} active` },
    { label: "Inventory Value", value: money(dash.total_inventory_value), icon: Package, accent: true },
    { label: "Low Stock", value: dash.low_stock, icon: TrendingDown, tone: dash.low_stock ? "warning" : undefined },
    { label: "Out of Stock", value: dash.out_of_stock, icon: PackageX, tone: dash.out_of_stock ? "danger" : undefined },
    { label: "Pending Transfers", value: dash.pending_transfers, icon: Truck },
    { label: "Today's Receipts", value: dash.today_receipts, icon: ArrowDownToLine, tone: "success" },
    { label: "Today's Dispatch", value: dash.today_dispatch, icon: ArrowUpFromLine, tone: "info" },
    { label: "Occupancy", value: `${dash.occupancy}%`, icon: Gauge },
  ];
  return (
    <div className="mb-6 space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
        {kpis.map((k) => <Kpi key={k.label} {...k} />)}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Movement chart */}
        <div className="rounded-[10px] border border-border bg-card p-4 lg:col-span-2" style={{ boxShadow: "var(--shadow-sm)" }}>
          <div className="mb-2 flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            <h3 className="font-display text-sm font-bold text-foreground">Stock Movement (30 days)</h3>
          </div>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dash.movement_chart} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="gIn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0D9488" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#0D9488" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gOut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#F59E0B" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#F59E0B" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E8EF" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6B7280" }}
                  tickFormatter={(d) => d?.slice(5)} minTickGap={24} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "#6B7280" }} width={44} axisLine={false} tickLine={false}
                  tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)} />
                <Tooltip formatter={(v, n) => [money(v), n === "inward" ? "Inward" : "Outward"]}
                  labelFormatter={(l) => l} contentStyle={{ borderRadius: 10, border: "1px solid #E4E8EF", fontSize: 12 }} />
                <Area type="monotone" dataKey="inward" stroke="#0D9488" strokeWidth={2} fill="url(#gIn)" />
                <Area type="monotone" dataKey="outward" stroke="#F59E0B" strokeWidth={2} fill="url(#gOut)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Heat map / occupancy by warehouse */}
        <div className="rounded-[10px] border border-border bg-card p-4" style={{ boxShadow: "var(--shadow-sm)" }}>
          <div className="mb-2 flex items-center gap-2">
            <Gauge className="h-4 w-4 text-primary" />
            <h3 className="font-display text-sm font-bold text-foreground">Warehouse Heat Map</h3>
          </div>
          {(dash.heat_map || []).length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">No stock data yet</p>
          ) : (
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={(dash.heat_map || []).slice(0, 8)} layout="vertical"
                  margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10, fill: "#6B7280" }}
                    axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v) => money(v)} cursor={{ fill: "rgba(13,148,136,0.06)" }}
                    contentStyle={{ borderRadius: 10, border: "1px solid #E4E8EF", fontSize: 12 }} />
                  <Bar dataKey="value" radius={[0, 6, 6, 0]} onClick={(d) => d?.id && onPickWarehouse(d.id)}
                    cursor="pointer">
                    {(dash.heat_map || []).slice(0, 8).map((c) => (
                      <Cell key={c.id} fill={heatColor(c.occupancy)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function heatColor(occ) {
  // Teal → amber → red as occupancy climbs.
  if (occ >= 80) return "#DC2626";
  if (occ >= 55) return "#F59E0B";
  if (occ >= 25) return "#0D9488";
  return "#5EEAD4";
}

function Kpi({ label, value, icon: Icon, sub, accent, tone }) {
  const vc = tone === "danger" ? "text-[var(--danger)]" : tone === "warning" ? "text-amber-600"
    : tone === "success" ? "text-primary" : tone === "info" ? "text-sky-600" : accent ? "text-primary" : "text-foreground";
  return (
    <div className="rounded-[10px] border border-border bg-card p-3.5 transition-all hover:-translate-y-0.5 hover:shadow-md"
      style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span className="label-overline truncate">{label}</span>
      </div>
      <div className={`mt-1.5 font-display text-xl font-bold tabular ${vc}`}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

// ── Virtualized table ─────────────────────────────────────────────────
const ROW_H = 56;
function WarehouseTable({ rows, valueById, nameById, onEdit, onDelete, isAdmin }) {
  const listRef = useRef(null);
  // Virtualize only when the list is long; short lists render normally so the
  // page prints and flows naturally.
  const virtualize = rows.length > 40;

  const Header = (
    <div className="grid grid-cols-[110px_1fr_120px_90px_140px_130px_90px_110px] items-center gap-2 border-b border-border bg-muted px-4 py-2.5 text-muted-foreground label-overline">
      <div>Code</div><div>Name</div><div>Type</div><div>Status</div><div>Location</div>
      <div className="text-right">Stock Value</div><div className="text-right">Items</div>
      <div className="text-right">Actions</div>
    </div>
  );

  const Row = ({ w, style }) => {
    const c = valueById[w.id] || {};
    const low = (c.low_stock || 0) > 0;
    return (
      <div style={style}
        className="grid grid-cols-[110px_1fr_120px_90px_140px_130px_90px_110px] items-center gap-2 border-b border-border px-4 text-sm hover:bg-muted/40">
        <div className="truncate font-mono text-xs text-muted-foreground">{w.code || "—"}</div>
        <div className="min-w-0">
          <button onClick={() => onEdit(w.id)} className="truncate text-left font-semibold text-foreground hover:text-primary">
            {w.name}
          </button>
          {w.parent_godown_id && (
            <div className="truncate text-[11px] text-muted-foreground">↳ under {nameById(w.parent_godown_id)}</div>
          )}
        </div>
        <div><Badge tone={TYPE_TONE[w.warehouse_type] || "neutral"}>{TYPE_LABELS[w.warehouse_type] || "Main"}</Badge></div>
        <div><Badge tone={(w.status || "ACTIVE") === "ACTIVE" ? "success" : "neutral"}>{(w.status || "ACTIVE") === "ACTIVE" ? "Active" : "Inactive"}</Badge></div>
        <div className="truncate text-muted-foreground">{w.city || w.state || "—"}</div>
        <div className="text-right font-mono tabular-nums text-foreground">{money(c.value)}</div>
        <div className="text-right font-mono tabular-nums">
          <span className={low ? "text-amber-600" : "text-muted-foreground"}>{c.item_count ?? 0}</span>
          {low && <span className="ml-1 text-[10px] text-amber-600">⚠</span>}
        </div>
        <div className="flex justify-end gap-1">
          <IconBtn title={isAdmin ? "Edit" : "View"} onClick={() => onEdit(w.id)}><Pencil className="h-3.5 w-3.5" /></IconBtn>
          {isAdmin && (
            <IconBtn title="Delete" danger onClick={() => onDelete(w)}><Trash2 className="h-3.5 w-3.5" /></IconBtn>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="overflow-hidden rounded-[10px] border border-border bg-card" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="overflow-x-auto">
        <div className="min-w-[900px]">
          {Header}
          {virtualize ? (
            <FixedSizeList ref={listRef} height={Math.min(rows.length * ROW_H, 560)} itemCount={rows.length}
              itemSize={ROW_H} width="100%">
              {({ index, style }) => <Row w={rows[index]} style={style} />}
            </FixedSizeList>
          ) : (
            rows.map((w) => <Row key={w.id} w={w} style={{ height: ROW_H }} />)
          )}
        </div>
      </div>
    </div>
  );
}

function IconBtn({ children, onClick, title, danger }) {
  return (
    <button onClick={onClick} title={title}
      className={`flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors ${
        danger ? "hover:border-[var(--danger)] hover:text-[var(--danger)]" : "hover:border-primary hover:text-primary"
      }`}>
      {children}
    </button>
  );
}
