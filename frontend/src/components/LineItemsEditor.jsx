import { Plus, Trash2 } from "lucide-react";

export default function LineItemsEditor({ items, setItems, products }) {
  const addRow = () => {
    setItems([
      ...items,
      {
        product_id: "",
        product_name: "",
        sku: "",
        quantity: 1,
        unit_price: 0,
        gst_rate: 18,
      },
    ]);
  };

  const updateRow = (idx, patch) => {
    const copy = [...items];
    copy[idx] = { ...copy[idx], ...patch };
    if (patch.product_id) {
      const p = products.find((x) => x.id === patch.product_id);
      if (p) {
        copy[idx].product_name = p.name;
        copy[idx].sku = p.sku;
        copy[idx].unit_price = Number(p.selling_price || 0);
        copy[idx].gst_rate = Number(p.gst_rate || 18);
      }
    }
    setItems(copy);
  };

  const removeRow = (idx) => setItems(items.filter((_, i) => i !== idx));

  let subtotal = 0;
  let gst = 0;
  items.forEach((i) => {
    const line = Number(i.quantity || 0) * Number(i.unit_price || 0);
    subtotal += line;
    gst += (line * Number(i.gst_rate || 0)) / 100;
  });
  const total = subtotal + gst;

  return (
    <div className="border border-border bg-card text-card-foreground">
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
              <th className="px-2 py-2">Product</th>
              <th className="px-2 py-2 w-20 text-right">Qty</th>
              <th className="px-2 py-2 w-32 text-right">Unit ₹</th>
              <th className="px-2 py-2 w-20 text-right">GST %</th>
              <th className="px-2 py-2 w-28 text-right">Line Total</th>
              <th className="px-2 py-2 w-8" />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center text-muted-foreground py-6 font-mono text-xs uppercase">
                  No line items — click "Add line"
                </td>
              </tr>
            ) : (
              items.map((it, idx) => {
                const line = Number(it.quantity || 0) * Number(it.unit_price || 0);
                return (
                  <tr key={idx} className="border-b border-border">
                    <td className="px-2 py-1.5">
                      <select
                        value={it.product_id}
                        onChange={(e) => updateRow(idx, { product_id: e.target.value })}
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
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        type="number"
                        step="0.01"
                        value={it.quantity}
                        onChange={(e) => updateRow(idx, { quantity: e.target.value })}
                        className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none text-right tabular transition-colors"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        type="number"
                        step="0.01"
                        value={it.unit_price}
                        onChange={(e) => updateRow(idx, { unit_price: e.target.value })}
                        className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none text-right tabular transition-colors"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        type="number"
                        step="0.01"
                        value={it.gst_rate}
                        onChange={(e) => updateRow(idx, { gst_rate: e.target.value })}
                        className="w-full bg-background border border-input text-foreground text-sm px-2 py-1 focus:border-primary focus:outline-none text-right tabular transition-colors"
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
              <td colSpan={4} className="px-2 py-2 text-right label-overline text-muted-foreground">
                Subtotal
              </td>
              <td className="px-2 py-2 text-right tabular text-foreground">
                ₹{subtotal.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </td>
              <td />
            </tr>
            <tr className="bg-muted">
              <td colSpan={4} className="px-2 py-2 text-right label-overline text-muted-foreground">
                GST
              </td>
              <td className="px-2 py-2 text-right tabular text-foreground">
                ₹{gst.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </td>
              <td />
            </tr>
            <tr className="bg-primary text-primary-foreground">
              <td colSpan={4} className="px-2 py-2 text-right font-display font-bold uppercase tracking-wider">
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
