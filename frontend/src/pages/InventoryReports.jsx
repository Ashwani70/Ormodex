import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, Input, Field, Select, EmptyState, SecondaryButton } from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Search, X, AlertTriangle, RefreshCw, Eye, ArrowRight } from "lucide-react";

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
  const [godowns, setGodowns] = useState([]);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selGodown, setSelGodown] = useState("");
  const [selItem, setSelItem] = useState("");
  const [viewItem, setViewItem] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([
      api.get("/inventory/v2/items"),
      api.get("/inventory/v2/godowns"),
    ]).then(([rItems, rGodowns]) => {
      const dItems = rItems.data;
      const dGodowns = rGodowns.data;
      setItems(Array.isArray(dItems) ? dItems : dItems?.items || []);
      setGodowns(Array.isArray(dGodowns) ? dGodowns : dGodowns?.items || []);
    }).catch(() => {});
  }, []);

  const godownName = (id) => godowns.find((g) => g.id === id)?.name || id;

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setData(null);
    setLoadError(null);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (selGodown) params.godown_id = selGodown;
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
  }, [tab, fromDate, toDate, selItem, selGodown]);

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
          {tab === "summary" && (
            <div className="w-56">
              <Field label="Warehouse">
                <Select value={selGodown} data-testid="report-godown-select"
                  onChange={(e) => setSelGodown(e.target.value)}>
                  <option value="">— All Warehouses —</option>
                  {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </Select>
              </Field>
            </div>
          )}
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
            <th className="px-3 py-2.5 text-right">Adjustment</th>
            <th className="px-3 py-2.5 text-right">Closing Qty</th>
            <th className="px-3 py-2.5 text-right">Closing Value</th>
            <th className="px-3 py-2.5 text-right">Seen</th>
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
                <td className={`px-3 py-2.5 text-right font-medium ${r.adjustment_qty < 0 ? "text-red-400" : r.adjustment_qty > 0 ? "text-emerald-400" : "text-muted-foreground"}`}>{inr(r.adjustment_qty)}</td>
                <td className="px-3 py-2.5 text-right text-foreground font-semibold">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right text-primary">{inr(r.closing_value)}</td>
                <td className="px-3 py-2.5 text-right">
                  <button
                    type="button"
                    title="View item details"
                    aria-label="View item details"
                    onClick={() => setViewItem(r)}
                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                </td>
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
            <th className="px-3 py-2.5 text-right">Seen</th>
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
                <td className="px-3 py-2.5 text-right">
                  <button
                    type="button"
                    title="View item details"
                    aria-label="View item details"
                    onClick={() => {
                      const sumItem = summaryRows.find((s) => s.stock_item_id === r.stock_item_id);
                      setViewItem(sumItem || { stock_item_id: r.stock_item_id, name: r.name, closing_qty: r.closing_qty });
                    }}
                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                </td>
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
            <th className="px-3 py-2.5 text-right">Seen</th>
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
                <td className="px-3 py-2.5 text-right">
                  <button
                    type="button"
                    title="View item details"
                    aria-label="View item details"
                    onClick={() => {
                      const sumItem = summaryRows.find((s) => s.stock_item_id === r.stock_item_id);
                      setViewItem(sumItem || { stock_item_id: r.stock_item_id, name: r.name, closing_qty: r.closing_qty });
                    }}
                    className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message={search ? `No items match "${search}"` : "No items at or below reorder level"} />
      )}

      {/* Seen / View Item Details Modal */}
      <Modal
        open={Boolean(viewItem)}
        onClose={() => setViewItem(null)}
        title={`Stock Details — ${viewItem?.name || ""}`}
        size="lg"
        footer={
          <div className="flex items-center justify-between w-full">
            <SecondaryButton
              icon={ArrowRight}
              onClick={() => {
                if (viewItem?.stock_item_id) {
                  setSelItem(viewItem.stock_item_id);
                  setTab("movement");
                  setViewItem(null);
                }
              }}
            >
              View Movement Ledger
            </SecondaryButton>
            <SecondaryButton onClick={() => setViewItem(null)}>Close</SecondaryButton>
          </div>
        }
      >
        {viewItem && (
          <div className="space-y-4 text-sm font-mono">
            {/* Top metrics summary grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 bg-muted/30 border border-border rounded">
                <div className="text-xs text-muted-foreground label-overline">Opening Stock</div>
                <div className="font-semibold text-foreground">{inr(viewItem.opening_qty)}</div>
                {viewItem.opening_value !== undefined && (
                  <div className="text-xs text-muted-foreground">₹{inr(viewItem.opening_value)}</div>
                )}
              </div>
              <div className="p-3 bg-emerald-950/20 border border-emerald-800/40 rounded">
                <div className="text-xs text-emerald-400 label-overline">Total Inward</div>
                <div className="font-semibold text-emerald-400">+{inr(viewItem.inward_qty)}</div>
                {viewItem.inward_value !== undefined && (
                  <div className="text-xs text-emerald-500/80">₹{inr(viewItem.inward_value)}</div>
                )}
              </div>
              <div className="p-3 bg-amber-950/20 border border-amber-800/40 rounded">
                <div className="text-xs text-amber-400 label-overline">Total Outward</div>
                <div className="font-semibold text-amber-400">-{inr(viewItem.outward_qty)}</div>
                {viewItem.outward_value !== undefined && (
                  <div className="text-xs text-amber-500/80">₹{inr(viewItem.outward_value)}</div>
                )}
              </div>
              <div className="p-3 bg-primary/10 border border-primary/30 rounded">
                <div className="text-xs text-primary label-overline">Closing Balance</div>
                <div className="font-semibold text-primary">{inr(viewItem.closing_qty)}</div>
                {viewItem.closing_value !== undefined && (
                  <div className="text-xs text-primary/80">₹{inr(viewItem.closing_value)}</div>
                )}
              </div>
            </div>

            {/* Item metadata */}
            <div className="flex items-center justify-between p-2.5 bg-muted/20 border border-border rounded text-xs text-muted-foreground">
              <div>
                Valuation Method: <span className="font-semibold text-foreground">{viewItem.valuation_method || "DEFAULT"}</span>
              </div>
              {viewItem.stock_item_id && (
                <div>
                  Item ID: <span className="font-mono text-foreground">{viewItem.stock_item_id}</span>
                </div>
              )}
            </div>

            {/* Warehouse / Godown breakdown */}
            <div>
              <div className="text-xs text-muted-foreground label-overline mb-2">Per-Warehouse Breakdown</div>
              {(viewItem.per_godown && viewItem.per_godown.length > 0) ? (
                <div className="border border-border rounded overflow-hidden">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-muted text-muted-foreground border-b border-border">
                      <tr>
                        <th className="px-3 py-2">Warehouse</th>
                        <th className="px-3 py-2 text-right">Closing Qty</th>
                        <th className="px-3 py-2 text-right">Closing Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {viewItem.per_godown.map((g, idx) => (
                        <tr key={idx} className="border-b border-border last:border-0 hover:bg-muted/20">
                          <td className="px-3 py-2 font-medium text-foreground">{godownName(g.godown_id)}</td>
                          <td className="px-3 py-2 text-right font-semibold text-foreground">{inr(g.qty)}</td>
                          <td className="px-3 py-2 text-right text-primary">₹{inr(g.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-3 text-xs text-muted-foreground text-center bg-muted/10 border border-border rounded">
                  No specific warehouse breakdown recorded for this item.
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

