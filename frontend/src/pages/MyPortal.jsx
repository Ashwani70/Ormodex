import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  StatTile,
  SectionTitle,
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { downloadPdf } from "@/lib/currency";
import { Clock, LogIn, LogOut, Plus, Download } from "lucide-react";

export default function MyPortal() {
  const [emp, setEmp] = useState(null);
  const [attendance, setAttendance] = useState([]);
  const [leaves, setLeaves] = useState([]);
  const [balance, setBalance] = useState([]);
  const [payslips, setPayslips] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
  const [todayRec, setTodayRec] = useState(null);

  const loadAll = async () => {
    try {
      const r = await api.get("/hr/me/employee");
      setEmp(r.data);
    } catch {
      setEmp(false);
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const from = today.slice(0, 7) + "-01";
    const [att, lv, bal, ps, lt] = await Promise.all([
      api.get("/hr/me/attendance", { params: { date_from: from, date_to: today } }),
      api.get("/hr/me/leaves"),
      api.get("/hr/me/leave-balance"),
      api.get("/hr/me/payslips"),
      api.get("/hr/leave-types"),
    ]);
    setAttendance(att.data);
    setLeaves(lv.data);
    setBalance(bal.data);
    setPayslips(ps.data);
    setLeaveTypes(lt.data);
    setTodayRec(att.data.find((a) => a.date === today) || null);
  };
  useEffect(() => {
    loadAll();
  }, []);

  if (emp === false) {
    return (
      <div className="border border-zinc-800 p-12 text-center">
        <div className="font-display text-xl text-white mb-2">Self-service is not enabled</div>
        <div className="text-sm text-zinc-400">
          Ask your HR admin to link your account to an employee record.
        </div>
      </div>
    );
  }

  const checkIn = async () => {
    try {
      const { data } = await api.post("/hr/me/attendance/check-in", {});
      setTodayRec(data);
      toast.success(`Checked in at ${data.check_in}`);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };
  const checkOut = async () => {
    try {
      const { data } = await api.post("/hr/me/attendance/check-out", {});
      setTodayRec(data);
      toast.success(`Checked out at ${data.check_out}`);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const applyLeave = async () => {
    try {
      await api.post("/hr/me/leaves", form);
      toast.success("Leave application submitted");
      setOpen(false);
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const presentDays = attendance.filter((a) => ["PRESENT", "LATE", "HALF_DAY"].includes(a.status)).length;

  return (
    <div data-testid="my-portal-page">
      <PageHeader
        eyebrow={`Welcome back, ${emp?.first_name || ""}`}
        title="My Portal"
        description="Your attendance, leaves, payslips and profile — all in one place."
        actions={
          <>
            {!todayRec?.check_in && (
              <PrimaryButton icon={LogIn} onClick={checkIn} testid="my-check-in">Check in</PrimaryButton>
            )}
            {todayRec?.check_in && !todayRec?.check_out && (
              <SecondaryButton icon={LogOut} onClick={checkOut} testid="my-check-out">Check out</SecondaryButton>
            )}
            {todayRec?.check_in && todayRec?.check_out && (
              <span className="inline-flex items-center gap-2 border border-green-700 text-green-400 px-3 py-2 text-xs font-mono uppercase">
                <Clock className="w-3.5 h-3.5" />
                {todayRec.check_in} → {todayRec.check_out}
              </span>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatTile label="Present this month" value={presentDays} sub={`${attendance.length} records`} accent />
        <StatTile label="Pending leaves" value={leaves.filter((l) => l.status === "PENDING").length} />
        <StatTile label="Approved leaves" value={leaves.filter((l) => l.status === "APPROVED").length} />
        <StatTile label="Payslips available" value={payslips.length} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-zinc-800 border border-zinc-800">
        <div className="bg-zinc-950 p-5">
          <SectionTitle action={<PrimaryButton icon={Plus} onClick={() => setOpen(true)} testid="apply-my-leave">Apply leave</PrimaryButton>}>
            My Leaves
          </SectionTitle>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {leaves.length === 0 ? (
              <div className="text-xs text-zinc-500 font-mono uppercase">No leave applications</div>
            ) : leaves.map((l) => (
              <div key={l.id} className="border border-zinc-800 p-3 bg-zinc-900/40">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-white">{l.start_date} → {l.end_date} <span className="text-zinc-500 text-xs ml-1">({l.total_days}d)</span></span>
                  <StatusBadge status={l.status} />
                </div>
                <div className="text-xs text-zinc-400 mt-1">{l.reason || "—"}</div>
              </div>
            ))}
          </div>

          <SectionTitle>Leave Balance</SectionTitle>
          <div className="grid grid-cols-2 gap-2">
            {balance.map((b) => (
              <div key={b.leave_type_id} className="border border-zinc-800 p-3 bg-zinc-900/40">
                <div className="label-overline">{b.leave_type_name}</div>
                <div className="font-display font-bold text-yellow-400 text-xl tabular mt-1">{b.available}</div>
                <div className="font-mono text-[10px] text-zinc-500">used {b.used} / {b.annual_quota}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-zinc-950 p-5">
          <SectionTitle>Recent Attendance</SectionTitle>
          <div className="space-y-px bg-zinc-800 max-h-64 overflow-y-auto">
            {attendance.length === 0 ? (
              <div className="bg-zinc-950 p-3 text-xs text-zinc-500 font-mono uppercase">No records yet</div>
            ) : attendance.slice(0, 12).map((a) => (
              <div key={a.id} className="bg-zinc-950 p-3 flex items-center justify-between">
                <div className="font-mono text-xs text-zinc-400">{a.date}</div>
                <div className="text-xs text-zinc-500">{a.check_in || "-"} → {a.check_out || "-"}</div>
                <StatusBadge status={a.status} />
              </div>
            ))}
          </div>

          <SectionTitle>My Payslips</SectionTitle>
          <div className="space-y-2">
            {payslips.length === 0 ? (
              <div className="text-xs text-zinc-500 font-mono uppercase">No finalised payslips yet</div>
            ) : payslips.map((p) => (
              <div key={p.id} className="flex items-center justify-between border border-zinc-800 bg-zinc-900/40 p-3">
                <div>
                  <div className="font-display text-white">{p.month}</div>
                  <div className="font-mono text-xs text-zinc-500">Net: ₹{Number(p.net_salary).toLocaleString("en-IN")}</div>
                </div>
                <button
                  onClick={() => downloadPdf(`/hr/me/payslips/${p.id}/pdf`, `payslip_${p.month}.pdf`)}
                  data-testid={`my-payslip-${p.month}`}
                  className="inline-flex items-center gap-1 border border-zinc-700 hover:border-yellow-400 hover:text-yellow-400 text-zinc-300 text-xs font-mono uppercase px-3 py-1.5"
                >
                  <Download className="w-3.5 h-3.5" /> PDF
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Apply for leave"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={applyLeave} testid="submit-my-leave">Submit</PrimaryButton>
          </>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Leave Type" required>
            <select required value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">— select —</option>
              {leaveTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="From" required><Input type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="To" required><Input type="date" required value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <div className="md:col-span-2">
            <Field label="Reason">
              <textarea rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400" />
            </Field>
          </div>
        </div>
      </Modal>
    </div>
  );
}
