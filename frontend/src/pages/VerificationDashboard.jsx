import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  PrimaryButton,
  SecondaryButton,
  EmptyState,
} from "@/components/ui-kit";
import { toast } from "sonner";
import { RefreshCw, Shield, AlertTriangle, CheckCircle, FileText, Settings } from "lucide-react";

export default function VerificationDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchDashboardData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);

    try {
      const r = await api.get("/verifications/dashboard");
      setData(r.data);
      if (isManual) {
        toast.success("Verification stats and recent logs refreshed.");
      }
    } catch (err) {
      toast.error("Failed to load verification dashboard metrics.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  return (
    <div data-testid="verification-dashboard-page" className="space-y-6">
      <PageHeader
        eyebrow="Verification Hub"
        title="Verification Dashboard"
        description="Verify and audit GSTIN, PAN, and Aadhaar numbers for parties."
        actions={
          <div className="flex gap-2">
            <SecondaryButton
              icon={RefreshCw}
              onClick={() => fetchDashboardData(true)}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </SecondaryButton>
            <Link to="/verifications/settings">
              <PrimaryButton icon={Settings}>
                API Settings
              </PrimaryButton>
            </Link>
          </div>
        }
      />

      {loading ? (
        <div className="flex flex-col items-center justify-center p-24 border border-zinc-800 bg-zinc-950">
          <RefreshCw className="w-8 h-8 text-yellow-400 animate-spin mb-4" />
          <p className="font-mono text-xs uppercase text-zinc-500 tracking-widest">Hydrating stats...</p>
        </div>
      ) : (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              label="Total Customers"
              value={data?.total_customers ?? 0}
              sub="Registered customer records"
            />
            <StatTile
              label="Total Vendors"
              value={data?.total_vendors ?? 0}
              sub="Registered vendor records"
            />
            <StatTile
              label="Active GST Status"
              value={data?.active_gst ?? 0}
              sub="Verified active GSTINs"
              accent
            />
            <StatTile
              label="Invalid GST Status"
              value={data?.invalid_gst ?? 0}
              sub="Unverified or inactive GSTINs"
            />
          </div>

          {/* Recent verifications list */}
          <div className="border border-zinc-800 bg-zinc-950 rounded-md p-6 shadow-lg">
            <SectionTitle>Recent Verification Activities</SectionTitle>
            <div className="overflow-x-auto mt-4">
              {data?.recent_verifications?.length > 0 ? (
                <table className="w-full text-sm font-mono text-left">
                  <thead className="bg-zinc-900 text-zinc-400">
                    <tr className="border-b border-zinc-800 label-overline">
                      <th className="px-3 py-2.5">Date & Time</th>
                      <th className="px-3 py-2.5">Verified By</th>
                      <th className="px-3 py-2.5">Type</th>
                      <th className="px-3 py-2.5">Value Checked</th>
                      <th className="px-3 py-2.5">Status</th>
                      <th className="px-3 py-2.5">Entity / Owner Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_verifications.map((log) => (
                      <tr
                        key={log.id}
                        className="border-b border-zinc-900 hover:bg-zinc-900/60 text-zinc-100"
                      >
                        <td className="px-3 py-2.5 text-zinc-400 text-xs">
                          {new Date(log.created_at).toLocaleString("en-IN")}
                        </td>
                        <td className="px-3 py-2.5 text-zinc-300">{log.user_name}</td>
                        <td className="px-3 py-2.5">
                          <span className="bg-zinc-800 text-yellow-400 px-1.5 py-0.5 text-[10px] rounded-sm font-semibold">
                            {log.type}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-white font-semibold">{log.value}</td>
                        <td className="px-3 py-2.5">
                          {log.success ? (
                            <span className="inline-flex items-center gap-1 text-xs text-green-400">
                              <CheckCircle className="w-3.5 h-3.5" /> VERIFIED
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-red-400">
                              <AlertTriangle className="w-3.5 h-3.5" /> FAILED
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-zinc-400 text-xs truncate max-w-xs">
                          {log.type === "GST" && log.result?.is_valid && (
                            <span>{log.result.legal_name || "—"} ({log.result.portal_status})</span>
                          )}
                          {log.type === "PAN" && log.result?.is_valid && (
                            <span>{log.result.pan_holder_name || "—"} ({log.result.pan_type})</span>
                          )}
                          {log.type === "AADHAAR" && log.result?.is_valid && (
                            <span>{log.result.aadhaar_holder_name || "—"} ({log.result.aadhaar_status})</span>
                          )}
                          {!log.success && <span className="text-red-500">{log.result?.error || "Invalid entry"}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState message="No verifications logged yet." />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
