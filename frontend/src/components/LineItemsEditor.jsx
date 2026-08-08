import { Plus, Trash2, PenLine, Package } from "lucide-react";
import { NumericInput } from "@/components/ui-kit";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";


const blankRow = () => ({
  product_id: "",
  product_name: "",
  sku: "",
  hsn_code: "",
  unit: DEFAULT_UOM,
  quantity: "",
  unit_price: "",
  gst_rate: "",
  _manual: false,
});

// Safely convert a value to a number for calculations — never NaN.
const n = (v) => {
  const x = parseFloat(v);
  return Number.isFinite(x) ? x : 0;
};

export default function LineItemsEditor({ items, setItems, products }) {
  const addRow = () => setItems([...items, blankRow()]);

  const updateRow = (idx, patch) => {
    const copy = [...items];
    copy[idx] = { ...copy[idx], ...patch };
    if (patch.product_id) {
      const p = products.find((x) => x.id === patch.product_id);
      if (p) {
        copy[idx].product_name = p.name;
        copy[idx].sku = p.sku;
        copy[idx].hsn_code = p.hsn_code || "";
        copy[idx].unit = p.unit || DEFAULT_UOM;
        // Pre-fill from catalog but keep as numbers (not strings) so they
        // display immediately — NumericInput handles display conversion.
        copy[idx].unit_price = p.selling_price != null ? Number(p.selling_price) : "";
        copy[idx].gst_rate = p.gst_rate != null ? Number(p.gst_rate) : "";
      }
    }
    setItems(copy);
  };

  const toggleManual = (idx) => {
    const copy = [...items];
    const isManual = !copy[idx]._manual;
    copy[idx] = { ...copy[idx], _manual: isManual, product_id: "", product_name: "", sku: "" };
    setItems(copy);
  };

  const removeRow = (idx) => setItems(items.filter((_, i) => i !== idx));
  const insertRowAfter = (idx) => {
    const copy = [...items];
    copy.splice(idx + 1, 0, blankRow());
    setItems(copy);
  };
  const removeRowKeepingNone = (idx) => setItems(items.filter((_, i) => i !== idx));

  // Tally-style row×column keyboard nav (see useGridKeyNav): Product → [SKU
  // if manual] → HSN → Qty → Unit → Rate → GST, Enter on the last cell of the
  // last row appends a fresh row. Manual-entry rows have one extra column
  // (product name + SKU as separate cells) vs catalog rows (a single
  // product <select>), so colCount varies per row exactly like SalesOrders.jsx.
  const colsForRow = (row) => (items[row]?._manual ? 7 : 6);
  const gridNav = useGridKeyNav({
    rowCount: items.length,
    colCount: colsForRow,
    onRowComplete: addRow,
    onInsertRow: insertRowAfter,
    onDeleteRow: removeRowKeepingNone,
  });
  // Column index of a given field depends on manual vs catalog shape:
  //   catalog: 0=product select, 1=HSN, 2=Qty, 3=Unit, 4=Rate, 5=GST
  //   manual:  0=product name, 1=SKU, 2=HSN, 3=Qty, 4=Unit, 5=Rate, 6=GST
  const col = (row, field) => {
    const manual = items[row]?._manual;
    const idx = { product: 0, sku: 1, hsn: manual ? 2 : 1, qty: manual ? 3 : 2, unit: manual ? 4 : 3, rate: manual ? 5 : 4, gst: manual ? 6 : 5 };
    return idx[field];
  };

  let subtotal = 0;
  let gst = 0;
  items.forEach((i) => {
    const line = n(i.quantity) * n(i.unit_price);
    subtotal += line;
    gst += (line * n(i.gst_rate)) / 100;
  });
  const total = subtotal + gst;

  return (
    <div className="border border-border bg-card text-card-foreground" data-grid-managed>
      <div className="bg-muted px-3 py-2 flex items-center justify-between">
        <div className="label-overline text-muted-foreground">Line Items</div>
        <button
          type="button"
          data-testid="add-line"
          onClick={addRow}
          className="inline-flex items-center gap-1 text-xs font-mono uppercase tracking-wider text-primary hover:opacity-80 transition-opacity"
        >
          <Plus className="w-3.5 h-3.5" /> Add line
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left label-overline border-b border-border bg-muted/20 text-muted-foreground">
              <th className="px-2 py-2 w-7" title="Toggle catalog / manual entry" />
              <th className="px-2 py-2">Product</th>
              <th className="px-2 py-2 w-24">HSN Code</th>
              <th className="px-2 py-2 w-20 text-right">Qty</th>
              <th className="px-2 py-2 w-20">Unit</th>
              <th className="px-2 py-2 w-32 text-right">Unit ₹</th>
              <th className="px-2 py-2 w-20 text-right">GST %</th>
              <th className="px-2 py-2 w-28 text-right">Line Total</th>
              <th className="px-2 py-2 w-8" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center text-muted-foreground py-6 font-mono text-xs uppercase">
                  No line items — click "Add line"
                </td>
              </tr>
            ) : (
              items.map((it, idx) => {
                const line = n(it.quantity) * n(it.unit_price);
                return (
                  <tr key={idx} className="border-b border-border">
                    {/* Catalog / Manual toggle */}
                    <td className="px-1 py-1.5">
                      <button
                        type="button"
                        title={it._manual ? "Switch to catalog" : "Enter manually"}
                        onClick={() => toggleManual(idx)}
                        className={`w-6 h-6 flex items-center justify-center border transition-colors ${it._manual ? "border-amber-500 text-amber-400" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                      >
                        {it._manual ? <PenLine className="w-3 h-3" /> : <Package className="w-3 h-3" />}
                      </button>
                    </td>
                    <td className="px-2 py-1.5">
                      {it._manual ? (
                        <div className="flex gap-1">
                          <input
                            placeholder="Product name"
                            value={it.product_name}
                            onChange={(e) => updateRow(idx, { product_name: e.target.value })}
                            ref={gridNav.registerCell(idx, col(idx, "product"))}
                            onKeyDown={gridNav.handleKeyDown(idx, col(idx, "product"))}
                            className="flex-1 bg-background border border-amber-500/60 text-foreground text-sm px-2 py-1 focus:border-amber-400 focus:outline-none transition-colors min-w-0"
                          />
                          <input
                            placeholder="SKU"
                            value={it.sku}
                            onChange={(e) => updateRow(idx, { sku: e.target.value })}
                            ref={gridNav.registerCell(idx, col(idx, "sku"))}
                            onKeyDown={gridNav.handleKeyDown(idx, col(idx, "sku"))}
                            className="w-24 bg-background border border-amber-500/60 text-foreground text-sm px-2 py-1 focus:border-amber-400 focus:outline-none transition-colors font-mono"
                          />
                        </div>
                      ) : (
                        <select
                          value={it.product_id}
                          onChange={(e) => updateRow(idx, { product_id: e.target.value })}
                          ref={gridNav.registerCell(idx, col(idx, "product"))}
                          onKeyDown={gridNav.handleKeyDown(idx, col(idx, "product"))}
                          className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none transition-colors"
                        >
                          <option value="">Select product…</option>
                          {products.map((p) => {
                            const isSelectedElsewhere = items.some((x, i) => i !== idx && x.product_id === p.id);
                            return (
                              <option key={p.id} value={p.id} disabled={isSelectedElsewhere}>
                                {p.name} ({p.sku})
                              </option>
                            );
                          })}
                        </select>
                      )}
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        placeholder="HSN/SAC"
                        value={it.hsn_code || ""}
                        onChange={(e) => updateRow(idx, { hsn_code: e.target.value })}
                        ref={gridNav.registerCell(idx, col(idx, "hsn"))}
                        onKeyDown={gridNav.handleKeyDown(idx, col(idx, "hsn"))}
                        className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none transition-colors font-mono"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <NumericInput
                        compact
                        value={it.quantity}
                        onChange={(v) => updateRow(idx, { quantity: v })}
                        placeholder="0"
                        ref={gridNav.registerCell(idx, col(idx, "qty"))}
                        onKeyDown={gridNav.handleKeyDown(idx, col(idx, "qty"))}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <select
                        value={it.unit || DEFAULT_UOM}
                        onChange={(e) => updateRow(idx, { unit: e.target.value })}
                        ref={gridNav.registerCell(idx, col(idx, "unit"))}
                        onKeyDown={gridNav.handleKeyDown(idx, col(idx, "unit"))}
                        className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none transition-colors"
                      >
                        {it.unit && !STANDARD_UOMS.includes(it.unit) && (
                          <option key={it.unit} value={it.unit}>{it.unit}</option>
                        )}
                        {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-1.5">
                      <NumericInput
                        compact
                        value={it.unit_price}
                        onChange={(v) => updateRow(idx, { unit_price: v })}
                        placeholder="0.00"
                        ref={gridNav.registerCell(idx, col(idx, "rate"))}
                        onKeyDown={gridNav.handleKeyDown(idx, col(idx, "rate"))}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <NumericInput
                        compact
                        value={it.gst_rate}
                        onChange={(v) => updateRow(idx, { gst_rate: v })}
                        placeholder="0"
                        ref={gridNav.registerCell(idx, col(idx, "gst"))}
                        onKeyDown={gridNav.handleKeyDown(idx, col(idx, "gst"))}
                      />
                    </td>
                    <td className="px-2 py-1.5 text-right tabular text-primary font-semibold">
                      ₹{line.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                    </td>
                    <td className="px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => removeRow(idx)}
                        className="text-muted-foreground hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
          <tfoot>
            <tr className="border-t border-border bg-muted">
              <td colSpan={7} className="px-2 py-2 text-right label-overline text-muted-foreground">
                Subtotal
              </td>
              <td className="px-2 py-2 text-right tabular text-foreground">
                ₹{subtotal.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </td>
              <td />
            </tr>
            <tr className="bg-muted">
              <td colSpan={7} className="px-2 py-2 text-right label-overline text-muted-foreground">
                GST
              </td>
              <td className="px-2 py-2 text-right tabular text-foreground">
                ₹{gst.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </td>
              <td />
            </tr>
            <tr className="bg-primary text-primary-foreground">
              <td colSpan={7} className="px-2 py-2 text-right font-display font-bold uppercase tracking-wider">
                Total
              </td>
              <td className="px-2 py-2 text-right tabular font-display font-black text-lg">
                ₹{total.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
