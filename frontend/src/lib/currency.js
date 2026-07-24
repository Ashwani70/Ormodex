import { Field, NumericInput } from "@/components/ui-kit";
import api from "@/lib/api";

export const CURRENCIES = ["INR", "USD", "AED", "EUR", "GBP"];
export const CURRENCY_SYMBOLS = {
  INR: "₹",
  USD: "$",
  AED: "AED ",
  EUR: "€",
  GBP: "£",
};

export function CurrencyFields({ form, setForm }) {
  return (
    <>
      <Field label="Currency">
        <select
          value={form.currency || "INR"}
          onChange={(e) =>
            setForm({
              ...form,
              currency: e.target.value,
              exchange_rate: e.target.value === "INR" ? 1 : form.exchange_rate || 1,
            })
          }
          data-testid="form-currency"
          className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
        >
          {CURRENCIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </Field>
      {form.currency && form.currency !== "INR" && (
        <Field label={`Exchange rate (1 ${form.currency} = ? INR)`}>
          <NumericInput
            decimals={4}
            data-testid="form-exchange-rate"
            value={form.exchange_rate != null && form.exchange_rate !== 1 ? form.exchange_rate : ""}
            onChange={(v) =>
              setForm({ ...form, exchange_rate: v === "" ? 1 : parseFloat(v) })
            }
            placeholder="1.0000"
          />
        </Field>
      )}
    </>
  );
}

/**
 * Fetch a PDF from an authenticated endpoint and either download it or open it
 * in a new browser tab. Uses the shared `api` axios instance, so the
 * `gew_access_token` Bearer + cookies are attached automatically — a plain
 * window.open(url) would not carry auth for cookie-blocked clients.
 *
 * Throws on failure so callers can surface a toast.
 *
 * @param {string} endpoint  API path, e.g. "/invoices/123/pdf"
 * @param {string} filename  Suggested filename for download mode.
 * @param {{ newTab?: boolean }} [opts]  newTab: open in a new tab instead of downloading.
 */
export async function downloadPdf(endpoint, filename, opts = {}) {
  const resp = await api.get(endpoint, { responseType: "blob" });
  const blob = new Blob([resp.data], { type: "application/pdf" });

  // Desktop build: use the native Save dialog instead of the browser download
  // tray, so it feels like a real desktop app. Falls through to the normal web
  // path if the Electron bridge isn't present (plain web/PWA build).
  if (typeof window !== "undefined" && window.ormodex?.saveFile) {
    const base64 = await blobToBase64(blob);
    const { saved } = await window.ormodex.saveFile(filename, base64);
    if (saved) return;
    // User cancelled the native dialog — nothing else to do.
    if (saved === false) return;
  }

  const url = URL.createObjectURL(blob);
  if (opts.newTab) {
    window.open(url, "_blank", "noopener,noreferrer");
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  // Give the tab/download time to consume the URL before revoking it.
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/** Open a PDF in a new tab. Thin wrapper over downloadPdf for readability. */
export function openPdf(endpoint, filename = "document.pdf") {
  return downloadPdf(endpoint, filename, { newTab: true });
}

export function fmtMoney(amount, currency = "INR") {
  const sym = CURRENCY_SYMBOLS[currency] ?? "";
  return `${sym}${Number(amount || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
