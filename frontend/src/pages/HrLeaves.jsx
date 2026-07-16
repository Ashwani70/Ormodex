import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, CheckCircle2, XCircle, Trash2 } from "lucide-react";

export default function Leaves() {
  const [items, setItems] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    employee_id: "",
    leave_type_id: "",
    start_date: "",
    end_date: "",
    reason: "",
  });
  const [rejectItem, setRejectItem] = useState(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = async () => {
    const r = await api.get("/hr/leaves", { params: filter ? { status: filter } : {} });
    setItems(r.data);
  };

  const sel = useBulkSelect(items);
  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/hr/leaves/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} leave record${ok === 1 ? "" : "s"}`);
  };
  useEffect(() => {
    load();
  }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get("/hr/employees").then((r) => setEmployees(r.data));
    api.get("/hr/leave-types").then((r) => setLeaveTypes(r.data));
  }, []);

  const apply = async () => {
    try {
      await api.post("/hr/leaves", form);
      toast.success("Leave application submitted");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  // Enter-as-Tab across the Record Leave form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels. Primary create action on this page → owns Ctrl+N.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: apply,
    onCancel: () => setOpen(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!open) setOpen(true); },
  });

  const approve = async (it) => {
    if (!window.confirm("Approve this leave?")) return;
    try {
      await api.post(`/hr/leaves/${it.id}/decide`, { status: "APPROVED" });
      toast.success("Approved");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const reject = async () => {
    try {
      await api.post(`/hr/leaves/${rejectItem.id}/decide`, {
        status: "REJECTED",
        rejection_reason: rejectReason,
      });
      toast.success("Rejected");
      setRejectItem(null);
      setRejectReason("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (it) => {
    if (!window.confirm("Delete this leave record?")) return;
    try {
      await api.delete(`/hr/leaves/${it.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="leaves-page-hr">
      <PageHeader
        eyebrow="HRM"
        title="Leave Management"
        description="Apply, approve and track employee leaves."
        actions={
          <PrimaryButton testid="hr-new-leave" icon={Plus} onClick={() => setOpen(true)}>
            Record leave
          </PrimaryButton>
        }
      />

      <div className="mb-4 flex gap-2">
        {["", "PENDING", "APPROVED", "REJECTED"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setFilter(s)}
            data-testid={`leave-filter-${s || "all"}`}
            className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider border ${
              filter === s
                ? "bg-yellow-400 text-black border-yellow-400"
                : "border-zinc-700 text-zinc-400 hover:border-yellow-400"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <EmptyState message="No leave records" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all leave records"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">Employee</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">From</th>
                <th className="px-3 py-2.5">To</th>
                <th className="px-3 py-2.5 text-right">Days</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Reason</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((l) => (
                <tr key={l.id} data-testid={`leave-row-${l.id}`} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${sel.isSelected(l.id) ? "bg-zinc-900/40" : ""}`}>
                  <td className="px-3 py-2">
                    <SelectCheckbox
                      label={`Select leave ${l.id}`}
                      checked={sel.isSelected(l.id)}
                      onChange={() => sel.toggle(l.id)}
                    />
                  </td>
                  <td className="px-3 py-2 text-white">{l.employee_name}</td>
                  <td className="px-3 py-2 text-zinc-300">{l.leave_type_name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-zinc-400">{l.start_date}</td>
                  <td className="px-3 py-2 font-mono text-xs text-zinc-400">{l.end_date}</td>
                  <td className="px-3 py-2 text-right tabular text-yellow-400">{l.total_days}</td>
                  <td className="px-3 py-2"><StatusBadge status={l.status} /></td>
                  <td className="px-3 py-2 text-zinc-400 text-xs">{l.reason || "-"}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1">
                      {l.status === "PENDING" && (
                        <>
                          <button onClick={() => approve(l)} title="Approve" data-testid={`approve-${l.id}`} className="w-7 h-7 border border-zinc-800 hover:border-green-500 hover:text-green-400 text-zinc-400 flex items-center justify-center">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => { setRejectItem(l); setRejectReason(""); }} title="Reject" data-testid={`reject-${l.id}`} className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center">
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        </>
                      )}
                      <button onClick={() => onDelete(l)} className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Record Leave"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={apply} testid="apply-leave">Submit</PrimaryButton>
          </>
        }
      >
        <div ref={formRef} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Employee" required>
            <select value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">— select —</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name} ({e.employee_code})</option>)}
            </select>
          </Field>
          <Field label="Leave Type" required>
            <select value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">—</option>
              {leaveTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="From" required><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="To" required><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <div className="md:col-span-2">
            <Field label="Reason">
              <textarea rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400" />
            </Field>
          </div>
        </div>
      </Modal>

      <Modal
        open={!!rejectItem}
        onClose={() => setRejectItem(null)}
        title="Reject Leave"
        size="sm"
        footer={
          <>
            <SecondaryButton onClick={() => setRejectItem(null)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={reject}>Reject</PrimaryButton>
          </>
        }
      >
        <Field label="Reason for rejection">
          <textarea rows={3} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
            className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400" />
        </Field>
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="leave record"
      />
    </div>
  );
}
