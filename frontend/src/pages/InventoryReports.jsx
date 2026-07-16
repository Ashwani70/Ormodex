import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, Input, Field, Select, EmptyState, SecondaryButton } from "@/components/ui-kit";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Search, X, AlertTriangle, RefreshCw } from "lucide-react";

const TABS = [
  { key: "summary", label: "Stock Summary" },
  { key: "movement", label: "Movement Analysis" },
  { key: "aging", label: "Stock Aging" },
  { key: "low-stock", label: "Low Stock" },
];

const inr = (n) => (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

function TabBar({ tab, setTab }) {
  return (
    <div className="flex gap-1 border-b border-border mb-4 overflow-x-auto">
      {TABS.map((t) => (
        <button key={t.key} data-testid={`report-tab-${t.key}`} onClick={() => setTab(t.key)}
          className={`font-mono uppercase tracking-wider text-[11px] px-4 py-2.5 border-b-2 transition-colors whitespace-nowrap ${
            tab === t.key
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Table({ head, children }) {
  return (
    <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
      <table className="w-full text-sm font-mono text-left">
        <thead className="bg-muted text-muted-foreground">
          <tr className="border-b border-border label-overline">{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export default function InventoryReports() {
  const online = useOnline();
  const [tab, setTab] = useState("summary");
  const [items, setItems] = useState([]);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selItem, setSelItem] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    api.get("/inventory/v2/items").then((r) => {
      const data = r.data;
      setItems(Array.isArray(data) ? data : data?.items || []);
    }).catch(() => {});
  }, []);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setData(null);
    setLoadError(null);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      let url;
      if (tab === "summary") url = "/inventory/v2/reports/stock-summary";
      else if (tab === "aging") { url = "/inventory/v2/reports/stock-aging"; }
      else if (tab === "low-stock") { url = "/inventory/v2/reports/low-stock"; }
      else {
        if (!selItem) { setLoading(false); return; }
        url = "/inventory/v2/reports/movement-analysis";
        params.stock_item_id = selItem;
      }
      const r = await api.get(url, { params });
      setData(r.data);
    } catch (err) {
      const detail = formatApiErrorDetail(err.response?.data?.detail) || err.message;
      const status = err.response?.status;
      console.error(`[InventoryReports] "${tab}" report load failed:`, status, detail, err);
      setLoadError(status ? `Error ${status}: ${detail}` : detail);
    } finally {
      setLoading(false);
    }
  }, [tab, fromDate, toDate, selItem]);

  useEffect(() => { fetchReport(); }, [fetchReport]);
  useEffect(() => { setSearch(""); }, [tab]);

  const showDateRange = tab === "summary" || tab === "movement";
  const showItemPicker = tab === "movement";

  const q = search.trim().toLowerCase();
  const summaryRows = Array.isArray(data) && tab === "summary"
    ? (q ? data.filter((r) => r.name?.toLowerCase().includes(q)) : data)
    : [];
  const agingRows = data?.items && tab === "aging"
    ? (q ? data.items.filter((r) => r.name?.toLowerCase().includes(q)) : data.items)
    : [];
  const lowStockRows = Array.isArray(data) && tab === "low-stock"
    ? (q ? data.filter((r) => r.name?.toLowerCase().includes(q)) : data)
    : [];
  const movementRows = data?.entries && tab === "movement"
    ? (q ? data.entries.filter((e) =>
        e.movement_type?.toLowerCase().includes(q) ||
        e.source_doc_type?.toLowerCase().includes(q) ||
        e.entry_date?.includes(q)
      ) : data.entries)
    : [];

  const showSearch = !loading && data !== null && tab !== "movement"
    ? (summaryRows.length > 0 || agingRows.length > 0 || lowStockRows.length > 0)
    : (!loading && tab === "movement" && !!selItem && movementRows.length >= 0);

  return (
    <div data-testid="inventory-reports-page">
      <PageHeader
        eyebrow="Inventory"
        title="Inventory Reports"
        description="Stock summary, movement analysis, aging and low-stock alerts — derived from the stock ledger."
      />
      <OfflineBanner online={online} />
      <TabBar tab={tab} setTab={setTab} />

      {(showDateRange || showItemPicker) && (
        <div className="flex flex-wrap gap-3 items-end mb-4">
          {showItemPicker && (
            <div className="w-64">
              <Field label="Stock Item">
                <Select value={selItem} data-testid="report-item-select"
                  onChange={(e) => setSelItem(e.target.value)}>
                  <option value="">— Select item —</option>
                  {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                </Select>
              </Field>
            </div>
          )}
          {showDateRange && (
            <>
              <div className="w-44">
                <Field label="From"><Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /></Field>
              </div>
              <div className="w-44">
                <Field label="To"><Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} /></Field>
              </div>
            </>
          )}
        </div>
      )}

      {loading && <div className="text-muted-foreground font-mono text-sm py-8 text-center" data-testid="reports-loading">Loading…</div>}

      {loadError && !loading && (
        <div
          data-testid="reports-error"
          className="border border-red-800/60 bg-red-950/30 rounded-lg p-6 flex flex-col items-center text-center gap-3 my-4"
        >
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div className="font-semibold text-red-200">Couldn't load report data</div>
          <div className="text-sm text-red-300/90 font-mono max-w-lg break-words">{loadError}</div>
          <SecondaryButton onClick={fetchReport} icon={RefreshCw}>Retry</SecondaryButton>
        </div>
      )}

      {/* Search bar — shown once data is loaded */}
      {!loading && !loadError && data !== null && (
        <div className="relative mb-3">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={
              tab === "movement"
                ? "Filter by date, movement type, source…"
                : "Search item name…"
            }
            className="w-full bg-background border border-input text-foreground text-sm pl-9 pr-8 py-2 focus:border-primary focus:outline-none transition-colors"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      )}

      {/* Result count hint */}
      {!loading && !loadError && search && (
        <div className="text-xs text-muted-foreground font-mono mb-2">
          {tab === "summary" && `${summaryRows.length} item${summaryRows.length !== 1 ? "s" : ""} found`}
          {tab === "aging"   && `${agingRows.length} item${agingRows.length !== 1 ? "s" : ""} found`}
          {tab === "low-stock" && `${lowStockRows.length} item${lowStockRows.length !== 1 ? "s" : ""} found`}
          {tab === "movement" && `${movementRows.length} entr${movementRows.length !== 1 ? "ies" : "y"} found`}
        </div>
      )}

      {!loading && !loadError && tab === "summary" && (
        summaryRows.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5">Method</th>
            <th className="px-3 py-2.5 text-right">Opening Qty</th>
            <th className="px-3 py-2.5 text-right">Inward</th>
            <th className="px-3 py-2.5 text-right">Outward</th>
            <th className="px-3 py-2.5 text-right">Closing Qty</th>
            <th className="px-3 py-2.5 text-right">Closing Value</th>
          </>}>
            {summaryRows.map((r) => (
              <tr key={r.stock_item_id} data-testid={`summary-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">
                  {q ? (
                    <span dangerouslySetInnerHTML={{
                      __html: r.name.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
                        "<mark class=\"bg-primary/20 text-primary rounded-sm\">$1</mark>")
                    }} />
                  ) : r.name}
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{r.valuation_method}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.opening_qty)}</td>
                <td className="px-3 py-2.5 text-right text-emerald-400">{inr(r.inward_qty)}</td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.outward_qty)}</td>
                <td className="px-3 py-2.5 text-right text-foreground font-semibold">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right text-primary">{inr(r.closing_value)}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message={search ? `No items match "${search}"` : "No stock summary data"} />
      )}

      {!loading && !loadError && tab === "movement" && (
        !selItem ? <EmptyState message="Select an item to view its movement ledger" />
        : movementRows.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Date</th>
            <th className="px-3 py-2.5">Movement</th>
            <th className="px-3 py-2.5">Source</th>
            <th className="px-3 py-2.5 text-right">Qty</th>
            <th className="px-3 py-2.5 text-right">Rate</th>
            <th className="px-3 py-2.5 text-right">Value</th>
          </>}>
            {movementRows.map((e) => (
              <tr key={e.id} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 text-muted-foreground">{e.entry_date}</td>
                <td className="px-3 py-2.5 text-xs">{e.movement_type}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{e.source_doc_type || "—"}</td>
                <td className={`px-3 py-2.5 text-right ${e.qty < 0 ? "text-amber-400" : "text-emerald-400"}`}>{inr(e.qty)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(e.rate)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(e.value)}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message={search ? `No entries match "${search}"` : "No movements for this item in range"} />
      )}

      {!loading && !loadError && tab === "aging" && (
        agingRows.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5 text-right">Closing Qty</th>
            <th className="px-3 py-2.5 text-right">0–30</th>
            <th className="px-3 py-2.5 text-right">31–60</th>
            <th className="px-3 py-2.5 text-right">61–90</th>
            <th className="px-3 py-2.5 text-right">90+</th>
          </>}>
            {agingRows.map((r) => (
              <tr key={r.stock_item_id} data-testid={`aging-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">
                  {q ? (
                    <span dangerouslySetInnerHTML={{
                      __html: r.name.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
                        "<mark class=\"bg-primary/20 text-primary rounded-sm\">$1</mark>")
                    }} />
                  ) : r.name}
                </td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["0-30"])}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["31-60"])}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["61-90"])}</td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.buckets["90+"])}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message={search ? `No items match "${search}"` : "No stock on hand to age"} />
      )}

      {!loading && !loadError && tab === "low-stock" && (
        lowStockRows.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5 text-right">On Hand</th>
            <th className="px-3 py-2.5 text-right">Reorder Level</th>
            <th className="px-3 py-2.5 text-right">Shortfall</th>
            <th className="px-3 py-2.5 text-right">Reorder Qty</th>
          </>}>
            {lowStockRows.map((r) => (
              <tr key={r.stock_item_id} data-testid={`lowstock-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">
                  {q ? (
                    <span dangerouslySetInnerHTML={{
                      __html: r.name.replace(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"),
                        "<mark class=\"bg-primary/20 text-primary rounded-sm\">$1</mark>")
                    }} />
                  ) : r.name}
                </td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.reorder_level)}</td>
                <td className="px-3 py-2.5 text-right text-red-400">{inr(r.shortfall)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.reorder_qty)}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message={search ? `No items match "${search}"` : "No items at or below reorder level"} />
      )}
    </div>
  );
}
