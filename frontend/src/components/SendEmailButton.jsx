import { useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import Modal from "@/components/Modal";
import { PrimaryButton, SecondaryButton, Input, Field } from "@/components/ui-kit";
import { Mail, Send } from "lucide-react";

/**
 * Send-via-email button.
 * Renders an icon-button (matches the row action style). On click, opens a modal
 * with To/Subject/Message and posts to /api/email/{docType}/{docId}.
 */
export default function SendEmailButton({
  docType, // "quotation" | "sales_order" | "invoice" | "dispatch" | "proforma"
  docId,
  docNumber,
  defaultRecipient,
  defaultRecipientName,
  testid,
  onSent,
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [to, setTo] = useState(defaultRecipient || "");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");

  const friendlyMap = {
    quotation: "Quotation",
    sales_order: "Sales Order",
    invoice: "GST Invoice",
    dispatch: "Dispatch Challan",
    proforma: "Proforma Invoice",
  };

  const startSend = () => {
    setTo(defaultRecipient || "");
    setSubject(
      `${friendlyMap[docType] || "Document"} ${docNumber} — GravityOne ERP`
    );
    setMessage("");
    setOpen(true);
  };

  const send = async () => {
    if (!to) return toast.error("Recipient email is required");
    setBusy(true);
    try {
      const { data } = await api.post(`/email/${docType}/${docId}`, {
        to,
        subject: subject || undefined,
        message: message || undefined,
      });
      toast.success(`Sent to ${data.sent_to}`);
      setOpen(false);
      onSent?.(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={startSend}
        title="Send via email"
        data-testid={testid || `email-${docId}`}
        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
      >
        <Mail className="w-3.5 h-3.5" />
      </button>

      <Modal
        open={open}
        onClose={() => !busy && setOpen(false)}
        title={`Send · ${friendlyMap[docType] || "Document"} ${docNumber}`}
        size="md"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={send} disabled={busy} icon={Send} testid="confirm-send">
              {busy ? "Sending…" : "Send email"}
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-3">
          <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider border border-zinc-800 bg-zinc-900/40 px-3 py-2">
            <span className="text-yellow-400">PDF auto-attached:</span> {docNumber}.pdf
            {defaultRecipientName && (
              <span className="block text-zinc-500 normal-case tracking-normal mt-1">
                Default recipient: {defaultRecipientName}
              </span>
            )}
          </div>
          <Field label="To" required>
            <Input
              type="email"
              required
              data-testid="email-to"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="customer@example.com"
            />
          </Field>
          <Field label="Subject">
            <Input
              data-testid="email-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </Field>
          <Field label="Optional message (added to the email body)">
            <textarea
              rows={4}
              data-testid="email-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="A short note to the recipient (optional)"
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
            />
          </Field>
        </div>
      </Modal>
    </>
  );
}
