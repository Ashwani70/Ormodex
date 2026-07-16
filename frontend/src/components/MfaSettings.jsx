/**
 * Two-factor authentication (TOTP) management card.
 *
 * Self-contained: drop <MfaSettings /> into any settings/profile page. Handles
 * the full lifecycle — enroll (QR + secret) → verify code → show one-time
 * recovery codes → disable (password-confirmed). Talks to /auth/mfa/* and the
 * status endpoint; see backend routers/mfa.py.
 */
import { useEffect, useState } from "react";
import QRCode from "react-qr-code";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Input, Field, PrimaryButton } from "@/components/ui-kit";

export default function MfaSettings() {
  const [status, setStatus] = useState(null); // { enabled, pending }
  const [enroll, setEnroll] = useState(null); // { secret, otpauth_uri }
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadStatus = async () => {
    try {
      const { data } = await api.get("/auth/mfa/status");
      setStatus(data);
    } catch (e) {
      setStatus({ enabled: false, pending: false });
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const fail = (e) => setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);

  const startEnroll = async () => {
    setErr("");
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/enroll");
      setEnroll(data);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/verify", { code: code.trim() });
      setRecoveryCodes(data.recovery_codes);
      setEnroll(null);
      setCode("");
      await loadStatus();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const disable = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.post("/auth/mfa/disable", { password });
      setPassword("");
      setRecoveryCodes(null);
      await loadStatus();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  if (status === null) return null;

  return (
    <div className="border border-border bg-card p-6" style={{ borderRadius: "var(--radius)" }}>
      <div className="label-overline mb-1">Security</div>
      <h3 className="font-display font-black text-xl text-foreground">
        Two-Factor Authentication
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Protect your account with a time-based one-time code from an authenticator
        app (Google Authenticator, Authy, 1Password).
      </p>

      {err && (
        <div
          className="mt-4 border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
          style={{ borderRadius: "var(--radius)" }}
        >
          {err}
        </div>
      )}

      {/* One-time recovery codes, shown right after enabling */}
      {recoveryCodes && (
        <div className="mt-4 border border-yellow-400/40 bg-yellow-400/10 p-4" style={{ borderRadius: "var(--radius)" }}>
          <div className="label-overline mb-2 text-foreground">
            Save your recovery codes
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            Each code works once if you lose your authenticator. They won’t be
            shown again.
          </p>
          <div className="grid grid-cols-2 gap-1 font-mono text-sm text-foreground">
            {recoveryCodes.map((c) => (
              <div key={c}>{c}</div>
            ))}
          </div>
        </div>
      )}

      {/* Enrollment step: QR + verify */}
      {enroll && (
        <form onSubmit={verify} className="mt-4 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4 items-start">
            <div className="bg-white p-3" style={{ borderRadius: "var(--radius)" }}>
              <QRCode value={enroll.otpauth_uri} size={148} />
            </div>
            <div className="text-xs text-muted-foreground space-y-2">
              <p>Scan the QR with your authenticator app, or enter the key manually:</p>
              <code className="block font-mono text-foreground break-all bg-muted px-2 py-1" style={{ borderRadius: "var(--radius)" }}>
                {enroll.secret}
              </code>
              <p>Then enter the 6-digit code it shows to finish setup.</p>
            </div>
          </div>
          <Field label="Verification code" required>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              required
            />
          </Field>
          <div className="flex gap-2">
            <PrimaryButton type="submit" disabled={busy}>
              {busy ? "Verifying…" : "Enable 2FA"}
            </PrimaryButton>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground font-mono"
              onClick={() => { setEnroll(null); setCode(""); setErr(""); }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Idle states: enable button, or disable form */}
      {!enroll && !status.enabled && (
        <div className="mt-4">
          <PrimaryButton onClick={startEnroll} disabled={busy}>
            {busy ? "Starting…" : "Set up 2FA"}
          </PrimaryButton>
        </div>
      )}

      {!enroll && status.enabled && (
        <form onSubmit={disable} className="mt-4 space-y-3">
          <div className="inline-flex items-center gap-2 text-sm text-green-600 font-mono">
            <span className="inline-block w-2 h-2 bg-green-500" style={{ borderRadius: "50%" }} />
            2FA is enabled
          </div>
          <Field label="Confirm password to disable">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </Field>
          <button
            type="submit"
            disabled={busy}
            className="text-xs text-destructive hover:underline font-mono"
          >
            {busy ? "Disabling…" : "Disable 2FA"}
          </button>
        </form>
      )}
    </div>
  );
}
