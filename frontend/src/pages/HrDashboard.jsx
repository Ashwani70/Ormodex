import { useEffect, useState } from "react";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  PrimaryButton,
} from "@/components/ui-kit";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Link } from "react-router-dom";
import { Users, Calendar, CalendarDays, IndianRupee, Building2 } from "lucide-react";

export default function HrDashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/hr/dashboard").then((r) => setData(r.data));
  }, []);

  const k = data?.kpis || {};

  return (
    <div data-testid="hr-dashboard-page">
      <PageHeader
        eyebrow="HRM"
        title="HR Mission Control"
        description="Headcount, attendance, leave queue, and payroll status at a glance."
        actions={
          <Link to="/hr/payroll">
            <PrimaryButton icon={IndianRupee} testid="goto-payroll">
              Run Payroll
            </PrimaryButton>
          </Link>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatTile label="Active Employees" value={k.total_employees ?? 0} testid="kpi-employees" />
        <StatTile label="Branches" value={k.branches ?? 0} />
        <StatTile label="Departments" value={k.departments ?? 0} />
        <StatTile
          label="Present Today"
          value={k.present_today ?? 0}
          sub={`${k.absent_today ?? 0} absent`}
          accent
        />
        <StatTile
          label="Pending Leaves"
          value={k.pending_leaves ?? 0}
          sub="Awaiting approval"
        />
        <StatTile
          label="Latest Payroll"
          value={k.latest_run || "—"}
          sub={k.latest_run_status ? `${k.latest_run_employees} emp · ${k.latest_run_status}` : "Not yet run"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-px bg-zinc-800 border border-zinc-800">
        <div className="lg:col-span-2 bg-zinc-950 p-5">
          <SectionTitle>Headcount by department</SectionTitle>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.by_department || []}>
                <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                <XAxis dataKey="department" stroke="rgb(var(--zinc-500))" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
                <YAxis stroke="rgb(var(--zinc-500))" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "var(--radius)",
                    fontFamily: "IBM Plex Mono",
                    color: "hsl(var(--foreground))"
                  }}
                />
                <Bar dataKey="count" fill="rgb(var(--yellow-400))" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-zinc-950 p-5">
          <SectionTitle>Quick Access</SectionTitle>
          <div className="space-y-px bg-zinc-800">
            {[
              { to: "/hr/employees", label: "Employees", icon: Users },
              { to: "/hr/attendance", label: "Attendance", icon: Calendar },
              { to: "/hr/leaves", label: "Leaves", icon: CalendarDays },
              { to: "/hr/payroll", label: "Payroll", icon: IndianRupee },
              { to: "/hr/settings", label: "HR Settings", icon: Building2 },
            ].map((q) => {
              const Icon = q.icon;
              return (
                <Link
                  key={q.to}
                  to={q.to}
                  className="flex items-center justify-between bg-zinc-950 hover:bg-zinc-900 p-3 group transition-colors"
                >
                  <span className="flex items-center gap-3 text-white text-sm">
                    <Icon className="w-4 h-4 text-yellow-400" />
                    {q.label}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500 group-hover:text-yellow-400">
                    Open →
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
