import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, EmptyState } from "@/components/ui-kit";
import { ArrowDownCircle, ArrowUpCircle } from "lucide-react";

export default function StockLog() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/stock-transactions").then((r) => setItems(r.data));
  }, []);

  return (
    <div data-testid="stocklog-page">
      <PageHeader
        eyebrow="Inventory"
        title="Stock Log"
        description="Append-only ledger of all stock movements (inwards & outwards)."
      />
      {items.length === 0 ? (
        <EmptyState message="No stock movements yet" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">When</th>
                <th className="px-3 py-2.5">Direction</th>
                <th className="px-3 py-2.5">Product</th>
                <th className="px-3 py-2.5 text-right">Delta</th>
                <th className="px-3 py-2.5 text-right">Balance</th>
                <th className="px-3 py-2.5">Reason</th>
                <th className="px-3 py-2.5">By</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const inward = t.delta > 0;
                return (
                  <tr key={t.id} className="border-t border-zinc-900">
                    <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2">
                      {inward ? (
                        <span className="inline-flex items-center gap-1 text-green-400 font-mono text-xs">
                          <ArrowDownCircle className="w-3.5 h-3.5" /> IN
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-400 font-mono text-xs">
                          <ArrowUpCircle className="w-3.5 h-3.5" /> OUT
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-white">{t.product_name}</td>
                    <td
                      className={`px-3 py-2 text-right tabular font-semibold ${
                        inward ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {inward ? "+" : ""}
                      {t.delta}
                    </td>
                    <td className="px-3 py-2 text-right tabular text-yellow-400">
                      {t.balance}
                    </td>
                    <td className="px-3 py-2 text-zinc-400 text-xs">
                      {t.reason}
                    </td>
                    <td className="px-3 py-2 text-zinc-400 text-xs">
                      {t.user_name}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
