import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { BACKEND_URL } from "@/lib/api";
import { Hammer, Download, ReceiptText } from "lucide-react";

export default function PayslipShare() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [company, setCompany] = useState(null);

  useEffect(() => {
    api.get(`/hr/public/payslip/${token}/info`)
      .then((r) => setInfo(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Not found"));

    api.get("/company/active")
      .then((res) => setCompany(res.data))
      .catch((err) => console.error("Failed to fetch active company", err));
  }, [token]);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-6">
          <div className={`w-10 h-10 flex items-center justify-center overflow-hidden ${company?.logo_url ? "bg-white" : "bg-yellow-400"}`}>
            {company?.logo_url ? (
              <img
                src={`${BACKEND_URL}/api/public/logo`}
                alt="Logo"
                className="w-full h-full object-contain p-0.5"
              />
            ) : (
              <Hammer className="w-5 h-5 text-black" strokeWidth={2.5} />
            )}
          </div>
          <div>
            <div className="font-display font-black text-white text-lg">
              {company?.name || "Ormodex"}
            </div>
            <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">
              {company?.name ? "ERP Platform" : "Engineering Works"}
            </div>
          </div>
        </div>

        <div className="industrial-corner border border-zinc-800 bg-zinc-900 p-6">
          <div className="hazard-stripe h-1.5 mb-5 -mx-6 -mt-6" />
          <div className="label-overline mb-1 flex items-center gap-1.5">
            <ReceiptText className="w-3.5 h-3.5 text-yellow-400" />
            Salary Slip
          </div>
          {error ? (
            <div className="text-red-400 font-mono uppercase">{error}</div>
          ) : info ? (
            <>
              <h1 className="font-display font-black text-2xl text-white">{info.employee_name}</h1>
              <div className="font-mono text-yellow-400 text-sm mt-1">{info.employee_code} · {info.month}</div>
              <div className="mt-6 bg-yellow-400 text-black px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-wider">Net Salary</div>
                <div className="font-display font-black text-2xl tabular">₹{Number(info.net_salary || 0).toLocaleString("en-IN")}</div>
              </div>
              <div className="mt-2 text-xs text-zinc-400">{info.amount_in_words}</div>
              <a
                href={`${BACKEND_URL}/api/hr/public/payslip/${token}/pdf`}
                target="_blank"
                rel="noreferrer"
                data-testid="public-payslip-pdf"
                className="mt-6 w-full inline-flex items-center justify-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black font-mono font-semibold uppercase tracking-wider text-xs py-3"
              >
                <Download className="w-4 h-4" /> Download payslip PDF
              </a>
            </>
          ) : (
            <div className="text-zinc-500 font-mono uppercase">Loading…</div>
          )}
        </div>
      </div>
    </div>
  );
}
