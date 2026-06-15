import { useEffect, useState } from "react";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  SecondaryButton,
} from "@/components/ui-kit";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { Download } from "lucide-react";

const downloadCsv = (filename, rows, cols) => {
  const lines = [cols.join(",")];
  rows.forEach((r) => {
    lines.push(
      cols
        .map((k) => `"${(r[k] ?? "").toString().replace(/"/g, '""')}"`)
        .join(",")
    );
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

export default function Reports() {
  const [profit, setProfit] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [sales, setSales] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [pendingJobWork, setPendingJobWork] = useState([]);

  const loadData = () => {
    api.get("/reports/profit").then((r) => setProfit(r.data));
    api.get("/reports/inventory").then((r) => setInventory(r.data));
    api.get("/reports/sales").then((r) => setSales(r.data));
    api.get("/reports/audit").then((r) => setAuditLogs(r.data)).catch(() => {});
    api.get("/job-work/reports/pending").then((r) => setPendingJobWork(r.data)).catch(() => {});
  };

  useEffect(() => {
    loadData();
  }, []);

  const inr = (n) =>
    Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

  const inventoryByCategory = inventory.reduce((acc, p) => {
    const c = p.category || "Other";
    acc[c] = (acc[c] || 0) + Number(p.quantity || 0) * Number(p.cost_price || 0);
    return acc;
  }, {});
  const pieData = Object.entries(inventoryByCategory).map(([name, value]) => ({
    name,
    value: Math.round(value),
  }));
  const PIE_COLORS = ["#2961BE", "#019E2A", "#DA5E2D", "#8B5CF6", "#F59E0B", "#EF4444"];

  return (
    <div data-testid="reports-page" className="space-y-6">
      <PageHeader
        eyebrow="Insights"
        title="Reports & Analytics"
        description="Inventory, sales and profit-and-loss insights with export-friendly tables."
      />

      {/* Profit summary */}
      {profit && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <StatTile
            label="Total Revenue"
            value={`₹${inr(profit.total_revenue)}`}
            sub={`${profit.rows.length} invoices`}
          />
          <StatTile
            label="Total Cost"
            value={`₹${inr(profit.total_cost)}`}
            sub="At product cost"
          />
          <StatTile
            label="Net Profit"
            value={`₹${inr(profit.total_profit)}`}
            sub={`${
              profit.total_revenue
                ? Math.round(
                    (profit.total_profit / profit.total_revenue) * 100
                  )
                : 0
            }% margin`}
            accent
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-zinc-800 border border-zinc-800">
        <div className="bg-zinc-950 p-5">
          <SectionTitle>Inventory Value by Category</SectionTitle>
          <div className="h-72">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  outerRadius={90}
                  innerRadius={50}
                  paddingAngle={2}
                  label={({ name, percent }) =>
                    `${name} ${(percent * 100).toFixed(0)}%`
                  }
                >
                  {pieData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={i === 0 ? "hsl(var(--primary))" : PIE_COLORS[i % PIE_COLORS.length]}
                      stroke="hsl(var(--card))"
                      strokeWidth={2}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                    fontFamily: "IBM Plex Mono",
                    color: "hsl(var(--foreground))"
                  }}
                  formatter={(v) => `₹${inr(v)}`}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-zinc-950 p-5">
          <SectionTitle>Profit by Invoice</SectionTitle>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={(profit?.rows || []).slice(0, 10)}>
                <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                <XAxis
                  dataKey="invoice_number"
                  stroke="rgb(var(--zinc-500))"
                  tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }}
                />
                <YAxis stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                    fontFamily: "IBM Plex Mono",
                    color: "hsl(var(--foreground))"
                  }}
                />
                <Legend wrapperStyle={{ fontFamily: "IBM Plex Mono", fontSize: 11 }} />
                <Bar dataKey="revenue" fill="rgb(var(--yellow-400))" />
                <Bar dataKey="profit" fill="#019E2A" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>


      {/* Inventory Report */}
      <div className="border border-zinc-800 rounded-md">
        <div className="bg-black px-4 py-3 flex items-center justify-between border-b border-zinc-800">
          <h3 className="font-display font-bold text-white text-sm">
            Inventory Report
          </h3>
          <SecondaryButton
            icon={Download}
            testid="export-inventory"
            onClick={() =>
              downloadCsv(
                `inventory_${new Date().toISOString().slice(0, 10)}.csv`,
                inventory,
                ["sku", "name", "category", "quantity", "cost_price", "selling_price", "low_stock_threshold", "gst_rate"]
              )
            }
          >
            CSV
          </SecondaryButton>
        </div>
        <div className="overflow-x-auto bg-zinc-950">
          <table className="w-full text-sm font-mono">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="text-left label-overline">
                <th className="px-3 py-2">SKU</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Category</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2 text-right">Stock Value</th>
              </tr>
            </thead>
            <tbody>
              {inventory.map((p) => (
                <tr key={p.id} className="border-t border-zinc-900 text-zinc-100">
                  <td className="px-3 py-2 font-mono text-yellow-400 text-xs">
                    {p.sku}
                  </td>
                  <td className="px-3 py-2 text-white">{p.name}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.category}</td>
                  <td className="px-3 py-2 text-right tabular text-white">
                    {p.quantity}
                  </td>
                  <td className="px-3 py-2 text-right tabular text-zinc-300">
                    ₹{inr(p.cost_price)}
                  </td>
                  <td className="px-3 py-2 text-right tabular text-yellow-400 font-semibold">
                    ₹{inr(Number(p.quantity || 0) * Number(p.cost_price || 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sales Report */}
      <div className="border border-zinc-800 rounded-md">
        <div className="bg-black px-4 py-3 flex items-center justify-between border-b border-zinc-800">
          <h3 className="font-display font-bold text-white text-sm">
            Sales Report
          </h3>
          <SecondaryButton
            icon={Download}
            testid="export-sales"
            onClick={() =>
              downloadCsv(
                `sales_${new Date().toISOString().slice(0, 10)}.csv`,
                sales.map((s) => ({
                  invoice_number: s.invoice_number,
                  customer: s.customer_name,
                  total: s.total,
                  payment_received: s.payment_received,
                  status: s.status,
                  date: s.created_at,
                })),
                ["invoice_number", "customer", "total", "payment_received", "status", "date"]
              )
            }
          >
            CSV
          </SecondaryButton>
        </div>
        <div className="overflow-x-auto bg-zinc-950">
          <table className="w-full text-sm font-mono">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="text-left label-overline">
                <th className="px-3 py-2">Invoice#</th>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2 text-right">Total</th>
                <th className="px-3 py-2 text-right">Received</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {sales.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-zinc-500 py-6 font-mono text-xs uppercase">
                    No sales yet
                  </td>
                </tr>
              ) : (
                sales.map((s) => (
                  <tr key={s.id} className="border-t border-zinc-900 text-zinc-100">
                    <td className="px-3 py-2 font-mono text-yellow-400 text-xs">
                      {s.invoice_number}
                    </td>
                    <td className="px-3 py-2 text-white">{s.customer_name}</td>
                    <td className="px-3 py-2 text-right tabular">
                      ₹{inr(s.total)}
                    </td>
                    <td className="px-3 py-2 text-right tabular text-green-400">
                      ₹{inr(s.payment_received)}
                    </td>
                    <td className="px-3 py-2 text-zinc-300">{s.status}</td>
                    <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                      {new Date(s.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pending Job Work Report */}
      <div className="border border-zinc-800 rounded-md">
        <div className="bg-black px-4 py-3 flex items-center justify-between border-b border-zinc-800">
          <h3 className="font-display font-bold text-white text-sm">
            Pending Job Work Material Report
          </h3>
          <SecondaryButton
            icon={Download}
            onClick={() =>
              downloadCsv(
                `pending_job_work_${new Date().toISOString().slice(0, 10)}.csv`,
                pendingJobWork,
                ["challan_number", "job_worker_name", "product_name", "sku", "quantity_sent", "quantity_received", "quantity_pending", "unit"]
              )
            }
          >
            CSV
          </SecondaryButton>
        </div>
        <div className="overflow-x-auto bg-zinc-950">
          <table className="w-full text-sm font-mono">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="text-left label-overline">
                <th className="px-3 py-2">Challan#</th>
                <th className="px-3 py-2">Job Worker</th>
                <th className="px-3 py-2">Material</th>
                <th className="px-3 py-2">SKU</th>
                <th className="px-3 py-2 text-right">Sent</th>
                <th className="px-3 py-2 text-right">Received</th>
                <th className="px-3 py-2 text-right font-bold text-primary">Pending</th>
              </tr>
            </thead>
            <tbody>
              {pendingJobWork.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center text-zinc-500 py-6 font-mono text-xs uppercase">
                    No pending materials at job workers
                  </td>
                </tr>
              ) : (
                pendingJobWork.map((pw, i) => (
                  <tr key={i} className="border-t border-zinc-900 text-zinc-100">
                    <td className="px-3 py-2 font-mono text-xs">{pw.challan_number}</td>
                    <td className="px-3 py-2">{pw.job_worker_name}</td>
                    <td className="px-3 py-2">{pw.product_name}</td>
                    <td className="px-3 py-2 text-zinc-400">{pw.sku}</td>
                    <td className="px-3 py-2 text-right">{pw.quantity_sent}</td>
                    <td className="px-3 py-2 text-right text-green-400">{pw.quantity_received}</td>
                    <td className="px-3 py-2 text-right font-bold text-primary">{pw.quantity_pending} {pw.unit}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit Trail Log Report */}
      <div className="border border-zinc-800 rounded-md">
        <div className="bg-black px-4 py-3 flex items-center justify-between border-b border-zinc-800">
          <h3 className="font-display font-bold text-white text-sm">
            Security & System Audit Trail Log
          </h3>
          <SecondaryButton
            icon={Download}
            onClick={() =>
              downloadCsv(
                `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`,
                auditLogs.map((log) => ({
                  timestamp: log.timestamp,
                  action: log.action,
                  module: log.collection_name,
                  doc_id: log.doc_id,
                  operator: log.user_name
                })),
                ["timestamp", "action", "module", "doc_id", "operator"]
              )
            }
          >
            CSV
          </SecondaryButton>
        </div>
        <div className="overflow-x-auto bg-zinc-950">
          <table className="w-full text-sm font-mono">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="text-left label-overline">
                <th className="px-3 py-2">Timestamp</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Module</th>
                <th className="px-3 py-2">Record ID</th>
                <th className="px-3 py-2">Operator</th>
                <th className="px-3 py-2">Old values</th>
                <th className="px-3 py-2">New values</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center text-zinc-500 py-6 font-mono text-xs uppercase">
                    No audit records logged yet
                  </td>
                </tr>
              ) : (
                auditLogs.map((log) => (
                  <tr key={log.id} className="border-t border-zinc-900 text-zinc-100 text-xs">
                    <td className="px-3 py-2 text-zinc-400 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 font-bold">
                      <span className={`px-1 py-0.5 rounded-sm text-[9px] ${
                        log.action === "CREATE" ? "bg-green-950 text-green-400 border border-green-900" :
                        log.action === "UPDATE" ? "bg-blue-950 text-blue-400 border border-blue-900" :
                        "bg-red-950 text-red-400 border border-red-900"
                      }`}>
                        {log.action}
                      </span>
                    </td>
                    <td className="px-3 py-2 uppercase text-zinc-300">{log.collection_name}</td>
                    <td className="px-3 py-2 text-zinc-500 select-all">{log.doc_id?.substring(0, 8)}...</td>
                    <td className="px-3 py-2 text-white">{log.user_name}</td>
                    <td className="px-3 py-2 text-red-400 max-w-xs truncate" title={JSON.stringify(log.old_values)}>
                      {log.old_values ? JSON.stringify(log.old_values) : "—"}
                    </td>
                    <td className="px-3 py-2 text-green-400 max-w-xs truncate" title={JSON.stringify(log.new_values)}>
                      {log.new_values ? JSON.stringify(log.new_values) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
