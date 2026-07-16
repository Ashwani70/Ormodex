import { useState, useEffect } from "react";
import { Printer, X } from "lucide-react";
import api from "@/lib/api";
import { useImageBlob } from "@/components/ImageUploader";

export default function PrintDoc({ docType, doc, docNumber, onClose }) {
  const [company, setCompany] = useState(null);
  // Authenticated blob-fetch — a raw <img src="{API}/files/..."> never sends
  // the SameSite=Lax access_token cookie cross-origin in dev, so the logo
  // would 401 and fail to render here even though it saved correctly.
  const logoSrc = useImageBlob(company?.logo_url);

  useEffect(() => {
    api.get("/company/active")
      .then((res) => setCompany(res.data))
      .catch((err) => console.error("Failed to fetch active company", err));
  }, []);
  if (!doc) return null;

  const subtotal = doc.subtotal || 0;
  const gst = doc.gst_amount || 0;
  const total = doc.total || 0;
  const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-start justify-center overflow-y-auto p-4 print:p-0 print:bg-white">
      <div className="industrial-corner relative w-full max-w-4xl bg-zinc-950 border border-zinc-800 print:border-0 print:bg-white">
        <div className="hazard-stripe h-1.5 w-full no-print" />
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4 no-print">
          <h3 className="font-display font-bold text-white text-lg">
            Preview · {docType}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black font-mono uppercase text-xs tracking-wider px-3 py-2"
            >
              <Printer className="w-4 h-4" /> Print
            </button>
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center border border-zinc-800 text-zinc-400 hover:text-yellow-400 hover:border-yellow-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="print-area p-8 bg-white text-black">
          <div className="flex justify-between items-start border-b-4 border-black pb-4 mb-6">
            <div className="flex items-start gap-4">
              {logoSrc && (
                <img
                  src={logoSrc}
                  alt="Company Logo"
                  className="h-16 w-auto max-w-[12rem] object-contain"
                />
              )}
              <div>
                <div className="text-3xl font-black tracking-tight">{company?.name || "GRAVITYONE ERP"}</div>
                <div className="text-xs text-zinc-600 mt-2">
                  {company?.address || "Pune, Maharashtra"} · GSTIN: {company?.gstin || "27AABCG1234F1Z5"}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="bg-yellow-400 px-4 py-2 inline-block">
                <div className="text-[10px] uppercase tracking-widest font-bold">
                  {docType}
                </div>
                <div className="font-mono font-bold text-lg">
                  {docNumber}
                </div>
              </div>
              <div className="text-xs text-zinc-600 mt-2">
                Date: {new Date(doc.created_at || Date.now()).toLocaleDateString()}
              </div>
              {doc.valid_until && (
                <div className="text-xs text-zinc-600">
                  Valid Until: {doc.valid_until}
                </div>
              )}
            </div>
          </div>

          <div className="mb-6">
            <div className="text-[10px] uppercase tracking-widest font-bold text-zinc-700 mb-1">
              Bill To
            </div>
            <div className="text-lg font-semibold">
              {doc.customer_name || "—"}
            </div>
          </div>

          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-black text-white">
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest">#</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest">Description</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest">SKU</th>
                <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest">Qty</th>
                <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest">Rate</th>
                <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest">GST</th>
                <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest">Amount</th>
              </tr>
            </thead>
            <tbody>
              {doc.items?.map((it, i) => {
                const line = Number(it.quantity || 0) * Number(it.unit_price || 0);
                return (
                  <tr key={i} className="border-b border-zinc-300">
                    <td className="px-3 py-2">{i + 1}</td>
                    <td className="px-3 py-2 font-semibold">{it.product_name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{it.sku}</td>
                    <td className="px-3 py-2 text-right tabular">{it.quantity}</td>
                    <td className="px-3 py-2 text-right tabular">₹{inr(it.unit_price)}</td>
                    <td className="px-3 py-2 text-right tabular">{it.gst_rate || 0}%</td>
                    <td className="px-3 py-2 text-right tabular font-semibold">₹{inr(line)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={6} className="px-3 py-2 text-right uppercase text-xs tracking-widest font-bold">
                  Subtotal
                </td>
                <td className="px-3 py-2 text-right tabular">₹{inr(subtotal)}</td>
              </tr>
              <tr>
                <td colSpan={6} className="px-3 py-2 text-right uppercase text-xs tracking-widest font-bold">
                  GST
                </td>
                <td className="px-3 py-2 text-right tabular">₹{inr(gst)}</td>
              </tr>
              <tr className="bg-yellow-400">
                <td colSpan={6} className="px-3 py-3 text-right uppercase text-xs tracking-widest font-black">
                  Total
                </td>
                <td className="px-3 py-3 text-right tabular font-black text-lg">
                  ₹{inr(total)}
                </td>
              </tr>
            </tfoot>
          </table>

          {doc.notes && (
            <div className="mt-6 border-t border-zinc-300 pt-4">
              <div className="text-[10px] uppercase tracking-widest font-bold text-zinc-700 mb-1">
                Notes
              </div>
              <div className="text-sm">{doc.notes}</div>
            </div>
          )}

          <div className="mt-12 grid grid-cols-2 gap-8 text-xs text-zinc-700">
            <div>
              <div className="border-t border-black pt-2 uppercase tracking-widest font-bold text-[10px]">
                Customer Signature
              </div>
            </div>
            <div className="text-right">
              <div className="border-t border-black pt-2 uppercase tracking-widest font-bold text-[10px]">
                For {company?.name || "Ormodex ERP"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
