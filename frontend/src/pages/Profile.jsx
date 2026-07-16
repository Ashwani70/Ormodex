/**
 * Self-service account & security page: profile info, password change,
 * two-factor authentication (MfaSettings), active devices/sessions, and
 * recent login history for the signed-in user.
 */
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, Card, SectionTitle, Input, Field, PrimaryButton, SecondaryButton, EmptyState } from "@/components/ui-kit";
import MfaSettings from "@/components/MfaSettings";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { Eye, EyeOff, Monitor, LogOut, CheckCircle2, XCircle, ArrowRight } from "lucide-react";

function PasswordField({ label, value, onChange, placeholder, testid }) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} required>
      <div className="relative">
        <Input
          data-testid={testid}
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className="pr-10"
          required
        />
        <button
          type="button"
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          onClick={() => setVisible((v) => !v)}
          tabIndex={-1}
        >
          {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </Field>
  );
}

function ChangePasswordCard() {
  const { changePassword } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setOk(false);
    if (next !== confirm) {
      setErr("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      setOk(true);
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  // Enter-as-Tab across the password fields; Ctrl+Enter/Ctrl+S submits, first
  // field auto-focuses on mount. Always-visible card — no modal, no cancel.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: true,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
  });

  return (
    <Card>
      <SectionTitle>Change Password</SectionTitle>
      <form ref={formRef} onSubmit={submit} className="space-y-4 max-w-md">
        <PasswordField label="Current password" testid="profile-current-password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="••••••••" />
        <PasswordField label="New password" testid="profile-new-password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="At least 12 characters" />
        <PasswordField label="Confirm new password" testid="profile-confirm-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Re-enter new password" />
        {err && (
          <div className="border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2" style={{ borderRadius: "var(--radius)" }}>
            {err}
          </div>
        )}
        {ok && (
          <div className="flex items-center gap-2 border border-green-500/20 bg-green-500/10 text-green-600 text-xs font-mono px-3 py-2" style={{ borderRadius: "var(--radius)" }}>
            <CheckCircle2 className="w-4 h-4" /> Password updated.
          </div>
        )}
        <PrimaryButton type="submit" disabled={busy} icon={ArrowRight}>
          {busy ? "Updating…" : "Update password"}
        </PrimaryButton>
      </form>
    </Card>
  );
}

function DevicesCard() {
  const { logoutAll } = useAuth();
  const [devices, setDevices] = useState(null);
  const [err, setErr] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/auth/devices");
      setDevices(data);
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const revoke = async (id) => {
    setBusyId(id);
    try {
      await api.delete(`/auth/devices/${id}`);
      await load();
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card>
      <SectionTitle
        action={
          <SecondaryButton icon={LogOut} onClick={logoutAll} testid="logout-all-btn">
            Log out all other devices
          </SecondaryButton>
        }
      >
        Active Devices &amp; Sessions
      </SectionTitle>
      {err && (
        <div className="mb-4 border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2" style={{ borderRadius: "var(--radius)" }}>
          {err}
        </div>
      )}
      {devices === null ? null : devices.length === 0 ? (
        <EmptyState message="No active devices." />
      ) : (
        <div className="space-y-2">
          {devices.map((d) => (
            <div key={d.id} className="flex items-center justify-between border border-border p-3" style={{ borderRadius: "var(--radius)" }}>
              <div className="flex items-center gap-3 min-w-0">
                <Monitor className="w-4 h-4 text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">{d.device_name || "Unknown device"}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {d.ip} · signed in {d.login_at ? new Date(d.login_at).toLocaleString() : "—"}
                  </div>
                </div>
              </div>
              <button
                type="button"
                className="text-xs text-destructive hover:underline font-mono shrink-0 ml-3"
                disabled={busyId === d.id}
                onClick={() => revoke(d.id)}
              >
                {busyId === d.id ? "Revoking…" : "Revoke"}
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function LoginHistoryCard() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/auth/login-history")
      .then((res) => setItems(res.data))
      .catch((e) => setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message));
  }, []);

  return (
    <Card>
      <SectionTitle>Recent Login History</SectionTitle>
      {err && (
        <div className="mb-4 border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2" style={{ borderRadius: "var(--radius)" }}>
          {err}
        </div>
      )}
      {items === null ? null : items.length === 0 ? (
        <EmptyState message="No login history yet." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="py-2 pr-4">When</th>
                <th className="py-2 pr-4">IP</th>
                <th className="py-2 pr-4">Device</th>
                <th className="py-2">Result</th>
              </tr>
            </thead>
            <tbody>
              {items.map((h) => (
                <tr key={h.id} className="border-b border-border/60 last:border-0">
                  <td className="py-2 pr-4 whitespace-nowrap">{new Date(h.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{h.ip || "—"}</td>
                  <td className="py-2 pr-4 truncate max-w-[220px]">{h.device_name || "—"}</td>
                  <td className="py-2">
                    {h.success ? (
                      <span className="inline-flex items-center gap-1 text-green-600 text-xs"><CheckCircle2 className="w-3.5 h-3.5" /> Success</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-destructive text-xs"><XCircle className="w-3.5 h-3.5" /> {h.failure_reason || "Failed"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function Profile() {
  const { user } = useAuth();

  return (
    <div>
      <PageHeader
        eyebrow="Account"
        title="My Profile & Security"
        description="Manage your password, two-factor authentication, active sessions and sign-in history."
      />
      <div className="space-y-6">
        <Card>
          <SectionTitle>Profile</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl text-sm">
            <div>
              <div className="label-overline text-muted-foreground mb-1">Name</div>
              <div className="text-foreground">{user?.name || "—"}</div>
            </div>
            <div>
              <div className="label-overline text-muted-foreground mb-1">Email</div>
              <div className="text-foreground">{user?.email || "—"}</div>
            </div>
            <div>
              <div className="label-overline text-muted-foreground mb-1">Role</div>
              <div className="text-foreground capitalize">{(user?.role || "—").replace(/_/g, " ")}</div>
            </div>
            <div>
              <div className="label-overline text-muted-foreground mb-1">Last login</div>
              <div className="text-foreground">{user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}</div>
            </div>
          </div>
        </Card>

        <ChangePasswordCard />
        <MfaSettings />
        <DevicesCard />
        <LoginHistoryCard />
      </div>
    </div>
  );
}
