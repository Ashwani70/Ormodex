import { useEffect, useRef, useState } from "react";
import useDebounce from "@/hooks/useDebounce";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import QRCode from "react-qr-code";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
  NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import {
  Plus,
  Pencil,
  Trash2,
  QrCode,
  Search,
  IndianRupee,
} from "lucide-react";

const blank = {
  employee_code: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  gender: "",
  dob: "",
  joining_date: "",
  branch_id: "",
  department_id: "",
  designation: "",
  shift_id: "",
  salary_type: "MONTHLY",
  basic_salary: "",
  bank_name: "",
  account_number: "",
  ifsc_code: "",
  pan_number: "",
  address: "",
  status: "active",
  create_login: false,
  login_password: "",
};

const blankSS = {
  basic: "",
  hra: "",
  da: "",
  conveyance: "",
  medical: "",
  special_allowance: "",
  other_allowance: "",
  pf_percent: 12,
  enable_pf: true,
  esi_employee_percent: 0.75,
  esi_employer_percent: 3.25,
  enable_esi: true,
  professional_tax: 200,
  tds_percent: "",
  overtime_rate_multiplier: 2,
};

export default function Employees() {
  const [items, setItems] = useState([]);
  const [branches, setBranches] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [searchParams] = useSearchParams();
  // Seed from ?q= so the global search can deep-link to a specific employee.
  const [q, setQ] = useState(searchParams.get("q") || "");
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(blank);
  const [qrEmp, setQrEmp] = useState(null);
  const [ssEmp, setSsEmp] = useState(null);
  const [ss, setSs] = useState(blankSS);

  const debouncedQ = useDebounce(q, 300);
  const load = async () => {
    const r = await api.get("/hr/employees", { params: { q: debouncedQ } });
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, [debouncedQ]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get("/hr/branches").then((r) => setBranches(r.data));
    api.get("/hr/departments").then((r) => setDepartments(r.data));
    api.get("/hr/shifts").then((r) => setShifts(r.data));
  }, []);

  const startNew = () => {
    setForm(blank);
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (it) => {
    setForm({ ...blank, ...it, create_login: false, login_password: "" });
    setEditingId(it.id);
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      basic_salary: Number(form.basic_salary || 0),
      branch_id: form.branch_id || null,
      department_id: form.department_id || null,
      shift_id: form.shift_id || null,
    };
    try {
      if (editingId) await api.put(`/hr/employees/${editingId}`, payload);
      else await api.post("/hr/employees", payload);
      toast.success("Employee saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  // Enter-as-Tab across the New/Edit Employee form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels. Primary create action on this page → owns Ctrl+N.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!open) startNew(); },
  });

  const onDelete = async (it) => {
    if (!window.confirm(`Delete ${it.first_name} ${it.last_name}?`)) return;
    try {
      await api.delete(`/hr/employees/${it.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const openSs = async (emp) => {
    const r = await api.get(`/hr/employees/${emp.id}/salary-structure`);
    setSs({ ...blankSS, ...r.data });
    setSsEmp(emp);
  };
  const saveSs = async () => {
    try {
      await api.put(`/hr/employees/${ssEmp.id}/salary-structure`, {
        ...ss,
        employee_id: ssEmp.id,
        basic: Number(ss.basic),
      });
      toast.success("Salary structure saved");
      setSsEmp(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const backend = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
  const qrUrl = qrEmp ? `${backend.replace(/\/$/, "")}/qr/${qrEmp.qr_token}` : "";

  return (
    <div data-testid="employees-page">
      <PageHeader
        eyebrow="HRM"
        title="Employees"
        description="Master roster — workforce, payroll setup and self-service access."
        actions={
          <PrimaryButton testid="new-employee" icon={Plus} onClick={startNew}>
            New employee
          </PrimaryButton>
        }
      />

      <div className="mb-4 max-w-md relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
        <Input
          data-testid="search-employees"
          placeholder="Search code, name, phone, email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="pl-9"
        />
      </div>

      {items.length === 0 ? (
        <EmptyState
          message="No employees yet"
          action={
            <PrimaryButton onClick={startNew} icon={Plus}>
              Add your first employee
            </PrimaryButton>
          }
        />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Code</th>
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Designation</th>
                <th className="px-3 py-2.5">Department</th>
                <th className="px-3 py-2.5">Branch</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5 text-right">Basic</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} data-testid={`employee-row-${p.employee_code}`} className="border-t border-zinc-900 hover:bg-zinc-900/60">
                  <td className="px-3 py-2 font-mono text-yellow-400 text-xs">{p.employee_code}</td>
                  <td className="px-3 py-2 text-white">{p.first_name} {p.last_name}</td>
                  <td className="px-3 py-2 text-zinc-300">{p.designation || "-"}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.department_name}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.branch_name}</td>
                  <td className="px-3 py-2 text-zinc-400 text-xs">{p.phone}</td>
                  <td className="px-3 py-2 text-right tabular text-zinc-300">
                    ₹{Number(p.basic_salary || 0).toLocaleString("en-IN")}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 border ${
                      p.status === "active" ? "border-green-700 text-green-400" : "border-zinc-700 text-zinc-500"
                    }`}>
                      {p.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => openSs(p)} title="Salary structure" className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center">
                        <IndianRupee className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => setQrEmp(p)} title="QR badge" className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center">
                        <QrCode className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => startEdit(p)} className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => onDelete(p)} className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center">
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

      {/* New/Edit employee modal */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Employee" : "New Employee"}
        size="xl"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-employee">Save</PrimaryButton>
          </>
        }
      >
        <div ref={formRef} className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Employee Code" required>
            <Input required data-testid="emp-code" value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />
          </Field>
          <Field label="First Name" required>
            <Input required data-testid="emp-fname" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </Field>
          <Field label="Last Name" required>
            <Input required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </Field>
          <Field label="Email">
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="Phone">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label="Gender">
            <select value={form.gender || ""} onChange={(e) => setForm({ ...form, gender: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">—</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Date of Birth"><Input type="date" value={form.dob || ""} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></Field>
          <Field label="Joining Date"><Input type="date" value={form.joining_date || ""} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} /></Field>
          <Field label="Status">
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              {["active", "inactive", "terminated"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Branch">
            <select value={form.branch_id || ""} onChange={(e) => setForm({ ...form, branch_id: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">—</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </Field>
          <Field label="Department">
            <select value={form.department_id || ""} onChange={(e) => setForm({ ...form, department_id: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">—</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="Designation">
            <Input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
          </Field>
          <Field label="Shift">
            <select value={form.shift_id || ""} onChange={(e) => setForm({ ...form, shift_id: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              <option value="">—</option>
              {shifts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Salary Type">
            <select value={form.salary_type} onChange={(e) => setForm({ ...form, salary_type: e.target.value })} className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400">
              {["MONTHLY", "DAILY", "HOURLY"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Basic Salary (₹)">
            <NumericInput value={form.basic_salary} onChange={(v) => setForm({ ...form, basic_salary: v })} placeholder="0.00" align="left" />
          </Field>
          <Field label="Bank Name"><Input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} /></Field>
          <Field label="Account Number"><Input value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} /></Field>
          <Field label="IFSC Code"><Input value={form.ifsc_code} onChange={(e) => setForm({ ...form, ifsc_code: e.target.value })} /></Field>
          <Field label="PAN Number"><Input value={form.pan_number} onChange={(e) => setForm({ ...form, pan_number: e.target.value })} /></Field>
          <div className="md:col-span-3">
            <Field label="Address">
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
          </div>

          {!editingId && (
            <div className="md:col-span-3 border border-zinc-800 p-3 bg-zinc-900/40">
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="emp-create-login"
                  checked={form.create_login}
                  onChange={(e) => setForm({ ...form, create_login: e.target.checked })}
                  className="accent-yellow-400"
                />
                Create self-service login (employee can log in via their email)
              </label>
              {form.create_login && (
                <div className="mt-2">
                  <Field label="Initial Password" required>
                    <Input
                      type="text"
                      data-testid="emp-login-pwd"
                      value={form.login_password}
                      onChange={(e) => setForm({ ...form, login_password: e.target.value })}
                      placeholder="Share with employee privately"
                    />
                  </Field>
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>

      {/* QR badge modal */}
      <Modal
        open={!!qrEmp}
        onClose={() => setQrEmp(null)}
        title={`QR Badge · ${qrEmp?.employee_code || ""}`}
        size="sm"
        footer={<SecondaryButton onClick={() => setQrEmp(null)}>Close</SecondaryButton>}
      >
        {qrEmp && (
          <div className="flex flex-col items-center gap-3">
            <div className="bg-white p-4">
              <QRCode value={qrUrl} size={200} />
            </div>
            <div className="text-center">
              <div className="font-display font-bold text-white">{qrEmp.first_name} {qrEmp.last_name}</div>
              <div className="font-mono text-xs text-yellow-400">{qrEmp.employee_code}</div>
            </div>
            <div className="text-[11px] font-mono text-zinc-500 text-center break-all">
              {qrUrl}
            </div>
            <PrimaryButton onClick={() => window.print()}>Print badge</PrimaryButton>
          </div>
        )}
      </Modal>

      {/* Salary structure modal */}
      <Modal
        open={!!ssEmp}
        onClose={() => setSsEmp(null)}
        title={`Salary Structure · ${ssEmp?.first_name || ""} ${ssEmp?.last_name || ""}`}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setSsEmp(null)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={saveSs} testid="save-ss">Save Structure</PrimaryButton>
          </>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Basic (₹)"><NumericInput value={ss.basic} onChange={(v) => setSs({ ...ss, basic: v })} placeholder="0.00" align="left" /></Field>
          <Field label="HRA"><NumericInput value={ss.hra} onChange={(v) => setSs({ ...ss, hra: v })} placeholder="0.00" align="left" /></Field>
          <Field label="DA"><NumericInput value={ss.da} onChange={(v) => setSs({ ...ss, da: v })} placeholder="0.00" align="left" /></Field>
          <Field label="Conveyance"><NumericInput value={ss.conveyance} onChange={(v) => setSs({ ...ss, conveyance: v })} placeholder="0.00" align="left" /></Field>
          <Field label="Medical"><NumericInput value={ss.medical} onChange={(v) => setSs({ ...ss, medical: v })} placeholder="0.00" align="left" /></Field>
          <Field label="Special Allowance"><NumericInput value={ss.special_allowance} onChange={(v) => setSs({ ...ss, special_allowance: v })} placeholder="0.00" align="left" /></Field>
          <Field label="Other Allowance"><NumericInput value={ss.other_allowance} onChange={(v) => setSs({ ...ss, other_allowance: v })} placeholder="0.00" align="left" /></Field>
          <Field label="PF % of basic"><NumericInput value={ss.pf_percent} onChange={(v) => setSs({ ...ss, pf_percent: v })} placeholder="12" align="left" /></Field>
          <Field label="ESI Employee %"><NumericInput value={ss.esi_employee_percent} onChange={(v) => setSs({ ...ss, esi_employee_percent: v })} placeholder="0.75" align="left" /></Field>
          <Field label="ESI Employer %"><NumericInput value={ss.esi_employer_percent} onChange={(v) => setSs({ ...ss, esi_employer_percent: v })} placeholder="3.25" align="left" /></Field>
          <Field label="Professional Tax (flat ₹)"><NumericInput value={ss.professional_tax} onChange={(v) => setSs({ ...ss, professional_tax: v })} placeholder="200" align="left" /></Field>
          <Field label="TDS %"><NumericInput value={ss.tds_percent} onChange={(v) => setSs({ ...ss, tds_percent: v })} placeholder="0" align="left" /></Field>
          <Field label="Overtime Multiplier (×)"><NumericInput value={ss.overtime_rate_multiplier} onChange={(v) => setSs({ ...ss, overtime_rate_multiplier: v })} placeholder="2" align="left" /></Field>
          <div className="md:col-span-2 grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer border border-zinc-800 px-3 py-2">
              <input type="checkbox" className="accent-yellow-400" checked={ss.enable_pf} onChange={(e) => setSs({ ...ss, enable_pf: e.target.checked })} />
              Enable PF deduction
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer border border-zinc-800 px-3 py-2">
              <input type="checkbox" className="accent-yellow-400" checked={ss.enable_esi} onChange={(e) => setSs({ ...ss, enable_esi: e.target.checked })} />
              Enable ESI (auto-applies when gross ≤ ₹21,000)
            </label>
          </div>
        </div>
      </Modal>
    </div>
  );
}
