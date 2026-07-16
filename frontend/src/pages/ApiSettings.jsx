import { useEffect, useRef, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  SectionTitle,
  EmptyState,
} from "@/components/ui-kit";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { Settings, Save, ShieldAlert, CheckCircle, AlertTriangle, Eye, EyeOff, Sparkles } from "lucide-react";

export default function ApiSettings() {
  const [form, setForm] = useState({
    gst_api_key: "",
    gst_api_enabled: true,
    pan_api_key: "",
    pan_api_enabled: true,
    aadhaar_api_key: "",
    aadhaar_api_enabled: true,
    gemini_api_key: "",
  });
  const [showKeys, setShowKeys] = useState({ gst: false, pan: false, aadhaar: false, gemini: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // GST provider connection health (admin "Test Connection")
  const [gstHealth, setGstHealth] = useState(null);
  const [testingGst, setTestingGst] = useState(false);

  const testGstConnection = async () => {
    setTestingGst(true);
    try {
      const r = await api.get("/verifications/gst/health");
      setGstHealth(r.data);
      if (r.data.authenticated) {
        if (r.data.warning) {
          toast.warning(`Key authenticates, but: ${r.data.warning}`);
        } else {
          toast.success("Connected to GST provider.");
        }
      } else if (!r.data.configured) {
        toast.warning("GST provider is not configured.");
      } else {
        toast.error("GST authentication failed.");
      }
    } catch (e) {
      setGstHealth({ configured: false, authenticated: false, error: "Health check failed." });
      toast.error("Unable to reach GST health endpoint.");
    } finally {
      setTestingGst(false);
    }
  };

  // Pagination for logs
  const [logs, setLogs] = useState([]);
  const [totalLogs, setTotalLogs] = useState(0);
  const [page, setPage] = useState(1);
  const limit = 20;

  const loadSettings = async () => {
    try {
      const r = await api.get("/verifications/settings");
      setForm(r.data);
    } catch (e) {
      toast.error("Failed to load API settings.");
    }
  };

  const loadLogs = async () => {
    try {
      const r = await api.get("/verifications/logs", { params: { page, limit } });
      setLogs(r.data.items);
      setTotalLogs(r.data.total);
    } catch (e) {
      toast.error("Failed to load verification logs.");
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([loadSettings(), loadLogs()]);
      setLoading(false);
    };
    init();
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/verifications/settings", form);
      toast.success("Verification settings saved successfully.");
      loadSettings();
      loadLogs();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab across the credentials form; Ctrl+Enter/Ctrl+S saves, first
  // field auto-focuses once settings have loaded. Always-visible settings
  // page — no modal, so there's no cancel action.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: !loading,
    autoFocus: true,
    onSave: () => handleSave(new Event("submit", { cancelable: true })),
  });

  return (
    <div data-testid="api-settings-page" className="space-y-6">
      <PageHeader
        eyebrow="System Configuration"
        title="Verification API Settings"
        description="Configure API integration credentials, toggles, and view access audit logs."
      />

      {loading ? (
        <div className="flex flex-col items-center justify-center p-24 border border-zinc-800 bg-zinc-950">
          <Settings className="w-8 h-8 text-yellow-400 animate-spin mb-4" />
          <p className="font-mono text-xs uppercase text-zinc-500 tracking-widest">Hydrating configurations...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Settings form column */}
          <div className="lg:col-span-1 border border-zinc-800 bg-zinc-950 p-6 rounded-md shadow-lg flex flex-col justify-between">
            <form ref={formRef} onSubmit={handleSave} className="space-y-4">
              <SectionTitle>API Credentials</SectionTitle>

              {/* GST API Settings */}
              <div className="border border-zinc-900 bg-zinc-900/10 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white">GST Validation API</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.gst_api_enabled}
                      onChange={(e) => setForm({ ...form, gst_api_enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-yellow-400 peer-checked:after:bg-black peer-checked:after:border-black"></div>
                  </label>
                </div>
                <Field label="GST Provider">
                  <select
                    value={form.gst_provider || "gstverify"}
                    onChange={(e) => setForm({ ...form, gst_provider: e.target.value })}
                    disabled={!form.gst_api_enabled}
                    className="w-full bg-zinc-950 border border-zinc-800 text-white font-mono text-xs px-3 py-2 rounded disabled:opacity-50"
                  >
                    <option value="gstverify">GSTVerify (gstverify.co.in)</option>
                    <option value="rapidapi">RapidAPI (gst-return-status)</option>
                    <option value="rapidapi_insights">RapidAPI (gst-insights-api)</option>
                  </select>
                </Field>
                <Field label="GST API Secret Key">
                  <div className="flex gap-2">
                    <Input
                      type={showKeys.gst ? "text" : "password"}
                      value={form.gst_api_key}
                      onChange={(e) => setForm({ ...form, gst_api_key: e.target.value })}
                      placeholder="Enter GST API key"
                      disabled={!form.gst_api_enabled}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKeys({ ...showKeys, gst: !showKeys.gst })}
                      className="p-2 border border-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center"
                    >
                      {showKeys.gst ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </Field>

                {/* Test Connection — live auth round-trip (consumes one credit) */}
                <div className="flex items-center justify-between gap-2 pt-1">
                  <SecondaryButton
                    type="button"
                    onClick={testGstConnection}
                    disabled={testingGst || !form.gst_api_enabled}
                    title="Performs a live lookup to verify the key — uses one provider credit"
                  >
                    {testingGst ? "Testing..." : "Test Connection"}
                  </SecondaryButton>
                  {gstHealth && (
                    <span className="font-mono text-xs flex items-center gap-1.5">
                      {gstHealth.authenticated ? (
                        <span className="text-green-400">🟢 Connected</span>
                      ) : !gstHealth.configured ? (
                        <span className="text-yellow-400">🟡 Not configured</span>
                      ) : (
                        <span className="text-red-400">🔴 Authentication failed</span>
                      )}
                    </span>
                  )}
                </div>
                {gstHealth && (
                  <p className="font-mono text-[10px] text-zinc-500 leading-relaxed">
                    {gstHealth.authenticated
                      ? `Provider: ${gstHealth.provider} · Env: ${gstHealth.environment}`
                      : gstHealth.error}
                    {gstHealth.warning ? ` · ⚠ ${gstHealth.warning}` : ""}
                    {gstHealth.note ? ` · ${gstHealth.note}` : ""}
                    {gstHealth.last_checked_at ? ` · Checked ${new Date(gstHealth.last_checked_at).toLocaleTimeString("en-IN")}` : ""}
                  </p>
                )}
              </div>

              {/* PAN API Settings */}
              <div className="border border-zinc-900 bg-zinc-900/10 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white">PAN Verification API</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.pan_api_enabled}
                      onChange={(e) => setForm({ ...form, pan_api_enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-yellow-400 peer-checked:after:bg-black peer-checked:after:border-black"></div>
                  </label>
                </div>
                <Field label="PAN API Secret Key">
                  <div className="flex gap-2">
                    <Input
                      type={showKeys.pan ? "text" : "password"}
                      value={form.pan_api_key}
                      onChange={(e) => setForm({ ...form, pan_api_key: e.target.value })}
                      placeholder="Enter PAN API key"
                      disabled={!form.pan_api_enabled}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKeys({ ...showKeys, pan: !showKeys.pan })}
                      className="p-2 border border-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center"
                    >
                      {showKeys.pan ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </Field>
              </div>

              {/* Aadhaar API Settings */}
              <div className="border border-zinc-900 bg-zinc-900/10 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white">Aadhaar Validation API</span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.aadhaar_api_enabled}
                      onChange={(e) => setForm({ ...form, aadhaar_api_enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-yellow-400 peer-checked:after:bg-black peer-checked:after:border-black"></div>
                  </label>
                </div>
                <Field label="Aadhaar API Secret Key">
                  <div className="flex gap-2">
                    <Input
                      type={showKeys.aadhaar ? "text" : "password"}
                      value={form.aadhaar_api_key}
                      onChange={(e) => setForm({ ...form, aadhaar_api_key: e.target.value })}
                      placeholder="Enter Aadhaar API key"
                      disabled={!form.aadhaar_api_enabled}
                    />
                    <button
                      type="button"
                      onClick={() => setShowKeys({ ...showKeys, aadhaar: !showKeys.aadhaar })}
                      className="p-2 border border-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center"
                    >
                      {showKeys.aadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </Field>
              </div>

              {/* AI Copilot Settings */}
              <div className="border border-zinc-900 bg-zinc-900/10 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-yellow-400" /> AI Copilot Integrations
                  </span>
                </div>
                <Field label="Gemini API Key (for Gemini 3.5)">
                  <div className="flex gap-2">
                    <Input
                      type={showKeys.gemini ? "text" : "password"}
                      value={form.gemini_api_key || ""}
                      onChange={(e) => setForm({ ...form, gemini_api_key: e.target.value })}
                      placeholder="AIzaSy..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowKeys({ ...showKeys, gemini: !showKeys.gemini })}
                      className="p-2 border border-zinc-800 text-zinc-400 hover:text-white flex items-center justify-center"
                    >
                      {showKeys.gemini ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </Field>
              </div>

              <div className="pt-2">
                <PrimaryButton type="submit" disabled={saving} icon={Save}>
                  {saving ? "Saving..." : "Save Settings"}
                </PrimaryButton>
              </div>
            </form>
          </div>

          {/* Audit log column */}
          <div className="lg:col-span-2 border border-zinc-800 bg-zinc-950 p-6 rounded-md shadow-lg flex flex-col justify-between min-h-[500px]">
            <div>
              <SectionTitle>API Usage & Audit logs</SectionTitle>
              <div className="overflow-x-auto mt-4">
                {logs.length > 0 ? (
                  <table className="w-full text-sm font-mono text-left">
                    <thead className="bg-zinc-900 text-zinc-400">
                      <tr className="border-b border-zinc-800 label-overline">
                        <th className="px-3 py-2.5">Timestamp</th>
                        <th className="px-3 py-2.5">User</th>
                        <th className="px-3 py-2.5">Type</th>
                        <th className="px-3 py-2.5">ID Checked</th>
                        <th className="px-3 py-2.5">Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((log) => (
                        <tr
                          key={log.id}
                          className="border-b border-zinc-900 hover:bg-zinc-900/60 text-zinc-100 text-xs"
                        >
                          <td className="px-3 py-2.5 text-zinc-500">
                            {new Date(log.created_at).toLocaleString("en-IN")}
                          </td>
                          <td className="px-3 py-2.5 text-zinc-300 font-bold">{log.user_name}</td>
                          <td className="px-3 py-2.5">
                            <span className="bg-zinc-800 text-yellow-400 px-1.5 py-0.5 rounded-sm">
                              {log.type}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-white font-semibold">{log.value}</td>
                          <td className="px-3 py-2.5">
                            {log.success ? (
                              <span className="text-green-400 inline-flex items-center gap-1">
                                <CheckCircle className="w-3 h-3" /> OK
                              </span>
                            ) : (
                              <span className="text-red-400 inline-flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" /> FAILED
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <EmptyState message="No API logs found." />
                )}
              </div>
            </div>

            {/* Pagination */}
            {totalLogs > limit && (
              <div className="flex items-center justify-between border-t border-zinc-900 pt-4 mt-4">
                <span className="text-xs text-zinc-500 font-mono">
                  Showing {(page - 1) * limit + 1} - {Math.min(page * limit, totalLogs)} of {totalLogs} logs
                </span>
                <div className="flex gap-2">
                  <SecondaryButton
                    disabled={page === 1}
                    onClick={() => setPage(page - 1)}
                  >
                    Previous
                  </SecondaryButton>
                  <SecondaryButton
                    disabled={page * limit >= totalLogs}
                    onClick={() => setPage(page + 1)}
                  >
                    Next
                  </SecondaryButton>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
