import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, Card, StatTile, Badge, EmptyState,
  PrimaryButton, SecondaryButton, Input, Select, Field, Spinner,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import {
  Fingerprint, Plus, RefreshCw, Trash2, KeyRound, Wifi, WifiOff,
  AlertTriangle, CheckCircle2, Clock, ListTree, Check, X, ClipboardEdit,
} from "lucide-react";

const TABS = ["Dashboard", "Devices", "Employee Mapping", "Raw Logs", "Sync History", "Rules", "Corrections"];

function healthTone(health) {
  if (health === "healthy") return "success";
  if (health === "stale") return "warning";
  if (health === "never_synced") return "neutral";
  return "danger";
}

// StatusBadge's shared STATUS_TONE map (ui-kit.jsx) doesn't know this module's
// sync-run/device statuses — using Badge directly with an explicit tone here
// instead of extending the app-wide map for statuses only this page renders.
function syncStatusTone(status) {
  const s = (status || "").toUpperCase();
  if (s === "SUCCESS") return "success";
  if (s === "FAILED") return "danger";
  if (s === "RUNNING" || s === "RETRYING") return "warning";
  return "neutral";
}

// ════════════════════════════════════════════ Dashboard ════════════════════════════════════════════
function DashboardTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/dashboard");
      setData(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;
  if (!data) return <EmptyState message="Could not load dashboard" />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Devices" value={data.devices_total} sub={`${data.devices_healthy} healthy`} />
        <StatTile label="Present Today" value={data.present_today} sub={`of ${data.active_employees} active`} accent />
        <StatTile label="Punches Today" value={data.punches_today} />
        <StatTile label="Pending / Failed Syncs" value={data.pending_or_failed_sync_runs} sub={data.unmapped_punches_recent > 0 ? `${data.unmapped_punches_recent} unmapped punches` : undefined} />
      </div>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-foreground">Device Health</h3>
          <SecondaryButton icon={RefreshCw} onClick={load} testid="refresh-dashboard">Refresh</SecondaryButton>
        </div>
        {data.device_health.length === 0 ? (
          <EmptyState message="No devices registered yet" />
        ) : (
          <div className="space-y-2">
            {data.device_health.map((d) => (
              <div key={d.device_id} className="flex items-center justify-between border border-border p-3" style={{ borderRadius: "var(--radius-md)" }}>
                <div className="flex items-center gap-3">
                  {d.health === "healthy" ? <Wifi className="w-4 h-4 text-[var(--success)]" /> : <WifiOff className="w-4 h-4 text-muted-foreground" />}
                  <div>
                    <div className="font-medium text-foreground">{d.device_name}</div>
                    <div className="text-xs text-muted-foreground">Last seen: {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "never"}</div>
                  </div>
                </div>
                <Badge tone={healthTone(d.health)}>{d.health.replace("_", " ")}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════ Devices ════════════════════════════════════════════
function DevicesTab() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [secretModal, setSecretModal] = useState(null); // { name, push_secret }
  const [form, setForm] = useState({
    name: "", serial_number: "", device_model: "", integration_mode: "push",
    host: "", port: 4370, api_path: "", poll_interval_seconds: 300, notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [syncingId, setSyncingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/devices");
      setDevices(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.name) return toast.error("Device name is required");
    if (form.integration_mode === "poll" && !form.host) return toast.error("Host is required for poll-mode devices");
    setSaving(true);
    try {
      const { data } = await api.post("/biometric/devices", { ...form, port: Number(form.port), poll_interval_seconds: Number(form.poll_interval_seconds) });
      toast.success("Device registered");
      setShowForm(false);
      setForm({ name: "", serial_number: "", device_model: "", integration_mode: "push", host: "", port: 4370, api_path: "", poll_interval_seconds: 300, notes: "" });
      setSecretModal({ name: data.name, push_secret: data.push_secret });
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const runSync = async (deviceId) => {
    setSyncingId(deviceId);
    try {
      const { data } = await api.post("/biometric/sync", { device_id: deviceId });
      const r = data.results[0];
      if (r?.skipped) toast.info(`${r.device_name}: ${r.skipped}`);
      else toast.success(`Synced ${r.device_name}: ${r.new} new, ${r.duplicate} duplicate punches`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSyncingId(null);
    }
  };

  const rotateSecret = async (deviceId, name) => {
    try {
      const { data } = await api.post(`/biometric/devices/${deviceId}/rotate-secret`);
      setSecretModal({ name, push_secret: data.push_secret });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const removeDevice = async (deviceId) => {
    if (!window.confirm("Delete this device? Mapped employees and raw logs are kept for audit.")) return;
    try {
      await api.delete(`/biometric/devices/${deviceId}`);
      toast.success("Device removed");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <PrimaryButton icon={Plus} type="button" onClick={() => setShowForm(true)} testid="add-device">Register Device</PrimaryButton>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : devices.length === 0 ? (
        <EmptyState message="No biometric devices registered yet" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {devices.map((d) => (
            <Card key={d.id}>
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-semibold text-foreground flex items-center gap-2">
                    <Fingerprint className="w-4 h-4 text-primary" /> {d.name}
                  </div>
                  <div className="text-xs text-muted-foreground">{d.device_model || "Unknown model"} {d.serial_number ? `· ${d.serial_number}` : ""}</div>
                </div>
                <Badge tone={d.is_active ? "success" : "neutral"}>{d.is_active ? "Active" : "Inactive"}</Badge>
              </div>
              <div className="text-sm text-muted-foreground space-y-1 mb-3">
                <div>Mode: <span className="text-foreground uppercase">{d.integration_mode}</span></div>
                {d.integration_mode === "poll" && <div>Endpoint: {d.host}:{d.port}{d.api_path}</div>}
                <div>Last sync: {d.last_sync_at ? new Date(d.last_sync_at).toLocaleString() : "never"} {d.last_sync_status && <Badge tone={syncStatusTone(d.last_sync_status)}>{d.last_sync_status}</Badge>}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                {d.integration_mode === "poll" && (
                  <SecondaryButton icon={RefreshCw} loading={syncingId === d.id} onClick={() => runSync(d.id)} testid={`sync-device-${d.id}`}>Sync Now</SecondaryButton>
                )}
                <SecondaryButton icon={KeyRound} onClick={() => rotateSecret(d.id, d.name)}>Rotate Secret</SecondaryButton>
                <SecondaryButton icon={Trash2} danger onClick={() => removeDevice(d.id)}>Delete</SecondaryButton>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Register Biometric Device" size="lg"
        footer={<><SecondaryButton onClick={() => setShowForm(false)}>Cancel</SecondaryButton><PrimaryButton loading={saving} onClick={save}>Register</PrimaryButton></>}>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Device Name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Main Gate Terminal" /></Field>
          <Field label="Model"><Input value={form.device_model} onChange={(e) => setForm({ ...form, device_model: e.target.value })} placeholder="eSSL X990" /></Field>
          <Field label="Serial Number"><Input value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} /></Field>
          <Field label="Integration Mode" required>
            <Select value={form.integration_mode} onChange={(e) => setForm({ ...form, integration_mode: e.target.value })}>
              <option value="push">Push (device sends punches to us)</option>
              <option value="poll">Poll (we fetch punches from device)</option>
            </Select>
          </Field>
          {form.integration_mode === "poll" && (
            <>
              <Field label="Host / IP" required><Input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="192.168.1.50" /></Field>
              <Field label="Port"><Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} /></Field>
              <Field label="API Path" hint="Vendor-specific endpoint path"><Input value={form.api_path} onChange={(e) => setForm({ ...form, api_path: e.target.value })} placeholder="/iclock/getrequest" /></Field>
              <Field label="Poll Interval (seconds)"><Input type="number" value={form.poll_interval_seconds} onChange={(e) => setForm({ ...form, poll_interval_seconds: e.target.value })} /></Field>
            </>
          )}
          <div className="md:col-span-2"><Field label="Notes"><Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field></div>
        </div>
      </Modal>

      <Modal open={!!secretModal} onClose={() => setSecretModal(null)} title="Device Push Secret"
        footer={<PrimaryButton onClick={() => setSecretModal(null)}>Done</PrimaryButton>}>
        <p className="text-sm text-muted-foreground mb-3">
          Configure <strong>{secretModal?.name}</strong> (or its ADMS/cloud gateway) to sign its push requests with this secret.
          It is shown only once — rotate it if lost.
        </p>
        <div className="bg-muted p-3 font-mono text-sm break-all" style={{ borderRadius: "var(--radius-md)" }}>{secretModal?.push_secret}</div>
      </Modal>
    </div>
  );
}

// ════════════════════════════════════════════ Employee Mapping ════════════════════════════════════════════
function MappingTab() {
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [mappings, setMappings] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ employee_id: "", device_enrollment_id: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/biometric/devices").then((r) => {
      setDevices(r.data);
      if (r.data.length && !deviceId) setDeviceId(r.data[0].id);
    }).catch(() => {});
    api.get("/hr/employees", { params: { status: "active" } }).then((r) => setEmployees(r.data)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/biometric/devices/${deviceId}/mappings`);
      setMappings(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => { load(); }, [load]);

  const addMapping = async () => {
    if (!form.employee_id || !form.device_enrollment_id) return toast.error("Employee and enrollment id are required");
    setSaving(true);
    try {
      await api.post("/biometric/mappings", { device_id: deviceId, ...form });
      toast.success("Mapping added");
      setForm({ employee_id: "", device_enrollment_id: "" });
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const removeMapping = async (id) => {
    try {
      await api.delete(`/biometric/mappings/${id}`);
      toast.success("Mapping removed");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="grid md:grid-cols-4 gap-3 items-end">
          <Field label="Device">
            <Select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </Field>
          <Field label="Employee">
            <Select value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}>
              <option value="">— Select —</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name} ({e.employee_code})</option>)}
            </Select>
          </Field>
          <Field label="Device Enrollment ID" hint="The device's own numeric user id for this person">
            <Input value={form.device_enrollment_id} onChange={(e) => setForm({ ...form, device_enrollment_id: e.target.value })} placeholder="e.g. 101" />
          </Field>
          <PrimaryButton icon={Plus} loading={saving} onClick={addMapping} type="button">Add Mapping</PrimaryButton>
        </div>
      </Card>

      {loading ? (
        <div className="flex justify-center py-10"><Spinner /></div>
      ) : mappings.length === 0 ? (
        <EmptyState message="No employees mapped to this device yet" />
      ) : (
        <div className="border border-border overflow-x-auto" style={{ borderRadius: "var(--radius-lg)" }}>
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Enrollment ID</th>
                <th className="px-3 py-2.5">Employee</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <tr key={m.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono">{m.device_enrollment_id}</td>
                  <td className="px-3 py-2">{m.employee_name}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => removeMapping(m.id)} className="text-muted-foreground hover:text-[var(--danger)]"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════ Raw Logs ════════════════════════════════════════════
function RawLogsTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState(new Date().toISOString().slice(0, 10));
  const [dateTo, setDateTo] = useState(new Date().toISOString().slice(0, 10));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/logs", { params: { date_from: dateFrom, date_to: dateTo } });
      setLogs(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="From"><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></Field>
          <Field label="To"><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Field>
          <SecondaryButton icon={RefreshCw} onClick={load} type="button">Refresh</SecondaryButton>
        </div>
      </Card>
      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : logs.length === 0 ? (
        <EmptyState message="No raw punches in this date range" />
      ) : (
        <div className="border border-border overflow-x-auto" style={{ borderRadius: "var(--radius-lg)" }}>
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Time</th>
                <th className="px-3 py-2.5">Employee</th>
                <th className="px-3 py-2.5">Direction</th>
                <th className="px-3 py-2.5">Source</th>
                <th className="px-3 py-2.5">Processed</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-t border-border">
                  <td className="px-3 py-2 tabular">{new Date(l.log_time).toLocaleString()}</td>
                  <td className="px-3 py-2">
                    {l.employee_name === "Unmapped"
                      ? <Badge tone="warning">Unmapped ({l.employee_code})</Badge>
                      : l.employee_name}
                  </td>
                  <td className="px-3 py-2">{l.direction || "-"}</td>
                  <td className="px-3 py-2 uppercase text-xs text-muted-foreground">{l.source}</td>
                  <td className="px-3 py-2">{l.processed ? <CheckCircle2 className="w-4 h-4 text-[var(--success)]" /> : <Clock className="w-4 h-4 text-muted-foreground" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════ Sync History ════════════════════════════════════════════
function SyncHistoryTab() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/sync/history");
      setRuns(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const retryFailed = async () => {
    setRetrying(true);
    try {
      const { data } = await api.post("/biometric/sync/retry-failed");
      toast.success(`Retried ${data.retried} run(s), ${data.given_up} gave up`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2">
        <SecondaryButton icon={AlertTriangle} loading={retrying} onClick={retryFailed} type="button">Retry Failed Syncs</SecondaryButton>
        <SecondaryButton icon={RefreshCw} onClick={load} type="button">Refresh</SecondaryButton>
      </div>
      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : runs.length === 0 ? (
        <EmptyState message="No sync runs yet" />
      ) : (
        <div className="border border-border overflow-x-auto" style={{ borderRadius: "var(--radius-lg)" }}>
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Started</th>
                <th className="px-3 py-2.5">Device</th>
                <th className="px-3 py-2.5">Trigger</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Fetched</th>
                <th className="px-3 py-2.5">New</th>
                <th className="px-3 py-2.5">Duplicate</th>
                <th className="px-3 py-2.5">Attempt</th>
                <th className="px-3 py-2.5">Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="px-3 py-2 tabular">{new Date(r.started_at).toLocaleString()}</td>
                  <td className="px-3 py-2">{r.device_name}</td>
                  <td className="px-3 py-2 uppercase text-xs text-muted-foreground">{r.trigger}</td>
                  <td className="px-3 py-2"><Badge tone={syncStatusTone(r.status)}>{r.status}</Badge></td>
                  <td className="px-3 py-2 tabular">{r.punches_fetched}</td>
                  <td className="px-3 py-2 tabular">{r.punches_new}</td>
                  <td className="px-3 py-2 tabular">{r.punches_duplicate}</td>
                  <td className="px-3 py-2 tabular">{r.attempt}</td>
                  <td className="px-3 py-2 text-xs text-[var(--danger)] max-w-xs truncate">{r.error_message || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════ Rules ════════════════════════════════════════════
function RulesTab() {
  const [rules, setRules] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    shift_id: "", late_grace_minutes: 10, early_leave_grace_minutes: 10,
    half_day_threshold_hours: 4, full_day_threshold_hours: 8,
    overtime_after_hours: 9, missing_punch_action: "flag",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/rules");
      setRules(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    api.get("/hr/shifts").then((r) => setShifts(r.data)).catch(() => setShifts([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/biometric/rules", { ...form, shift_id: form.shift_id || null });
      toast.success("Rule saved");
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const removeRule = async (id) => {
    if (!window.confirm("Delete this rule? Attendance derivation falls back to the tenant-wide default (or built-in defaults if none exists).")) return;
    try {
      await api.delete(`/biometric/rules/${id}`);
      toast.success("Rule deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <PrimaryButton icon={Plus} type="button" onClick={() => setShowForm(true)}>Add Rule</PrimaryButton>
      </div>
      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : rules.length === 0 ? (
        <EmptyState message="No custom rules — using built-in defaults (10 min grace, 8h full day, OT after 9h)" />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {rules.map((r) => (
            <Card key={r.id}>
              <div className="flex items-start justify-between mb-2">
                <div className="font-semibold text-foreground">{r.shift_id ? `Shift-specific rule` : "Tenant-wide default"}</div>
                <button onClick={() => removeRule(r.id)} className="text-muted-foreground hover:text-[var(--danger)]"><Trash2 className="w-4 h-4" /></button>
              </div>
              <div className="text-sm text-muted-foreground space-y-1">
                <div>Late grace: {r.late_grace_minutes} min · Early leave grace: {r.early_leave_grace_minutes} min</div>
                <div>Half day &lt; {r.half_day_threshold_hours}h · Full day ≥ {r.full_day_threshold_hours}h</div>
                <div>Overtime after {r.overtime_after_hours}h</div>
                <div>Missing punch: <Badge tone={r.missing_punch_action === "absent" ? "danger" : "neutral"}>{r.missing_punch_action}</Badge></div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Attendance Rule" size="lg"
        footer={<><SecondaryButton onClick={() => setShowForm(false)}>Cancel</SecondaryButton><PrimaryButton loading={saving} onClick={save}>Save</PrimaryButton></>}>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Shift" hint="Leave blank for the tenant-wide default rule">
            <Select value={form.shift_id} onChange={(e) => setForm({ ...form, shift_id: e.target.value })}>
              <option value="">— Tenant-wide default —</option>
              {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Missing Punch Action">
            <Select value={form.missing_punch_action} onChange={(e) => setForm({ ...form, missing_punch_action: e.target.value })}>
              <option value="flag">Flag (mark present, flag for review)</option>
              <option value="absent">Mark Absent</option>
              <option value="ignore">Ignore</option>
            </Select>
          </Field>
          <Field label="Late Grace (minutes)"><Input type="number" value={form.late_grace_minutes} onChange={(e) => setForm({ ...form, late_grace_minutes: Number(e.target.value) })} /></Field>
          <Field label="Early Leave Grace (minutes)"><Input type="number" value={form.early_leave_grace_minutes} onChange={(e) => setForm({ ...form, early_leave_grace_minutes: Number(e.target.value) })} /></Field>
          <Field label="Half Day Threshold (hours)"><Input type="number" step="0.5" value={form.half_day_threshold_hours} onChange={(e) => setForm({ ...form, half_day_threshold_hours: Number(e.target.value) })} /></Field>
          <Field label="Full Day Threshold (hours)"><Input type="number" step="0.5" value={form.full_day_threshold_hours} onChange={(e) => setForm({ ...form, full_day_threshold_hours: Number(e.target.value) })} /></Field>
          <Field label="Overtime After (hours)"><Input type="number" step="0.5" value={form.overtime_after_hours} onChange={(e) => setForm({ ...form, overtime_after_hours: Number(e.target.value) })} /></Field>
        </div>
      </Modal>
    </div>
  );
}

// ════════════════════════════════════════════ Corrections ════════════════════════════════════════════
function CorrectionsTab() {
  const [corrections, setCorrections] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [decidingId, setDecidingId] = useState(null);
  const [rejectModal, setRejectModal] = useState(null); // { id }
  const [rejectReason, setRejectReason] = useState("");
  const [form, setForm] = useState({ employee_id: "", attendance_date: "", requested_check_in: "", requested_check_out: "", requested_status: "", reason: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/biometric/corrections", { params: statusFilter ? { status: statusFilter } : {} });
      setCorrections(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/hr/employees", { params: { status: "active" } }).then((r) => setEmployees(r.data)).catch(() => {});
  }, []);

  const submit = async () => {
    if (!form.employee_id || !form.attendance_date) return toast.error("Employee and date are required");
    if (!form.requested_check_in && !form.requested_check_out && !form.requested_status) {
      return toast.error("Provide a requested check-in/out time or a status");
    }
    if (!form.reason) return toast.error("A reason is required");
    setSaving(true);
    try {
      await api.post("/biometric/corrections", {
        ...form,
        requested_check_in: form.requested_check_in || null,
        requested_check_out: form.requested_check_out || null,
        requested_status: form.requested_status || null,
      });
      toast.success("Correction submitted for approval");
      setShowForm(false);
      setForm({ employee_id: "", attendance_date: "", requested_check_in: "", requested_check_out: "", requested_status: "", reason: "" });
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const approve = async (id) => {
    setDecidingId(id);
    try {
      await api.post(`/biometric/corrections/${id}/decide`, { status: "APPROVED" });
      toast.success("Correction approved — attendance recomputed");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setDecidingId(null);
    }
  };

  const reject = async () => {
    setDecidingId(rejectModal.id);
    try {
      await api.post(`/biometric/corrections/${rejectModal.id}/decide`, { status: "REJECTED", rejection_reason: rejectReason });
      toast.success("Correction rejected");
      setRejectModal(null);
      setRejectReason("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setDecidingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-44">
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="">All</option>
        </Select>
        <PrimaryButton icon={ClipboardEdit} type="button" onClick={() => setShowForm(true)}>Request Correction</PrimaryButton>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : corrections.length === 0 ? (
        <EmptyState message="No correction requests" />
      ) : (
        <div className="border border-border overflow-x-auto" style={{ borderRadius: "var(--radius-lg)" }}>
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Employee</th>
                <th className="px-3 py-2.5">Requested</th>
                <th className="px-3 py-2.5">Reason</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {corrections.map((c) => (
                <tr key={c.id} className="border-t border-border">
                  <td className="px-3 py-2 tabular">{c.attendance_date}</td>
                  <td className="px-3 py-2">{c.employee_name}</td>
                  <td className="px-3 py-2">
                    {c.requested_status
                      ? <Badge tone="neutral">{c.requested_status}</Badge>
                      : `${c.requested_check_in || "—"} → ${c.requested_check_out || "—"}`}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground max-w-xs truncate">{c.reason}</td>
                  <td className="px-3 py-2"><Badge tone={c.status === "APPROVED" ? "success" : c.status === "REJECTED" ? "danger" : "warning"}>{c.status}</Badge></td>
                  <td className="px-3 py-2 text-right">
                    {c.status === "PENDING" && (
                      <div className="flex justify-end gap-1">
                        <button onClick={() => approve(c.id)} disabled={decidingId === c.id} className="text-[var(--success)] hover:opacity-70 disabled:opacity-40" title="Approve"><Check className="w-4 h-4" /></button>
                        <button onClick={() => setRejectModal({ id: c.id })} disabled={decidingId === c.id} className="text-[var(--danger)] hover:opacity-70 disabled:opacity-40" title="Reject"><X className="w-4 h-4" /></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Request Attendance Correction" size="lg"
        footer={<><SecondaryButton onClick={() => setShowForm(false)}>Cancel</SecondaryButton><PrimaryButton loading={saving} onClick={submit}>Submit</PrimaryButton></>}>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Employee" required>
            <Select value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}>
              <option value="">— Select —</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name} ({e.employee_code})</option>)}
            </Select>
          </Field>
          <Field label="Date" required><Input type="date" value={form.attendance_date} onChange={(e) => setForm({ ...form, attendance_date: e.target.value })} /></Field>
          <Field label="Requested Check-in" hint="Leave blank if only setting a status"><Input type="time" value={form.requested_check_in} onChange={(e) => setForm({ ...form, requested_check_in: e.target.value })} /></Field>
          <Field label="Requested Check-out"><Input type="time" value={form.requested_check_out} onChange={(e) => setForm({ ...form, requested_check_out: e.target.value })} /></Field>
          <Field label="Requested Status (optional)" hint="Use instead of times, e.g. device was down all day">
            <Select value={form.requested_status} onChange={(e) => setForm({ ...form, requested_status: e.target.value })}>
              <option value="">— None —</option>
              <option value="PRESENT">PRESENT</option>
              <option value="HALF_DAY">HALF_DAY</option>
              <option value="LEAVE">LEAVE</option>
            </Select>
          </Field>
          <div className="md:col-span-2"><Field label="Reason" required><Input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Device missed my punch, I was on-site all day" /></Field></div>
        </div>
      </Modal>

      <Modal open={!!rejectModal} onClose={() => setRejectModal(null)} title="Reject Correction"
        footer={<><SecondaryButton onClick={() => setRejectModal(null)}>Cancel</SecondaryButton><PrimaryButton loading={decidingId === rejectModal?.id} onClick={reject}>Reject</PrimaryButton></>}>
        <Field label="Rejection Reason"><Input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} /></Field>
      </Modal>
    </div>
  );
}

// ════════════════════════════════════════════ Page ════════════════════════════════════════════
export default function BiometricAttendance() {
  const [activeTab, setActiveTab] = useState(0);
  const [period, setPeriod] = useState(() => {
    const now = new Date();
    return `${String(now.getMonth() + 1).padStart(2, "0")}${now.getFullYear()}`;
  });
  const [aggregating, setAggregating] = useState(false);

  const runAggregate = async () => {
    setAggregating(true);
    try {
      const { data } = await api.post("/biometric/payroll/aggregate", { period });
      toast.success(`Payroll paid_days updated for ${data.employees_processed} employee(s)`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setAggregating(false);
    }
  };

  const tabs = [
    <DashboardTab key="dashboard" />,
    <DevicesTab key="devices" />,
    <MappingTab key="mapping" />,
    <RawLogsTab key="logs" />,
    <SyncHistoryTab key="history" />,
    <RulesTab key="rules" />,
    <CorrectionsTab key="corrections" />,
  ];

  return (
    <div data-testid="biometric-attendance-page">
      <PageHeader
        eyebrow="HRM"
        title="Biometric Attendance Integration"
        description="Register eSSL devices, map employees, sync punches, and derive daily attendance + payroll paid days."
        actions={
          <div className="flex items-center gap-2">
            <Input value={period} onChange={(e) => setPeriod(e.target.value)} className="w-28" placeholder="MMYYYY" data-testid="aggregate-period" />
            <PrimaryButton icon={ListTree} loading={aggregating} onClick={runAggregate} testid="run-payroll-aggregate">
              Run Payroll Aggregate
            </PrimaryButton>
          </div>
        }
      />

      <div className="flex gap-2 mb-6 border-b border-border overflow-x-auto">
        {TABS.map((tab, i) => (
          <button
            key={tab}
            onClick={() => setActiveTab(i)}
            data-testid={`biometric-tab-${i}`}
            className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px ${
              activeTab === i ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {tabs[activeTab]}
    </div>
  );
}
