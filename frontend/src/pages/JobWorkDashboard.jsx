import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, Card, StatTile, PrimaryButton, SecondaryButton, Spinner } from "@/components/ui-kit";
import { Plus, ArrowDownToLine, FileText, ClipboardList } from "lucide-react";

const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function JobWorkDashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/job-work/dashboard")
      .then((res) => setStats(res.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div data-testid="job-work-dashboard-page">
      <PageHeader
        eyebrow="Manufacturing"
        title="Job Work"
        description="Materials sent to and received from job workers — outward challans and inward receipts, kept strictly separate."
        actions={
          <div className="flex gap-2">
            <SecondaryButton icon={ArrowDownToLine} onClick={() => navigate("/job-work/receipts/new")}>
              New Receipt
            </SecondaryButton>
            <PrimaryButton icon={Plus} onClick={() => navigate("/job-work/challans/new")}>
              New Challan
            </PrimaryButton>
          </div>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
            <StatTile label="Total Challans" value={stats?.total ?? 0} testid="jw-kpi-total" />
            <StatTile label="Pending" value={stats?.pending ?? 0} testid="jw-kpi-pending" />
            <StatTile label="Partial" value={stats?.partial ?? 0} testid="jw-kpi-partial" />
            <StatTile label="Completed" value={stats?.completed ?? 0} accent testid="jw-kpi-completed" />
            <StatTile label="Overdue" value={stats?.overdue ?? 0} testid="jw-kpi-overdue" />
            <StatTile
              label="Material at Job Worker"
              value={inr(stats?.material_at_job_worker_value)}
              sub="Est. value of pending goods"
              testid="jw-kpi-material-value"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="cursor-pointer hover:shadow-md transition-shadow" style={{ borderRadius: "var(--radius-lg)" }}>
              <button className="w-full text-left" onClick={() => navigate("/job-work/reports/challans")}>
                <div className="flex items-center gap-3">
                  <FileText className="w-5 h-5 text-primary" />
                  <div>
                    <div className="font-semibold text-foreground">Job Work Challans</div>
                    <div className="text-xs text-muted-foreground">All outward challans issued</div>
                  </div>
                </div>
              </button>
            </Card>
            <Card className="cursor-pointer hover:shadow-md transition-shadow" style={{ borderRadius: "var(--radius-lg)" }}>
              <button className="w-full text-left" onClick={() => navigate("/job-work/reports/receipts")}>
                <div className="flex items-center gap-3">
                  <ArrowDownToLine className="w-5 h-5 text-primary" />
                  <div>
                    <div className="font-semibold text-foreground">Job Work Receipts</div>
                    <div className="text-xs text-muted-foreground">All inward receipts logged</div>
                  </div>
                </div>
              </button>
            </Card>
            <Card className="cursor-pointer hover:shadow-md transition-shadow" style={{ borderRadius: "var(--radius-lg)" }}>
              <button className="w-full text-left" onClick={() => navigate("/job-work/reports/pending")}>
                <div className="flex items-center gap-3">
                  <ClipboardList className="w-5 h-5 text-primary" />
                  <div>
                    <div className="font-semibold text-foreground">Pending Job Work</div>
                    <div className="text-xs text-muted-foreground">Material still with job workers</div>
                  </div>
                </div>
              </button>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
