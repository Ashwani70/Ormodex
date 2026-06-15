import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
  StatTile,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { Send, CheckCircle2, XCircle, Mail } from "lucide-react";

export default function EmailLog() {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState({ configured: false });
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [s, l] = await Promise.all([
      api.get("/email/status"),
      api.get("/email/logs"),
    ]);
    setStatus(s.data);
    setLogs(l.data);
  };
  useEffect(() => {
    load();
  }, []);

  const sendTest = async () => {
    if (!to) return toast.error("Recipient email is required");
    setBusy(true);
    try {
      await api.post("/email/test", { to });
      toast.success(`Test email sent to ${to}`);
      setOpen(false);
      setTo("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  const sent = logs.filter((l) => l.status === "sent").length;
  const failed = logs.filter((l) => l.status === "failed").length;

  return (
    <div data-testid="email-log-page">
      <PageHeader
        eyebrow="System"
        title="Email Log"
        description="Outgoing email activity. Each send is logged regardless of outcome."
        actions={
          <>
            <PrimaryButton
              icon={Send}
              testid="send-test-email"
              onClick={() => setOpen(true)}
            >
              Send test email
            </PrimaryButton>
          </>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        <StatTile
          label="Service status"
          value={status.configured ? "Configured" : "Disabled"}
          sub={status.configured ? "Resend integration active" : "RESEND_API_KEY missing"}
          accent={status.configured}
        />
        <StatTile
          label="Successful sends"
          value={sent}
          sub={`${logs.length} total attempts`}
        />
        <StatTile label="Failed sends" value={failed} sub="Check error column" />
      </div>

      {logs.length === 0 ? (
        <EmptyState message="No emails sent yet" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">When</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Document</th>
                <th className="px-3 py-2.5">To</th>
                <th className="px-3 py-2.5">Subject</th>
                <th className="px-3 py-2.5">By</th>
                <th className="px-3 py-2.5">Message ID / Error</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-t border-zinc-900 hover:bg-zinc-900/60">
                  <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                    {new Date(l.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    {l.status === "sent" ? (
                      <span className="inline-flex items-center gap-1 text-green-400 font-mono text-xs">
                        <CheckCircle2 className="w-3.5 h-3.5" /> SENT
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-400 font-mono text-xs">
                        <XCircle className="w-3.5 h-3.5" /> FAILED
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-yellow-400 text-xs">
                    {l.doc_number}
                    <span className="block text-zinc-500 text-[10px] uppercase tracking-wider">
                      {l.doc_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-white">{l.to}</td>
                  <td className="px-3 py-2 text-zinc-300 text-xs">{l.subject}</td>
                  <td className="px-3 py-2 text-zinc-400 text-xs">{l.sent_by || "—"}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-zinc-500">
                    {l.status === "sent"
                      ? l.message_id || "—"
                      : (
                        <span className="text-red-400">{l.error}</span>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={open}
        onClose={() => !busy && setOpen(false)}
        title="Send test email"
        size="sm"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={sendTest} icon={Send} disabled={busy} testid="confirm-test">
              {busy ? "Sending…" : "Send test"}
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-3">
          <div className="text-xs text-zinc-400 font-mono">
            <Mail className="inline w-3.5 h-3.5 mr-1" />
            Resend free-tier sandbox can only deliver to{" "}
            <span className="text-yellow-400">your Resend account email</span> until
            your sending domain is verified.
          </div>
          <Field label="Recipient" required>
            <Input
              type="email"
              data-testid="test-to"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="you@example.com"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
