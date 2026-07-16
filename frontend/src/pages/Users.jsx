import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, Pencil, Trash2, ShieldCheck, User, Lock, Unlock, KeyRound,
  History, Monitor, MoreVertical,
} from "lucide-react";

const ROLES = [
  ["employee", "Employee"],
  ["viewer", "Viewer"],
  ["store", "Store"],
  ["production", "Production"],
  ["sales", "Sales"],
  ["purchase", "Purchase"],
  ["hr", "HR"],
  ["accountant", "Accountant"],
  ["manager", "Manager"],
  ["admin", "Admin"],
  ["super_admin", "Super Admin"],
];

const blank = {
  name: "",
  email: "",
  phone: "",
  role: "employee",
  password: "",
  module_permissions: [],
};

// Fixed-position dropdown item: consistent spacing/hover for every row.
function MenuItem({ onClick, icon: Icon, danger, children, testid }) {
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className={`w-full flex items-center gap-2 px-3 py-2.5 text-left transition-colors ${
        danger
          ? "text-red-400 hover:bg-red-950/40 hover:text-red-300"
          : "text-zinc-300 hover:bg-zinc-900 hover:text-white"
      }`}
    >
      <Icon className="w-3.5 h-3.5 flex-shrink-0" /> {children}
    </button>
  );
}

function ActionsMenu({ user, onLock, onUnlock, onForceChange, onResetPassword, onLoginHistory, onDevices, onDelete, onEdit }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const MENU_WIDTH = 224; // w-56
  const MENU_HEIGHT_ESTIMATE = 340; // ~7 items, used to decide open-up vs open-down

  // Compute the menu's fixed viewport position from the trigger button's own
  // rect — this is what lets the dropdown render in a portal (escaping the
  // table's overflow-x-auto clipping) while still visually anchoring to the
  // button. Flips left when there's not enough room on the right, and flips
  // up when there's not enough room below, always clamped inside the viewport.
  const placeMenu = () => {
    const el = btnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const spaceRight = window.innerWidth - r.right;
    const openLeft = spaceRight < MENU_WIDTH && r.right >= MENU_WIDTH;
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < MENU_HEIGHT_ESTIMATE && r.top > spaceBelow;

    let left = openLeft ? r.right - MENU_WIDTH : r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - MENU_WIDTH - 8));

    setCoords({
      left,
      top: openUp ? undefined : r.bottom + 4,
      bottom: openUp ? window.innerHeight - r.top + 4 : undefined,
    });
  };

  useLayoutEffect(() => {
    if (!open) return;
    placeMenu();
    const onScrollOrResize = () => placeMenu();
    // Capture phase so scrolling the table body (or any ancestor) also
    // re-tracks the button instead of leaving the menu stranded.
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  // Close on Escape, and on outside click (checking both the trigger button
  // and the portaled menu itself, since the menu no longer lives inside this
  // component's own DOM subtree).
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => { if (e.key === "Escape") setOpen(false); };
    const onClickOutside = (e) => {
      if (btnRef.current?.contains(e.target)) return;
      if (menuRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [open]);

  const act = (fn) => () => { setOpen(false); fn(); };

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        className="w-7 h-7 rounded-md border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center transition-colors"
        data-testid={`user-actions-${user.id}`}
      >
        <MoreVertical className="w-3.5 h-3.5" />
      </button>
      {open && coords && createPortal(
        <div
          ref={menuRef}
          className="fixed w-56 rounded-lg border border-zinc-800 bg-zinc-950 shadow-2xl text-sm overflow-hidden py-1"
          style={{ left: coords.left, top: coords.top, bottom: coords.bottom, zIndex: 9999 }}
        >
          <MenuItem icon={Pencil} onClick={act(onEdit)}>Edit</MenuItem>
          {user.is_locked ? (
            <MenuItem icon={Unlock} onClick={act(onUnlock)}>Unlock account</MenuItem>
          ) : (
            <MenuItem icon={Lock} onClick={act(onLock)}>Lock account</MenuItem>
          )}
          <MenuItem icon={KeyRound} onClick={act(onForceChange)}>Force password change</MenuItem>
          <MenuItem icon={KeyRound} onClick={act(onResetPassword)}>Reset password</MenuItem>
          <MenuItem icon={History} onClick={act(onLoginHistory)}>Login history</MenuItem>
          <MenuItem icon={Monitor} onClick={act(onDevices)}>Devices</MenuItem>
          <div className="border-t border-zinc-900 my-1" />
          <MenuItem icon={Trash2} danger onClick={act(onDelete)}>Delete</MenuItem>
        </div>,
        document.body
      )}
    </>
  );
}

export default function Users() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [modules, setModules] = useState([]); // [{key, label}]

  // Reset-password modal state (shows the generated temp password once).
  const [resetTarget, setResetTarget] = useState(null);
  const [tempPassword, setTempPassword] = useState(null);

  // Login-history / devices viewer modals.
  const [historyTarget, setHistoryTarget] = useState(null);
  const [historyItems, setHistoryItems] = useState(null);
  const [devicesTarget, setDevicesTarget] = useState(null);
  const [devicesItems, setDevicesItems] = useState(null);

  const load = async () => {
    const r = await api.get("/users");
    setItems(r.data);
  };
  useEffect(() => {
    load();
    // Module catalog drives the access checkboxes; admin-only endpoint.
    api.get("/users/modules").then((r) => setModules(r.data)).catch(() => setModules([]));
  }, []);

  // Admins implicitly have every module, so hide the per-module toggles for them.
  const showModules = form.role !== "admin" && form.role !== "super_admin";

  const toggleModule = (key) => {
    setForm((f) => {
      const has = (f.module_permissions || []).includes(key);
      return {
        ...f,
        module_permissions: has
          ? f.module_permissions.filter((k) => k !== key)
          : [...(f.module_permissions || []), key],
      };
    });
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editingId) {
        const payload = { ...form };
        if (!payload.password) delete payload.password;
        delete payload.email;
        await api.put(`/users/${editingId}`, payload);
      } else {
        await api.post("/users", form);
      }
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api.delete(`/users/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onLock = async (item) => {
    try {
      await api.post(`/users/${item.id}/lock`);
      toast.success(`${item.name} locked`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onUnlock = async (item) => {
    try {
      await api.post(`/users/${item.id}/unlock`);
      toast.success(`${item.name} unlocked`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onForceChange = async (item) => {
    try {
      await api.post(`/users/${item.id}/force-password-change`);
      toast.success(`${item.name} must change password on next login`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onResetPassword = async (item) => {
    try {
      const { data } = await api.post(`/users/${item.id}/reset-password`, {});
      setResetTarget(item);
      setTempPassword(data.temp_password);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onLoginHistory = async (item) => {
    setHistoryTarget(item);
    setHistoryItems(null);
    try {
      const { data } = await api.get(`/users/${item.id}/login-history`);
      setHistoryItems(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setHistoryItems([]);
    }
  };

  const onDevices = async (item) => {
    setDevicesTarget(item);
    setDevicesItems(null);
    try {
      const { data } = await api.get(`/users/${item.id}/devices`);
      setDevicesItems(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setDevicesItems([]);
    }
  };

  const openNew = () => {
    setForm(blank);
    setEditingId(null);
    setOpen(true);
  };

  // Enter-as-Tab across the create/edit modal form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels, first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
  });

  return (
    <div data-testid="users-page">
      <PageHeader
        eyebrow="System"
        title="Users & Roles"
        description="Manage operators, supervisors and admins."
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-user"
            onClick={openNew}
          >
            New user
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No users yet" />
      ) : (
        <div className="border border-zinc-800 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900">
              <tr className="text-left label-overline">
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Email</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">Role</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Created</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr
                  key={u.id}
                  className="border-t border-zinc-900 hover:bg-zinc-900/60"
                >
                  <td className="px-3 py-2.5 text-white">
                    <div className="flex items-center gap-2">
                      {u.role === "admin" || u.role === "super_admin" ? (
                        <ShieldCheck className="w-3.5 h-3.5 text-yellow-400" />
                      ) : (
                        <User className="w-3.5 h-3.5 text-zinc-500" />
                      )}
                      {u.name}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">{u.email}</td>
                  <td className="px-3 py-2.5 text-zinc-400">{u.phone}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`text-xs font-mono uppercase tracking-wider px-2 py-0.5 border ${
                        u.role === "admin" || u.role === "super_admin"
                          ? "border-yellow-400 text-yellow-400"
                          : "border-zinc-700 text-zinc-400"
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {u.is_locked ? (
                      <span className="inline-flex items-center gap-1 text-xs text-red-400"><Lock className="w-3 h-3" /> Locked</span>
                    ) : u.is_active === false ? (
                      <span className="text-xs text-zinc-500">Disabled</span>
                    ) : (
                      <span className="text-xs text-green-500">Active</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <ActionsMenu
                      user={u}
                      onEdit={() => { setForm({ ...blank, ...u, password: "" }); setEditingId(u.id); setOpen(true); }}
                      onLock={() => onLock(u)}
                      onUnlock={() => onUnlock(u)}
                      onForceChange={() => onForceChange(u)}
                      onResetPassword={() => onResetPassword(u)}
                      onLoginHistory={() => onLoginHistory(u)}
                      onDevices={() => onDevices(u)}
                      onDelete={() => onDelete(u)}
                    />
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
        title={editingId ? "Edit User" : "New User"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-user">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Name" required>
            <Input
              required
              data-testid="form-user-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Email" required>
            <Input
              type="email"
              required
              disabled={!!editingId}
              data-testid="form-user-email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Phone">
            <Input
              value={form.phone || ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
            >
              {ROLES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </Field>
          {editingId && (
            <Field label="Account status">
              <select
                value={form.is_active === false ? "disabled" : "active"}
                onChange={(e) => setForm({ ...form, is_active: e.target.value !== "disabled" })}
                className="w-full bg-black border border-zinc-700 text-white text-sm px-3 py-2 focus:border-yellow-400"
              >
                <option value="active">Active</option>
                <option value="disabled">Disabled</option>
              </select>
            </Field>
          )}
          <div className="md:col-span-2">
            <Field label={editingId ? "New password (leave blank to keep)" : "Password"} required={!editingId}>
              <Input
                type="password"
                required={!editingId}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </Field>
          </div>

          {showModules && (
            <div className="md:col-span-2">
              <Field label="Module access">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 border border-zinc-800 p-3 max-h-56 overflow-y-auto">
                  {modules.map((m) => (
                    <label
                      key={m.key}
                      className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer hover:text-white"
                    >
                      <input
                        type="checkbox"
                        className="accent-yellow-400"
                        checked={(form.module_permissions || []).includes(m.key)}
                        onChange={() => toggleModule(m.key)}
                      />
                      {m.label}
                    </label>
                  ))}
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  Admins have access to all modules automatically.
                </p>
              </Field>
            </div>
          )}
        </form>
      </Modal>

      {/* Admin-generated temp password, shown once. */}
      <Modal
        open={!!resetTarget}
        onClose={() => { setResetTarget(null); setTempPassword(null); }}
        title={`Password reset — ${resetTarget?.name || ""}`}
        footer={
          <PrimaryButton onClick={() => { setResetTarget(null); setTempPassword(null); }}>
            Done
          </PrimaryButton>
        }
      >
        <p className="text-sm text-zinc-400 mb-3">
          Hand this temporary password to <b>{resetTarget?.name}</b> out-of-band. They
          will be required to change it on their next sign-in. It will not be shown again.
        </p>
        <div className="font-mono text-lg text-yellow-400 bg-zinc-950 border border-zinc-800 px-4 py-3 select-all">
          {tempPassword}
        </div>
      </Modal>

      {/* Login history viewer */}
      <Modal
        open={!!historyTarget}
        onClose={() => { setHistoryTarget(null); setHistoryItems(null); }}
        title={`Login history — ${historyTarget?.name || ""}`}
        size="lg"
      >
        {historyItems === null ? null : historyItems.length === 0 ? (
          <EmptyState message="No login history." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 pr-4">When</th>
                <th className="py-2 pr-4">IP</th>
                <th className="py-2 pr-4">Device</th>
                <th className="py-2">Result</th>
              </tr>
            </thead>
            <tbody>
              {historyItems.map((h) => (
                <tr key={h.id} className="border-b border-zinc-900 last:border-0">
                  <td className="py-2 pr-4 whitespace-nowrap text-zinc-300">{new Date(h.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-zinc-400">{h.ip || "—"}</td>
                  <td className="py-2 pr-4 text-zinc-400">{h.device_name || "—"}</td>
                  <td className="py-2">
                    {h.success ? (
                      <span className="text-green-500 text-xs">Success</span>
                    ) : (
                      <span className="text-red-400 text-xs">{h.failure_reason || "Failed"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Modal>

      {/* Devices viewer */}
      <Modal
        open={!!devicesTarget}
        onClose={() => { setDevicesTarget(null); setDevicesItems(null); }}
        title={`Devices — ${devicesTarget?.name || ""}`}
      >
        {devicesItems === null ? null : devicesItems.length === 0 ? (
          <EmptyState message="No active devices." />
        ) : (
          <div className="space-y-2">
            {devicesItems.map((d) => (
              <div key={d.id} className="flex items-center gap-3 border border-zinc-800 p-3">
                <Monitor className="w-4 h-4 text-zinc-500 shrink-0" />
                <div className="min-w-0">
                  <div className="text-sm text-white truncate">{d.device_name || "Unknown device"}</div>
                  <div className="text-xs text-zinc-500 truncate">
                    {d.ip} · signed in {d.login_at ? new Date(d.login_at).toLocaleString() : "—"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}
