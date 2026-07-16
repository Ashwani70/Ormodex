import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/**
 * Keyboard shortcuts for ERP navigation.
 *
 * Pattern: G then a letter (vim-style "go to") for page navigation.
 * Single-key shortcuts for frequent actions.
 *
 * Tally/SAP/NetSuite-style function keys and Alt-combos (always-on, app-wide;
 * suppressed only while a text field is focused — see isInputFocused()).
 * This F-key legend matches Tally's own layout exactly (F3 Company … F10
 * Other Voucher) — it superseded an earlier, non-Tally F4/F8/F9/F10 mapping
 * (Product Master/Sales Orders/Purchase Orders/Stock Log), which moved to
 * Alt-combos below so those destinations stay one keystroke away without
 * colliding with the real Tally keys:
 *
 * F3  → Company Master   (/admin/company-master)
 * F4  → Contra Voucher   (/vouchers, pre-set to CONTRA)
 * F5  → Payment Voucher  (/vouchers, pre-set to PAYMENT)
 * F6  → Receipt Voucher  (/vouchers, pre-set to RECEIPT)
 * F7  → Journal Voucher  (/vouchers, pre-set to JOURNAL)
 * F8  → Sales Voucher    (/sales-orders)
 * F9  → Purchase Voucher (/purchase-orders-v2)
 * F10 → Other Voucher    (/vouchers — the full voucher-type picker)
 * (F11 → fullscreen, F12 → Settings: already handled in Layout.jsx)
 *
 * Alt+C → Create Customer (Customers, opens the new-record form)
 * Alt+P → Create Product  (Products, opens the new-record form)
 * Alt+I → Product Master  (Products list — displaced from F4 by Contra)
 * Alt+L → Stock Log       (displaced from F10 by Other Voucher)
 * Alt+W → Select Warehouse (Warehouses list — a dedicated cross-page picker
 *          is a larger follow-up; this session wires navigation only)
 *
 * These are intentionally GLOBAL fallbacks: a page that registers its own
 * F8/F9/Ctrl+N/etc via useModuleShortcuts (capture phase + stopPropagation)
 * takes precedence over the behavior below for that key on that page.
 *
 * G + D  → Dashboard
 * G + I  → Invoices
 * G + Q  → Quotations
 * G + S  → Sales Orders
 * G + P  → Products
 * G + O  → Purchase Orders
 * G + B  → Purchase Bills
 * G + R  → Purchase Returns
 * G + N  → GRNs
 * G + C  → Customers
 * G + V  → Vendors
 * G + A  → Accounting
 * G + T  → GST Accounting
 * G + H  → HR Dashboard
 * G + Y  → Payroll
 * G + E  → Expenses
 * G + L  → Ledger
 * G + M  → Manufacturing
 * G + J  → Job Work
 * G + W  → Inventory Reports
 * G + X  → MIS Reports
 * G + Z  → AI Assistant
 * G + K  → POS (counter)
 *
 * Single-key (no modifier, no text input focused):
 * ?      → Show/hide shortcuts help
 */
export const SHORTCUTS = [
  { keys: ["G", "D"], label: "Dashboard",           path: "/" },
  { keys: ["G", "I"], label: "GST Invoices",         path: "/invoices" },
  { keys: ["G", "Q"], label: "Quotations",           path: "/quotations" },
  { keys: ["G", "S"], label: "Sales Orders",         path: "/sales-orders" },
  { keys: ["G", "C"], label: "Customers",            path: "/customers" },
  { keys: ["G", "P"], label: "Products",             path: "/products" },
  { keys: ["G", "O"], label: "Purchase Orders",      path: "/purchase-orders-v2" },
  { keys: ["G", "B"], label: "Purchase Bills",       path: "/purchase-bills" },
  { keys: ["G", "R"], label: "Purchase Returns",     path: "/purchase-returns" },
  { keys: ["G", "N"], label: "GRNs",                 path: "/grns" },
  { keys: ["G", "V"], label: "Vendors",              path: "/vendors" },
  { keys: ["G", "A"], label: "Accounting",           path: "/accounting" },
  { keys: ["G", "T"], label: "GST Accounting",       path: "/gst" },
  { keys: ["G", "E"], label: "Expenses",             path: "/expenses" },
  { keys: ["G", "L"], label: "Ledger",               path: "/ledger" },
  { keys: ["G", "H"], label: "HR Dashboard",         path: "/hr" },
  { keys: ["G", "Y"], label: "Payroll",              path: "/hr/payroll" },
  { keys: ["G", "M"], label: "Manufacturing",        path: "/manufacturing" },
  { keys: ["G", "J"], label: "Job Work",             path: "/job-work" },
  { keys: ["G", "W"], label: "Inventory Reports",    path: "/inventory-reports" },
  { keys: ["G", "X"], label: "MIS Reports",          path: "/mis-reports" },
  { keys: ["G", "Z"], label: "AI Assistant",         path: "/ai-assistant" },
  { keys: ["G", "K"], label: "POS Counter",          path: "/pos" },
  { keys: ["G", "F"], label: "Fixed Assets",         path: "/fixed-assets" },
  { keys: ["G", "U"], label: "Banking",              path: "/banking" },
];

/** Exported so other global shortcut handlers (Layout, useModuleShortcuts) reuse the same check. */
export function isInputFocused() {
  const tag = document.activeElement?.tagName;
  const type = document.activeElement?.type;
  if (!tag) return false;
  if (tag === "INPUT" && type !== "checkbox" && type !== "radio") return true;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (document.activeElement?.isContentEditable) return true;
  return false;
}

// Bare function keys → app-wide navigation, matching Tally's own F-key
// layout exactly. See the module docstring above for the full legend.
const FKEY_ROUTES = {
  F3: "/admin/company-master",
  F4: "/vouchers?type=CONTRA",
  F5: "/vouchers?type=PAYMENT",
  F6: "/vouchers?type=RECEIPT",
  F7: "/vouchers?type=JOURNAL",
  F8: "/sales-orders",
  F9: "/purchase-orders-v2",
  F10: "/vouchers",
};

// Alt+letter → jump straight into a create-form on the target page, or to a
// destination displaced from its F-key by the Tally-accurate remap above.
// Alt+W is handled separately (opens the global WarehousePicker overlay, not
// a route) since "select a warehouse" is a cross-page action, not a single
// page to navigate to — see WarehousePicker.jsx's docstring for the scope note.
const ALT_ROUTES = {
  C: "/customers?new=1",
  P: "/products?new=1",
  I: "/products",       // Product Master — was F4 before the Tally remap
  L: "/stock-log",       // Stock Log — was F10 before the Tally remap
};

export function useKeyboardShortcuts({ onToggleHelp, onOpenSearch, onToggleCopilot, onOpenWarehousePicker }) {
  const navigate = useNavigate();

  useEffect(() => {
    let pendingG = false;
    let gTimer = null;

    const handler = (e) => {
      // Ctrl+K / Cmd+K → search (handled in Layout too, but keep here for consistency)
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        onOpenSearch?.();
        return;
      }

      // Ctrl+/ → toggle shortcuts help
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        onToggleHelp?.();
        return;
      }

      // Skip all single/combo key shortcuts when typing in an input
      if (isInputFocused()) return;

      // Alt+C / Alt+P / Alt+W — checked before the generic Alt early-return
      // below, and before any page's own capture-phase handler could have
      // already stopped propagation for a DIFFERENT Alt combo.
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        if (e.key.toUpperCase() === "W") {
          e.preventDefault();
          onOpenWarehousePicker?.();
          return;
        }
        const route = ALT_ROUTES[e.key.toUpperCase()];
        if (route) {
          e.preventDefault();
          navigate(route);
        }
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // Bare F-keys — global voucher/module navigation. A page that wants a
      // DIFFERENT meaning for one of these (there are none today) would
      // register it via useModuleShortcuts, whose capture-phase listener
      // runs first and can stopPropagation() to pre-empt this.
      if (FKEY_ROUTES[e.key]) {
        e.preventDefault();
        navigate(FKEY_ROUTES[e.key]);
        return;
      }

      const key = e.key.toUpperCase();

      // ? → toggle help overlay
      if (e.key === "?" || e.key === "/") {
        e.preventDefault();
        onToggleHelp?.();
        return;
      }

      // G prefix: arm for second key
      if (key === "G" && !pendingG) {
        pendingG = true;
        clearTimeout(gTimer);
        // Auto-cancel G prefix after 1.5 s if no second key pressed
        gTimer = setTimeout(() => { pendingG = false; }, 1500);
        return;
      }

      // Second key after G
      if (pendingG) {
        pendingG = false;
        clearTimeout(gTimer);
        const shortcut = SHORTCUTS.find((s) => s.keys[1] === key);
        if (shortcut) {
          e.preventDefault();
          navigate(shortcut.path);
        }
        return;
      }
    };

    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      clearTimeout(gTimer);
    };
  }, [navigate, onToggleHelp, onOpenSearch, onToggleCopilot, onOpenWarehousePicker]);
}
