// Split out from Dashboard.jsx so recharts (the single largest lazy chunk in
// the app, ~380KB) is only fetched/parsed once the dashboard actually needs
// to render a chart, not bundled into Dashboard.jsx's own chunk. Dashboard.jsx
// lazy-loads this module and shows ChartCard's existing skeleton as the
// Suspense fallback while it loads.
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border p-3 shadow-lg rounded-[var(--radius-sm)] text-xs">
        <p className="font-bold text-muted-foreground uppercase tracking-wider text-[10px] mb-1.5">{label}</p>
        {payload.map((p, idx) => (
          <p key={idx} className="font-semibold flex items-center justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: p.color || p.fill }} />
              {p.name}
            </span>
            <span className="font-mono text-foreground font-bold">₹{Number(p.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export function SalesAreaChart({ data, shortInr }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={64} tickFormatter={shortInr} />
        <Tooltip content={<CustomTooltip />} />
        <Area type="monotone" dataKey="value" name="Revenue" stroke="hsl(var(--primary))" strokeWidth={2.5} fill="url(#salesGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ExpenseIncomeBarChart({ data, shortInr }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }} barGap={4}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={64} tickFormatter={shortInr} />
        <Tooltip content={<CustomTooltip />} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: "11px" }} />
        <Bar dataKey="income" name="Income" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} maxBarSize={14} />
        <Bar dataKey="expense" name="Expense" fill="hsl(var(--secondary))" radius={[3, 3, 0, 0]} maxBarSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}
