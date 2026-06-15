import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, Input, Field, Select, EmptyState } from "@/components/ui-kit";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";

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

  useEffect(() => {
    api.get("/inventory/v2/items").then((r) => setItems(r.data)).catch(() => {});
  }, []);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setData(null);
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
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [tab, fromDate, toDate, selItem]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const showDateRange = tab === "summary" || tab === "movement";
  const showItemPicker = tab === "movement";

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

      {loading && <div className="text-muted-foreground font-mono text-sm py-8 text-center">Loading…</div>}

      {!loading && tab === "summary" && (
        Array.isArray(data) && data.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5">Method</th>
            <th className="px-3 py-2.5 text-right">Opening Qty</th>
            <th className="px-3 py-2.5 text-right">Inward</th>
            <th className="px-3 py-2.5 text-right">Outward</th>
            <th className="px-3 py-2.5 text-right">Closing Qty</th>
            <th className="px-3 py-2.5 text-right">Closing Value</th>
          </>}>
            {data.map((r) => (
              <tr key={r.stock_item_id} data-testid={`summary-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">{r.name}</td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground">{r.valuation_method}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.opening_qty)}</td>
                <td className="px-3 py-2.5 text-right text-emerald-400">{inr(r.inward_qty)}</td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.outward_qty)}</td>
                <td className="px-3 py-2.5 text-right text-foreground font-semibold">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right text-primary">{inr(r.closing_value)}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message="No stock summary data" />
      )}

      {!loading && tab === "movement" && (
        !selItem ? <EmptyState message="Select an item to view its movement ledger" />
        : data && data.entries?.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Date</th>
            <th className="px-3 py-2.5">Movement</th>
            <th className="px-3 py-2.5">Source</th>
            <th className="px-3 py-2.5 text-right">Qty</th>
            <th className="px-3 py-2.5 text-right">Rate</th>
            <th className="px-3 py-2.5 text-right">Value</th>
          </>}>
            {data.entries.map((e) => (
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
        ) : <EmptyState message="No movements for this item in range" />
      )}

      {!loading && tab === "aging" && (
        data && data.items?.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5 text-right">Closing Qty</th>
            <th className="px-3 py-2.5 text-right">0–30</th>
            <th className="px-3 py-2.5 text-right">31–60</th>
            <th className="px-3 py-2.5 text-right">61–90</th>
            <th className="px-3 py-2.5 text-right">90+</th>
          </>}>
            {data.items.map((r) => (
              <tr key={r.stock_item_id} data-testid={`aging-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">{r.name}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["0-30"])}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["31-60"])}</td>
                <td className="px-3 py-2.5 text-right">{inr(r.buckets["61-90"])}</td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.buckets["90+"])}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message="No stock on hand to age" />
      )}

      {!loading && tab === "low-stock" && (
        Array.isArray(data) && data.length > 0 ? (
          <Table head={<>
            <th className="px-3 py-2.5">Item</th>
            <th className="px-3 py-2.5 text-right">On Hand</th>
            <th className="px-3 py-2.5 text-right">Reorder Level</th>
            <th className="px-3 py-2.5 text-right">Shortfall</th>
            <th className="px-3 py-2.5 text-right">Reorder Qty</th>
          </>}>
            {data.map((r) => (
              <tr key={r.stock_item_id} data-testid={`lowstock-row-${r.stock_item_id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                <td className="px-3 py-2.5 font-semibold">{r.name}</td>
                <td className="px-3 py-2.5 text-right text-amber-400">{inr(r.closing_qty)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.reorder_level)}</td>
                <td className="px-3 py-2.5 text-right text-red-400">{inr(r.shortfall)}</td>
                <td className="px-3 py-2.5 text-right text-muted-foreground">{inr(r.reorder_qty)}</td>
              </tr>
            ))}
          </Table>
        ) : <EmptyState message="No items at or below reorder level" />
      )}
    </div>
  );
}
