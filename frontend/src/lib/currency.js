import { Field, Input } from "@/components/ui-kit";
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
          <Input
            type="number"
            step="0.0001"
            data-testid="form-exchange-rate"
            value={form.exchange_rate || 1}
            onChange={(e) =>
              setForm({ ...form, exchange_rate: Number(e.target.value) })
            }
          />
        </Field>
      )}
    </>
  );
}

export async function downloadPdf(endpoint, filename) {
  const resp = await api.get(endpoint, { responseType: "blob" });
  const blob = new Blob([resp.data], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function fmtMoney(amount, currency = "INR") {
  const sym = CURRENCY_SYMBOLS[currency] ?? "";
  return `${sym}${Number(amount || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
