import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
} from "@/components/ui-kit";
import { CheckCircle2, Save } from "lucide-react";

const STATUS_OPTIONS = ["PRESENT", "ABSENT", "HALF_DAY", "LEAVE", "LATE"];
const STATUS_COLOR = {
  PRESENT: "border-green-700 text-green-400",
  LATE: "border-yellow-700 text-yellow-400",
  ABSENT: "border-red-700 text-red-400",
  HALF_DAY: "border-blue-700 text-blue-400",
  LEAVE: "border-purple-700 text-purple-400",
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function Attendance() {
  const [date, setDate] = useState(todayIso());
  const [employees, setEmployees] = useState([]);
  const [attendance, setAttendance] = useState({});
  const [busy, setBusy] = useState(false);

  const loadEmps = async () => {
    const r = await api.get("/hr/employees", { params: { status: "active" } });
    setEmployees(r.data);
  };
  const loadAtt = async () => {
    const r = await api.get("/hr/attendance", {
      params: { date_from: date, date_to: date },
    });
    const map = {};
    r.data.forEach((a) => {
      map[a.employee_id] = a;
    });
    setAttendance(map);
  };
  useEffect(() => {
    loadEmps();
  }, []);
  useEffect(() => {
    loadAtt();
  }, [date]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateRow = (empId, patch) => {
    setAttendance({
      ...attendance,
      [empId]: {
        ...(attendance[empId] || { status: "PRESENT", overtime_hours: 0, check_in: "", check_out: "" }),
        ...patch,
      },
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      const rows = employees
        .map((e) => attendance[e.id] && { ...attendance[e.id], employee_id: e.id })
        .filter(Boolean);
      await api.post("/hr/attendance/bulk", {
        date,
        rows: rows.map((r) => ({
          employee_id: r.employee_id,
          status: r.status,
          check_in: r.check_in || null,
          check_out: r.check_out || null,
          overtime_hours: Number(r.overtime_hours || 0),
          remarks: r.remarks || null,
        })),
      });
      toast.success("Attendance saved");
      loadAtt();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const markAllPresent = () => {
    const map = { ...attendance };
    employees.forEach((e) => {
      map[e.id] = {
        ...(map[e.id] || {}),
        status: "PRESENT",
        check_in: map[e.id]?.check_in || "09:00",
        check_out: map[e.id]?.check_out || "18:00",
      };
    });
    setAttendance(map);
  };

  const summary = useMemo(() => {
    const out = { PRESENT: 0, LATE: 0, ABSENT: 0, HALF_DAY: 0, LEAVE: 0 };
    Object.values(attendance).forEach((a) => {
      out[a.status] = (out[a.status] || 0) + 1;
    });
    return out;
  }, [attendance]);

  return (
    <div data-testid="attendance-page">
      <PageHeader
        eyebrow="HRM"
        title="Daily Attendance"
        description="Mark attendance manually, track OT hours, late punches and shift compliance."
        actions={
          <>
            <SecondaryButton testid="mark-all-present" onClick={markAllPresent}>
              Mark all present
            </SecondaryButton>
            <PrimaryButton icon={Save} onClick={save} disabled={busy} testid="save-attendance">
              {busy ? "Saving…" : "Save attendance"}
            </PrimaryButton>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="border border-zinc-800 bg-zinc-900/50 px-3 py-2 flex items-center gap-3">
          <span className="label-overline">Date</span>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-44" data-testid="att-date" />
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-mono uppercase tracking-wider">
          {STATUS_OPTIONS.map((s) => (
            <span key={s} className={`border px-2 py-1 ${STATUS_COLOR[s]}`}>
              {s}: <span className="tabular ml-1">{summary[s] || 0}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="border border-zinc-800 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900">
            <tr className="text-left label-overline">
              <th className="px-3 py-2.5">Code</th>
              <th className="px-3 py-2.5">Employee</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Check-in</th>
              <th className="px-3 py-2.5">Check-out</th>
              <th className="px-3 py-2.5">OT Hours</th>
              <th className="px-3 py-2.5">Remarks</th>
            </tr>
          </thead>
          <tbody>
            {employees.length === 0 ? (
              <tr><td colSpan={7} className="text-center text-zinc-500 py-6 font-mono text-xs uppercase">No active employees</td></tr>
            ) : employees.map((e) => {
              const a = attendance[e.id] || { status: "PRESENT", overtime_hours: 0 };
              return (
                <tr key={e.id} className="border-t border-zinc-900">
                  <td className="px-3 py-1.5 font-mono text-yellow-400 text-xs">{e.employee_code}</td>
                  <td className="px-3 py-1.5 text-white">{e.first_name} {e.last_name}</td>
                  <td className="px-3 py-1.5">
                    <select
                      value={a.status}
                      onChange={(ev) => updateRow(e.id, { status: ev.target.value })}
                      data-testid={`att-status-${e.employee_code}`}
                      className={`bg-black border text-xs font-mono uppercase px-2 py-1 focus:border-yellow-400 ${STATUS_COLOR[a.status] || "border-zinc-700"}`}
                    >
                      {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-1.5">
                    <input type="time" value={a.check_in || ""} onChange={(ev) => updateRow(e.id, { check_in: ev.target.value })}
                      className="bg-black border border-zinc-700 text-white text-sm px-2 py-1 w-28" />
                  </td>
                  <td className="px-3 py-1.5">
                    <input type="time" value={a.check_out || ""} onChange={(ev) => updateRow(e.id, { check_out: ev.target.value })}
                      className="bg-black border border-zinc-700 text-white text-sm px-2 py-1 w-28" />
                  </td>
                  <td className="px-3 py-1.5">
                    <input type="text" inputMode="decimal" step="0.25" value={a.overtime_hours || 0} onChange={(ev) => updateRow(e.id, { overtime_hours: ev.target.value })}
                      className="bg-black border border-zinc-700 text-white text-sm px-2 py-1 w-20 text-right tabular" />
                  </td>
                  <td className="px-3 py-1.5">
                    <input type="text" value={a.remarks || ""} onChange={(ev) => updateRow(e.id, { remarks: ev.target.value })}
                      placeholder="Optional" className="bg-black border border-zinc-700 text-white text-sm px-2 py-1 w-full" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {Object.values(attendance).some((a) => a) && (
        <div className="mt-4 flex items-center gap-2 text-xs font-mono text-zinc-500">
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
          Changes are not saved until you click "Save attendance"
        </div>
      )}
    </div>
  );
}
