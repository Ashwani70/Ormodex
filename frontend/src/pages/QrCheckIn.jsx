import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Hammer, LogIn, LogOut, CheckCircle2 } from "lucide-react";

export default function QrCheckIn() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  useEffect(() => {
    api.get(`/hr/qr/${token}/info`).then((r) => setInfo(r.data)).catch((e) => {
      setError(formatApiErrorDetail(e.response?.data?.detail) || "Invalid QR");
    });
  }, [token]);

  const punch = async (kind) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/hr/qr/${token}/${kind === "in" ? "check-in" : "check-out"}`);
      setLast({ kind, time: kind === "in" ? data.attendance.check_in : data.attendance.check_out });
      toast.success(`${kind === "in" ? "Checked in" : "Checked out"} at ${kind === "in" ? data.attendance.check_in : data.attendance.check_out}`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-yellow-400 flex items-center justify-center">
            <Hammer className="w-5 h-5 text-black" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-display font-black text-white text-lg">Ormodex</div>
            <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">Engineering Works</div>
          </div>
        </div>

        <div className="industrial-corner border border-zinc-800 bg-zinc-900 p-6">
          <div className="hazard-stripe h-1.5 mb-5 -mx-6 -mt-6" />
          {error ? (
            <div className="text-red-400 text-center font-mono uppercase">{error}</div>
          ) : info ? (
            <>
              <div className="label-overline mb-1">Employee</div>
              <h1 className="font-display font-black text-2xl text-white">
                {info.first_name} {info.last_name}
              </h1>
              <div className="font-mono text-yellow-400 text-sm mt-1">{info.employee_code}</div>

              {last ? (
                <div className="mt-6 border border-green-700 bg-green-950/30 p-4 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-green-400" />
                  <div className="text-sm">
                    <div className="text-green-400 font-mono uppercase tracking-wider text-xs">
                      Recorded
                    </div>
                    <div className="text-white">
                      {last.kind === "in" ? "Check-in" : "Check-out"} at <span className="font-mono text-yellow-400">{last.time}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-6 grid grid-cols-2 gap-3">
                  <button
                    onClick={() => punch("in")}
                    disabled={busy}
                    data-testid="qr-check-in-btn"
                    className="bg-yellow-400 hover:bg-yellow-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-black font-mono font-semibold uppercase tracking-wider text-xs py-4 flex flex-col items-center gap-1"
                  >
                    <LogIn className="w-5 h-5" />
                    Check in
                  </button>
                  <button
                    onClick={() => punch("out")}
                    disabled={busy}
                    data-testid="qr-check-out-btn"
                    className="border border-zinc-700 hover:border-yellow-400 hover:text-yellow-400 text-zinc-300 font-mono font-semibold uppercase tracking-wider text-xs py-4 flex flex-col items-center gap-1"
                  >
                    <LogOut className="w-5 h-5" />
                    Check out
                  </button>
                </div>
              )}

              <div className="mt-4 font-mono text-[11px] uppercase tracking-wider text-zinc-500">
                {new Date().toLocaleString()}
              </div>
            </>
          ) : (
            <div className="text-zinc-500 font-mono uppercase">Loading…</div>
          )}
        </div>
      </div>
    </div>
  );
}
