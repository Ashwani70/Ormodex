import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import {
  Boxes, Plus, ArrowDownToLine, ArrowUpFromLine,
  TrendingDown, AlertTriangle, FileText, Trash2,
  Search, ChevronDown, PencilLine, Loader2, Download, Pencil,
  BarChart3,
} from "lucide-react";
import {
  PageHeader, PrimaryButton, SecondaryButton,
  Field, Input, Textarea, Select, StatusBadge, EmptyState, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import usePdfAction from "@/hooks/usePdfAction";
import useTrackingFlags from "@/hooks/useTrackingFlags";
import { missingTrackingFields } from "@/lib/tracking";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const num = (n, d = 2) => Number(n || 0).toFixed(d);

const UOM_OPTIONS = ["pcs", "kg", "g", "ltr", "ml", "mtr", "cm", "box", "set", "nos", "pair", "roll", "sheet"];
const UOM_LABELS = { pcs: "Pcs", nos: "Nos", mtr: "Mtr" };
const uomLabel = (u) => UOM_LABELS[u] || u;

// Normalize a product doc from /products into the shape the selector relies on.
// The API returns `id` (Mongo `_id` is projected out) and `quantity` for stock;
// we also tolerate `_id` / `availableQty` defensively so a backend shape change
// can't silently break the dropdown (value=undefined / blank qty).
const normalizeProduct = (p) => ({
  ...p,
  id: p.id ?? p._id ?? "",
  name: p.name ?? "",
  sku: p.sku ?? "",
  quantity: Number(p.quantity ?? p.availableQty ?? 0),
  unit: p.unit ?? "pcs",
});

const blankExistingItem = () => ({ product_id: "", quantity: 1, sku: "", product_name: "", description: "", remarks: "", unit: "pcs", rate: "", gst_rate: "", hsn_code: "", is_custom: false, batch_id: "", serial_id: "", expiry_date: "" });
const blankCustomItem = () => ({ product_id: "", quantity: 1, sku: "", product_name: "", description: "", unit: "pcs", remarks: "", rate: "", gst_rate: "", hsn_code: "", is_custom: true, batch_id: "", serial_id: "", expiry_date: "" });

// Material value of a line = rate × quantity (no GST charged; for ITC-04).
const lineTaxable = (it) => (parseFloat(it.rate) || 0) * (parseFloat(it.quantity) || 0);

// Searchable, dark-theme product picker. Shows name + SKU + available qty,
// supports type-to-filter for long lists, and surfaces loading / empty states.
// `disabledIds` prevents picking the same product on two rows.
// `triggerRef`/`onKeyDown` are an optional passthrough so this can act as a
// grid cell for useGridKeyNav (see JobWork's line-item grid): the trigger
// button is registered as the cell, Enter/Arrow keys reach the grid's
// handler when the dropdown is closed, and open/select still works exactly
// as before via mouse or Enter-to-open.
function SearchableProductSelect({ products, loading, value, onChange, disabledIds = [], invalid, triggerRef: externalTriggerRef, onKeyDown }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef(null);
  const ownTriggerRef = useRef(null);
  const setTriggerRef = (el) => {
    ownTriggerRef.current = el;
    if (typeof externalTriggerRef === "function") externalTriggerRef(el);
    else if (externalTriggerRef) externalTriggerRef.current = el;
  };
  const triggerRef = ownTriggerRef;
  const panelRef = useRef(null);
  // The panel renders in a portal at the document root so it escapes the
  // table's `overflow-x-auto` clipping (which was squashing/cutting off the
  // results list). We position it manually against the trigger's viewport rect.
  const [coords, setCoords] = useState(null);

  const placePanel = () => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, 288); // 288px = 18rem minimum
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < 260 && r.top > spaceBelow; // flip if cramped below
    setCoords({
      left: Math.min(r.left, window.innerWidth - width - 8),
      top: openUp ? undefined : r.bottom + 4,
      bottom: openUp ? window.innerHeight - r.top + 4 : undefined,
      width,
    });
  };

  useLayoutEffect(() => {
    if (!open) return;
    placePanel();
    const onScrollOrResize = () => placePanel();
    // Capture scroll on any ancestor (the modal body scrolls) so the panel
    // tracks the trigger instead of detaching from it.
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (ref.current && ref.current.contains(e.target)) return;
      if (panelRef.current && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const selected = products.find((p) => p.id === value);
  const q = query.trim().toLowerCase();
  const filtered = q
    ? products.filter((p) =>
        `${p.name || ""} ${p.sku || ""} ${p.category || ""}`.toLowerCase().includes(q))
    : products;

  return (
    <div className="relative" ref={ref}>
      <button
        ref={setTriggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          // Let Enter/Space open the picker as usual. Any other key the grid
          // cares about (Arrow nav, Insert, Ctrl+Delete, Escape) passes
          // through to the grid's own handler only while the dropdown is
          // closed — once open, the search input inside the portal owns
          // Arrow/Enter for choosing a result.
          if (!open && e.key !== "Enter" && e.key !== " ") onKeyDown?.(e);
        }}
        className={`w-full flex items-center justify-between gap-2 bg-background border text-left text-sm px-3 py-2 transition-colors focus:outline-none focus:border-primary ${
          invalid ? "border-red-500" : "border-input hover:border-primary/60"
        }`}
        style={{ borderRadius: "var(--radius)" }}
      >
        <span className={`truncate ${selected ? "text-foreground" : "text-muted-foreground"}`}>
          {selected ? (
            <>
              {selected.name}
              <span className="text-muted-foreground"> · {selected.sku || "—"}</span>
            </>
          ) : (
            "Select product…"
          )}
        </span>
        <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      </button>

      {open && coords && createPortal(
        <div
          ref={panelRef}
          className="fixed z-[100] bg-card border border-border shadow-2xl"
          style={{
            borderRadius: "var(--radius)",
            left: coords.left,
            top: coords.top,
            bottom: coords.bottom,
            width: coords.width,
          }}
        >
          <div className="flex items-center gap-2 px-2.5 py-2 border-b border-border">
            <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); triggerRef.current?.focus(); return; }
                if (e.key === "Enter") {
                  e.preventDefault();
                  const first = filtered.find((p) => !(disabledIds.includes(p.id) && p.id !== value));
                  if (first) { onChange(first.id); setOpen(false); setQuery(""); }
                }
              }}
              placeholder="Search name, SKU…"
              className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            {loading ? (
              <div className="flex items-center gap-2 px-3 py-4 text-muted-foreground font-mono text-xs">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading products…
              </div>
            ) : filtered.length === 0 ? (
              <div className="px-3 py-4 text-muted-foreground font-mono text-xs text-center">No products found</div>
            ) : (
              filtered.map((p) => {
                const isDisabled = disabledIds.includes(p.id) && p.id !== value;
                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => { onChange(p.id); setOpen(false); setQuery(""); }}
                    className={`w-full text-left px-3 py-2 flex items-center justify-between gap-3 border-b border-border/50 last:border-0 transition-colors ${
                      isDisabled
                        ? "opacity-40 cursor-not-allowed"
                        : p.id === value
                        ? "bg-primary/10 text-primary"
                        : "hover:bg-muted/40 text-foreground"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm">{p.name}</span>
                      <span className="block truncate font-mono text-[10px] text-muted-foreground">
                        {p.sku || "no-sku"}{isDisabled ? " · already added" : ""}
                      </span>
                    </span>
                    <span className="font-mono text-[11px] text-muted-foreground whitespace-nowrap flex-shrink-0">
                      {p.unit || "pcs"}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

const PAGE_LIMIT = 50;

export default function JobWork() {
  const { run: downloadChallanPdf, busyId: pdfBusy } = usePdfAction();
  const { run: downloadReceiptPdf, busyId: receiptPdfBusy } = usePdfAction();
  const [challans, setChallans] = useState([]);
  // Only PENDING challans are bulk-deletable. Guard against null/undefined status
  // from legacy rows — the backend normalizes to PENDING on read, but be defensive.
  const deletableChallans = challans.filter(c => (c.status || "PENDING") === "PENDING");
  const sel = useBulkSelect(deletableChallans);
  const [receipts, setReceipts] = useState([]);
  const receiptSel = useBulkSelect(receipts);
  const [products, setProducts] = useState([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("challans");
  const [pendingReport, setPendingReport] = useState([]);
  const [report, setReport] = useState(null);
  const [reportRange, setReportRange] = useState({ date_from: "", date_to: "" });
  const [reportLoading, setReportLoading] = useState(false);
  const [itc04, setItc04] = useState(null);
  const [itc04Period, setItc04Period] = useState(() => {
    const d = new Date();
    return `${String(d.getMonth() + 1).padStart(2, "0")}${d.getFullYear()}`;
  });

  // Challans tab: server-side search / overdue filter / pagination.
  const [challanSearch, setChallanSearch] = useState("");
  const [challanOverdueOnly, setChallanOverdueOnly] = useState(false);
  const [challanPage, setChallanPage] = useState(1);
  const [challanTotal, setChallanTotal] = useState(0);

  // Receipts tab: server-side search / pagination.
  const [receiptSearch, setReceiptSearch] = useState("");
  const [receiptPage, setReceiptPage] = useState(1);
  const [receiptTotal, setReceiptTotal] = useState(0);

  const [isChallanModalOpen, setIsChallanModalOpen] = useState(false);
  const [isReceiptModalOpen, setIsReceiptModalOpen] = useState(false);
  const [selectedChallan, setSelectedChallan] = useState(null);
  // null = create mode; a challan id = edit mode for the create/edit modal.
  const [editingChallanId, setEditingChallanId] = useState(null);
  const [savingChallan, setSavingChallan] = useState(false);
  // null = create mode; a receipt id = edit mode for the receipt modal.
  const [editingReceiptId, setEditingReceiptId] = useState(null);
  const [savingReceipt, setSavingReceipt] = useState(false);
  // Row-click detail viewers.
  const [detailChallan, setDetailChallan] = useState(null);
  const [detailReceipt, setDetailReceipt] = useState(null);
  // How many receipts a detail challan has (0 ⇒ editable).
  const [detailReceiptCount, setDetailReceiptCount] = useState(0);
  // Batch/serial/expiry tracking flags, resolved from each product's linked
  // stock_item via the backend. Drives which tracking fields show / are required.
  const { flagsFor, ensureFlags } = useTrackingFlags();

  const [newChallan, setNewChallan] = useState({
    job_worker_id: "", date: new Date().toISOString().split("T")[0],
    nature: "inputs",
    job_worker_gstin: "",
    gst_type: "auto",
    items: [blankExistingItem()],
    notes: "",
  });
  const [gstFetching, setGstFetching] = useState(false);

  const [newReceipt, setNewReceipt] = useState({
    date: new Date().toISOString().split("T")[0], items: [], notes: "",
  });

  const loadProducts = async () => {
    // Loaded independently so it can be refreshed when the challan modal opens,
    // and so a failure here is reported on its own (not masked by other calls).
    setProductsLoading(true);
    try {
      const pRes = await api.get("/products");
      setProducts(Array.isArray(pRes.data) ? pRes.data.map(normalizeProduct) : []);
    } catch (e) {
      setProducts([]);
      toast.error("Failed to load inventory products. Use 'Add Custom Product' to continue.");
    } finally {
      setProductsLoading(false);
    }
  };

  // Refresh products each time the challan modal opens, so the selector reflects
  // current inventory (and recovers if the initial load failed).
  const openChallanModal = () => {
    setEditingChallanId(null);
    setNewChallan({ job_worker_id: "", date: new Date().toISOString().split("T")[0], nature: "inputs", job_worker_gstin: "", gst_type: "auto", vehicle_no: "", transport: "", items: [blankExistingItem()], notes: "" });
    setIsChallanModalOpen(true);
    loadProducts();
  };

  // Pull each line's rate/HSN/GST from the chosen product (catalog items only).
  // Returns a patch merged into the item; rate falls back to cost_price.
  const productPatch = (productId) => {
    if (productId) ensureFlags([productId]);  // resolve tracking flags for the picker
    const pr = products.find((p) => p.id === productId);
    if (!pr) return { product_id: productId };
    return {
      product_id: productId,
      product_name: pr.name || "",
      sku: pr.sku || "",
      hsn_code: pr.hsn_code || "",
      unit: pr.unit || "pcs",
      rate: pr.cost_price ?? pr.selling_price ?? "",
      gst_rate: pr.gst_rate ?? "",
    };
  };

  // Fetch the selected job worker's GSTIN details and stamp them on the challan.
  const fetchJobWorkerGstin = async () => {
    const jw = vendors.find((s) => s.id === newChallan.job_worker_id);
    const gstin = (jw?.gstin || newChallan.job_worker_gstin || "").trim();
    if (!gstin) {
      toast.warning("No GSTIN on file for this job worker. Add one to the party first.");
      return;
    }
    setGstFetching(true);
    try {
      const { data } = await api.post("/customers/fetch-gstin", { gstin });
      setNewChallan((p) => ({ ...p, job_worker_gstin: gstin }));
      const name = data.trade_name || data.company_name;
      toast.success(`GSTIN verified${name ? `: ${name}` : ""} (${data.status || "fetched"})`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "GSTIN lookup failed.");
    } finally {
      setGstFetching(false);
    }
  };

  // Populate the create/edit modal from an existing challan and switch to edit mode.
  const openEditChallan = (challan) => {
    setEditingChallanId(challan.id);
    setNewChallan({
      job_worker_id: challan.job_worker_id || "",
      date: challan.date || new Date().toISOString().split("T")[0],
      nature: challan.nature || "inputs",
      job_worker_gstin: challan.job_worker_gstin || "",
      gst_type: challan.gst_type || "auto",
      vehicle_no: challan.vehicle_no || "",
      transport: challan.transport || "",
      notes: challan.notes || "",
      items: (challan.items || []).map(it => ({
        product_id: it.product_id || "",
        product_name: it.product_name || "",
        sku: it.sku || "",
        description: it.description || "",
        remarks: it.remarks || "",
        unit: it.unit || "pcs",
        quantity: it.quantity,
        rate: it.rate ?? "",
        gst_rate: it.gst_rate ?? "",
        hsn_code: it.hsn_code || "",
        is_custom: !!it.is_custom || !it.product_id,
        batch_id: it.batch_id || "",
        serial_id: it.serial_id || "",
        expiry_date: it.expiry_date || "",
      })),
    });
    ensureFlags((challan.items || []).map((it) => it.product_id));
    setDetailChallan(null);
    setIsChallanModalOpen(true);
    loadProducts();
  };

  const loadChallans = useCallback(async (opts = {}) => {
    const page = opts.page ?? challanPage;
    const search = opts.search ?? challanSearch;
    const overdueOnly = opts.overdueOnly ?? challanOverdueOnly;
    const params = { page, limit: PAGE_LIMIT };
    if (search) params.q = search;
    if (overdueOnly) params.overdue_only = true;
    const res = await api.get("/job-work/challans", { params });
    setChallans(res.data.items || []);
    setChallanTotal(res.data.total || 0);
  }, [challanPage, challanSearch, challanOverdueOnly]);

  const loadData = async () => {
    setLoading(true);
    // Each call is independent: a failing challans/vendors fetch must not blank
    // out the product list (which would break the challan product selector).
    const [cRes, sRes, custRes] = await Promise.allSettled([
      loadChallans(),
      api.get("/purchase/v2/vendors"),
      api.get("/customers"),
    ]);

    // Tag each party with its source so the picker can show whether the job
    // worker is a Vendor or a Customer (the two lists are otherwise merged).
    let combined = [];
    if (sRes.status === "fulfilled") {
      combined = [...combined, ...sRes.value.data.map(p => ({ ...p, party_type: "vendor" }))];
    }
    if (custRes.status === "fulfilled") {
      combined = [...combined, ...custRes.value.data.map(p => ({ ...p, party_type: "customer" }))];
    }

    // De-duplicate by id (a party in both lists keeps its first tag — vendor wins)
    const uniqueMap = {};
    combined.forEach(p => {
      if (p && p.id && !uniqueMap[p.id]) {
        uniqueMap[p.id] = p;
      }
    });
    setVendors(Object.values(uniqueMap));

    if (cRes.status === "rejected" || sRes.status === "rejected" || custRes.status === "rejected") {
      toast.error("Some Job Work data failed to load.");
    }
    await loadProducts();
    setLoading(false);
  };

  const loadReceipts = useCallback(async (opts = {}) => {
    const page = opts.page ?? receiptPage;
    const search = opts.search ?? receiptSearch;
    try {
      const params = { page, limit: PAGE_LIMIT };
      if (search) params.q = search;
      const res = await api.get("/job-work/receipts", { params });
      setReceipts(res.data.items || []);
      setReceiptTotal(res.data.total || 0);
    } catch { /* non-fatal */ }
  }, [receiptPage, receiptSearch]);

  const loadPendingReport = useCallback(async () => {
    try { const res = await api.get("/job-work/reports/pending"); setPendingReport(res.data); }
    catch { /* non-fatal */ }
  }, []);

  const loadReport = useCallback(async (range) => {
    setReportLoading(true);
    try {
      const params = new URLSearchParams();
      if (range?.date_from) params.set("date_from", range.date_from);
      if (range?.date_to) params.set("date_to", range.date_to);
      const qs = params.toString();
      const res = await api.get(`/job-work/reports/summary${qs ? `?${qs}` : ""}`);
      setReport(res.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load Job Work report");
    } finally {
      setReportLoading(false);
    }
  }, []);

  const loadItc04 = useCallback(async (period) => {
    try {
      const res = await api.get(`/job-work/itc-04?period=${period}`);
      setItc04(res.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load ITC-04"); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, []);

  // Challans tab: re-query the server whenever search/overdue-filter/page change.
  useEffect(() => {
    if (tab === "challans") loadChallans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, challanSearch, challanOverdueOnly, challanPage]);

  // Reset to page 1 whenever the challan search/filter changes.
  useEffect(() => { setChallanPage(1); }, [challanSearch, challanOverdueOnly]);

  // Receipts tab: re-query the server whenever search/page change.
  useEffect(() => {
    if (tab === "receipts") loadReceipts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, receiptSearch, receiptPage]);

  // Reset to page 1 whenever the receipt search changes.
  useEffect(() => { setReceiptPage(1); }, [receiptSearch]);

  // Load the active tab's data. For ITC-04 this also refreshes when the period
  // changes; the "Generate ITC-04" button remains for an explicit re-fetch.
  useEffect(() => {
    if (tab === "pending") loadPendingReport();
    else if (tab === "report") loadReport(reportRange);
    else if (tab === "itc04") loadItc04(itc04Period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, itc04Period, loadPendingReport, loadReport, loadItc04]);

  const handleCreateChallan = async (e) => {
    e.preventDefault();
    if (!newChallan.job_worker_id) { toast.warning("Please select a Job Worker."); return; }

    for (const it of newChallan.items) {
      if (it.is_custom) {
        if (!String(it.product_name || "").trim()) { toast.warning("Please enter a product name for the custom line item."); return; }
      } else if (!it.product_id) {
        toast.warning("Please select a product for each line item."); return;
      }
      if (!(parseFloat(it.quantity) > 0)) { toast.warning("Each line item needs a quantity greater than zero."); return; }
    }

    const parseOpt = (v) => (v === "" || v === null || v === undefined ? null : parseFloat(v));
    const finalItems = newChallan.items.map(it => {
      if (it.is_custom) {
        return {
          product_id: null, product_name: it.product_name.trim(), sku: it.sku || "",
          description: (it.description || "").trim(), quantity: parseFloat(it.quantity),
          unit: it.unit || "pcs", remarks: (it.remarks || "").trim(),
          rate: parseOpt(it.rate), gst_rate: parseOpt(it.gst_rate), is_custom: true,
        };
      }
      const pr = products.find(p => p.id === it.product_id);
      return {
        product_id: it.product_id, product_name: pr?.name || "", sku: pr?.sku || "",
        description: (it.description || "").trim(), quantity: parseFloat(it.quantity),
        unit: pr?.unit || "pcs", remarks: (it.remarks || "").trim(),
        rate: parseOpt(it.rate), gst_rate: parseOpt(it.gst_rate),
        hsn_code: pr?.hsn_code || null, is_custom: false,
        batch_id: it.batch_id || null, serial_id: it.serial_id || null, expiry_date: it.expiry_date || null,
      };
    });
    for (const item of finalItems) {
      if (item.is_custom) continue;
      // Stock availability isn't tracked on the Product master (managed in a
      // separate module), so no client-side over-stock block here; the server
      // still enforces any real stock rules.
      // Client-side mirror of the server's tracking rules (server still enforces).
      const miss = missingTrackingFields(item, flagsFor(item.product_id));
      if (miss.length) {
        toast.error(`${miss.join(" & ")} required for '${item.product_name || item.product_id}'.`); return;
      }
    }

    if (savingChallan) return;
    setSavingChallan(true);
    try {
      const worker = vendors.find(s => s.id === newChallan.job_worker_id);
      const workerName = worker ? (worker.company ? (worker.name ? `${worker.company} (${worker.name})` : worker.company) : (worker.name || "")) : "";
      const gstin = newChallan.job_worker_gstin || worker?.gstin || "";
      const body = { ...newChallan, job_worker_name: workerName, job_worker_gstin: gstin, items: finalItems };
      if (editingChallanId) {
        await api.put(`/job-work/challans/${editingChallanId}`, body);
        toast.success("Job Work Challan updated!");
      } else {
        await api.post("/job-work/challans", body);
        toast.success("Job Work Challan generated!");
      }
      setIsChallanModalOpen(false);
      setEditingChallanId(null);
      setNewChallan({ job_worker_id: "", date: new Date().toISOString().split("T")[0], nature: "inputs", job_worker_gstin: "", gst_type: "auto", vehicle_no: "", transport: "", items: [blankExistingItem()], notes: "" });
      loadData();
    } catch (err) { toast.error("Failed: " + (err.response?.data?.detail || "")); } finally { setSavingChallan(false); }
  };

  const handleDeleteChallan = async (challan) => {
    if (!window.confirm(`Delete challan ${challan.challan_number || challan.id}? This cannot be undone.`)) return;
    try {
      await api.delete(`/job-work/challans/${challan.id}`);
      toast.success(`Challan ${challan.challan_number || ""} deleted`);
      loadData();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Unknown error";
      toast.error(`Delete failed: ${detail}`);
    }
  };

  const handleBulkDelete = async () => {
    const targets = sel.selectedIds;
    if (targets.length === 0) return;
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/job-work/challans/${id}`),
      { reload: loadData }
    );
    if (failed > 0 && ok === 0) {
      toast.error(`All ${failed} delete(s) failed. Check that the challans are PENDING and have no receipts logged.`);
    } else if (failed > 0) {
      toast.warning(`Deleted ${ok}, failed ${failed}. Failed challans may have receipts logged or are not PENDING.`);
    } else {
      toast.success(`Deleted ${ok} challan${ok === 1 ? "" : "s"}`);
    }
  };

  // Open the read-only / editable challan detail viewer. Editability requires
  // status PENDING and zero receipts (matching the backend PUT guard), so we
  // fetch the receipt count up front.
  const handleOpenChallanDetail = async (challan) => {
    setDetailChallan(challan);
    setDetailReceiptCount(0);
    try {
      const res = await api.get("/job-work/receipts", { params: { challan_id: challan.id, limit: 1000 } });
      setDetailReceiptCount(res.data.total ?? (res.data.items || []).length);
    } catch { /* leave count at 0; backend still enforces the guard */ }
  };

  // Opens the receipt modal in create mode (against a challan's remaining pending qty)
  // or edit mode (pre-filled from an existing receipt, excluding its own qty from "already received").
  const handleOpenReceiptModal = async (challan, editReceipt = null) => {
    setSelectedChallan(challan);
    setEditingReceiptId(editReceipt?.id || null);
    try {
      const res = await api.get("/job-work/receipts", { params: { challan_id: challan.id, limit: 1000 } });
      const allReceipts = res.data.items || [];
      const keyOf = (it) => (it.is_custom || !it.product_id) ? `custom::${it.product_name || ""}` : it.product_id;
      const receivedMap = {};
      allReceipts
        .filter(r => r.id !== editReceipt?.id)
        .forEach(r => r.items?.forEach(it => {
          const k = keyOf(it);
          receivedMap[k] = (receivedMap[k] || 0) + parseFloat(it.quantity_received || 0);
        }));
      const editItemsByKey = {};
      if (editReceipt) {
        editReceipt.items?.forEach(it => { editItemsByKey[keyOf(it)] = it; });
      }
      setNewReceipt({
        date: editReceipt?.date || new Date().toISOString().split("T")[0],
        items: challan.items.map(it => {
          const recv = receivedMap[keyOf(it)] || 0;
          const pend = Math.max(0, it.quantity - recv);
          const editIt = editItemsByKey[keyOf(it)];
          return {
            product_id: it.product_id || null, product_name: it.product_name, sku: it.sku || "",
            is_custom: !!it.is_custom, quantity_sent: it.quantity, quantity_already_received: recv,
            quantity_pending: pend,
            quantity_received: editIt ? editIt.quantity_received : pend,
            accepted_quantity: editIt?.accepted_quantity ?? null,
            rejected_quantity: editIt?.rejected_quantity || 0,
            scrap_quantity: editIt?.scrap_quantity || 0,
            batch_id: editIt?.batch_id || "", serial_id: editIt?.serial_id || "", expiry_date: editIt?.expiry_date || "",
          };
        }),
        notes: editReceipt?.notes || "",
      });
      ensureFlags(challan.items.map((it) => it.product_id));
      setIsReceiptModalOpen(true);
    } catch { toast.error("Failed to load existing receipts."); }
  };

  const handleCreateReceipt = async (e) => {
    e.preventDefault();
    for (const item of newReceipt.items) {
      if (item.quantity_received > item.quantity_pending + 1e-5) {
        toast.error(`Received qty for ${item.product_name} exceeds pending (${item.quantity_pending}).`); return;
      }
      // Tracking fields required only for items received back (qty > 0).
      if (parseFloat(item.quantity_received) > 0) {
        const miss = missingTrackingFields(item, flagsFor(item.product_id));
        if (miss.length) {
          toast.error(`${miss.join(" & ")} required for '${item.product_name || item.product_id}'.`); return;
        }
      }
    }
    if (savingReceipt) return;
    setSavingReceipt(true);
    try {
      if (editingReceiptId) {
        await api.put(`/job-work/receipts/${editingReceiptId}`, newReceipt);
        toast.success("Material receipt updated!");
      } else {
        await api.post(`/job-work/challans/${selectedChallan.id}/receipt`, newReceipt);
        toast.success("Material receipt registered!");
      }
      setIsReceiptModalOpen(false);
      setEditingReceiptId(null);
      loadData();
      loadReceipts();
    } catch (err) { toast.error("Failed: " + (err.response?.data?.detail || "")); } finally { setSavingReceipt(false); }
  };

  const handleDeleteReceipt = async (receipt) => {
    if (!window.confirm(`Delete receipt ${receipt.receipt_number || receipt.id}? This cannot be undone.`)) return;
    try {
      await api.delete(`/job-work/receipts/${receipt.id}`);
      toast.success(`Receipt ${receipt.receipt_number || ""} deleted`);
      loadReceipts();
      loadData();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || "Unknown error";
      toast.error(`Delete failed: ${detail}`);
    }
  };

  // Edit-receipt entry point from the Receipts tab row action: the row only
  // carries the receipt + a flattened challan_number/job_worker_name, not the
  // challan's full item list needed by the receipt modal — fetch it fresh.
  const handleEditReceiptClick = async (receipt) => {
    try {
      const res = await api.get(`/job-work/challans/${receipt.challan_id}`);
      handleOpenReceiptModal(res.data, receipt);
    } catch {
      toast.error("Failed to load the parent challan for this receipt.");
    }
  };

  const handleBulkDeleteReceipts = async () => {
    const targets = receiptSel.selectedIds;
    if (targets.length === 0) return;
    const { ok, failed } = await receiptSel.runDelete(
      (id) => api.delete(`/job-work/receipts/${id}`),
      { reload: () => Promise.all([loadReceipts(), loadData()]) }
    );
    if (failed > 0 && ok === 0) {
      toast.error(`All ${failed} delete(s) failed.`);
    } else if (failed > 0) {
      toast.warning(`Deleted ${ok}, failed ${failed}.`);
    } else {
      toast.success(`Deleted ${ok} receipt${ok === 1 ? "" : "s"}`);
    }
  };

  // Shared blob-download helper for the two Excel export endpoints.
  const exportExcel = async (endpoint, params, filename) => {
    try {
      const resp = await api.get(endpoint, { params, responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed");
    }
  };

  const TABS_DEF = [
    { id: "challans", label: "Challans Sent", icon: ArrowUpFromLine },
    { id: "receipts", label: "Receipts Inward", icon: ArrowDownToLine },
    { id: "pending",  label: "Pending Report",  icon: TrendingDown },
    { id: "report",   label: "Job Work Report", icon: BarChart3 },
    { id: "itc04",    label: "ITC-04",          icon: FileText },
  ];

  // ── Keyboard-first line-item entry: Challan modal grid ──────────────────
  // Fixed columns 0-6 = Product, Description, HSN, Quantity, Unit, Rate, GST%.
  // Columns 7+ are the conditional batch/expiry/serial tracking cells that
  // appear directly below a row when the chosen product requires them —
  // included in the SAME row's column count (via colCount(row)) so Enter
  // flows straight from GST% into tracking fields and then on to the next
  // row's Product cell, instead of getting swallowed by data-grid-managed.
  const challanTrackingColsForRow = (row) => {
    const item = newChallan.items[row];
    if (!item || item.is_custom || !item.product_id) return 0;
    const flags = flagsFor(item.product_id);
    if (!flags) return 0;
    return (flags.track_batch ? 1 : 0) + (flags.track_expiry ? 1 : 0) + (flags.track_serial ? 1 : 0);
  };
  const challanColsForRow = (row) => 7 + challanTrackingColsForRow(row);
  const challanAddLine = () => setNewChallan(p => ({ ...p, items: [...p.items, blankExistingItem()] }));
  const challanInsertLineAfter = (idx) => setNewChallan(p => {
    const items = [...p.items];
    items.splice(idx + 1, 0, blankExistingItem());
    return { ...p, items };
  });
  const challanRemoveLineKeepingOne = (idx) => setNewChallan(p => ({
    ...p,
    items: p.items.length > 1 ? p.items.filter((_, i) => i !== idx) : [blankExistingItem()],
  }));
  const challanGridNav = useGridKeyNav({
    rowCount: newChallan.items.length,
    colCount: challanColsForRow,
    onRowComplete: challanAddLine,
    onInsertRow: challanInsertLineAfter,
    onDeleteRow: challanRemoveLineKeepingOne,
  });

  // Enter-as-Tab across the whole challan form (job worker / GSTIN / dates ⇒
  // falls through to the grid's own Enter handling inside the line-item
  // table ⇒ Notes). Ctrl+Enter saves, Ctrl+Shift+Enter saves & opens a fresh
  // challan, Escape cancels. Auto-focuses the Job Worker field on open.
  const challanFormRef = useRef(null);
  useEnterNavigation(challanFormRef, {
    enabled: isChallanModalOpen,
    autoFocus: true,
    onSave: () => handleCreateChallan(new Event("submit", { cancelable: true })),
    onSaveAndNew: async () => {
      await handleCreateChallan(new Event("submit", { cancelable: true }));
      openChallanModal();
    },
    onCancel: () => setIsChallanModalOpen(false),
  });

  // ── Keyboard-first line-item entry: Receipt modal grid ──────────────────
  // Each row's fixed columns 0-3 = Received/Accepted/Rejected/Scrap qty
  // (Sent & Already-Received are disabled/readOnly, not part of the grid).
  // Columns 4+ mirror the same conditional tracking fields as the challan
  // grid. Rows are 1:1 with the parent challan's items — no add/remove here,
  // so onRowComplete/onInsertRow/onDeleteRow are omitted (undefined is safe;
  // useGridKeyNav no-ops those keys when the callback isn't provided).
  const receiptTrackingColsForRow = (row) => {
    const item = newReceipt.items[row];
    if (!item || item.is_custom || !item.product_id) return 0;
    const flags = flagsFor(item.product_id);
    if (!flags) return 0;
    return (flags.track_batch ? 1 : 0) + (flags.track_expiry ? 1 : 0) + (flags.track_serial ? 1 : 0);
  };
  const receiptColsForRow = (row) => 4 + receiptTrackingColsForRow(row);
  const receiptGridNav = useGridKeyNav({
    rowCount: newReceipt.items.length,
    colCount: receiptColsForRow,
  });

  // Enter-as-Tab across the receipt form (Inward Date ⇒ grid ⇒ Remarks).
  const receiptFormRef = useRef(null);
  useEnterNavigation(receiptFormRef, {
    enabled: isReceiptModalOpen,
    autoFocus: true,
    onSave: () => handleCreateReceipt(new Event("submit", { cancelable: true })),
    onCancel: () => { setIsReceiptModalOpen(false); setEditingReceiptId(null); },
  });

  // Global module shortcut: Ctrl/Cmd+N opens a new Job Work Challan (the
  // primary create action on this page) when no modal is already open.
  useModuleShortcuts({
    onNew: () => { if (!isChallanModalOpen && !isReceiptModalOpen) openChallanModal(); },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inventory & Production"
        title="Job Work Processing"
        description="Track materials sent to job workers · Record returns · Monitor overdue challans · Generate ITC-04."
        actions={<PrimaryButton icon={Plus} onClick={openChallanModal}>New Job Work Challan</PrimaryButton>}
      />

      {/* Tab bar */}
      <div className="flex border-b border-zinc-800 gap-4">
        {TABS_DEF.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`py-3 px-1 font-mono text-xs uppercase tracking-wider border-b-2 flex items-center gap-1.5 transition-colors ${
                tab === t.id ? "border-primary text-primary font-bold" : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}>
              <Icon className="w-3.5 h-3.5" />{t.label}
            </button>
          );
        })}
      </div>

      {/* ── Challans Tab ─────────────────────────────────────────────────────── */}
      {tab === "challans" && (() => {
        const flatChallanItems = challans.flatMap(c => 
          (c.items || []).map((it, idx) => ({
            ...it,
            challan_id: c.id,
            challan_number: c.challan_number,
            date: c.date,
            due_date: c.due_date,
            job_worker_name: c.job_worker_name,
            status: c.status,
            is_overdue: c.is_overdue,
            deemed_supply: c.deemed_supply,
            raw_challan: c,
            item_idx: idx
          }))
        );
        return (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[220px] max-w-sm">
                <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  value={challanSearch}
                  onChange={e => setChallanSearch(e.target.value)}
                  placeholder="Search challan no. / job worker…"
                  className="w-full bg-background border border-input text-foreground text-xs pl-8 pr-3 py-2 focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <label className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground cursor-pointer select-none">
                <input type="checkbox" checked={challanOverdueOnly}
                  onChange={e => setChallanOverdueOnly(e.target.checked)}
                  className="w-3.5 h-3.5 accent-[var(--primary)]" />
                Overdue only
              </label>
              <SecondaryButton
                icon={Download}
                onClick={() => exportExcel(
                  "/job-work/challans/export",
                  { q: challanSearch || undefined, overdue_only: challanOverdueOnly || undefined },
                  "job-work-challans.xlsx",
                )}
              >
                Export Excel
              </SecondaryButton>
            </div>

            {flatChallanItems.length === 0 ? (
              <EmptyState message="No Job Work Challans yet" />
            ) : (
              <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border bg-muted text-muted-foreground">
                      <th className="px-3 py-2.5 w-10">
                        <SelectCheckbox
                          label="Select all deletable challans"
                          checked={sel.allSelected}
                          indeterminate={sel.someSelected}
                          onChange={sel.toggleAll}
                        />
                      </th>
                      <th className="px-3 py-2.5 uppercase">Challan No</th>
                      <th className="px-3 py-2.5 uppercase">Challan Date</th>
                      <th className="px-3 py-2.5 uppercase">Due Date</th>
                      <th className="px-3 py-2.5 uppercase">Job Worker</th>
                      <th className="px-3 py-2.5 uppercase">Item Name</th>
                      <th className="px-3 py-2.5 uppercase">Item Code</th>
                      <th className="px-3 py-2.5 uppercase">UOM</th>
                      <th className="px-3 py-2.5 uppercase">Sent Qty</th>
                      <th className="px-3 py-2.5 uppercase">Balance Qty</th>
                      <th className="px-3 py-2.5 uppercase">Status</th>
                      <th className="px-3 py-2.5 uppercase text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flatChallanItems.map((item, index) => {
                      const c = item.raw_challan;
                      const overdue = item.is_overdue || item.deemed_supply;
                      const isDeletable = (item.status || "PENDING") === "PENDING";
                      return (
                        <tr key={`${item.challan_id}-${item.product_id || 'custom'}-${index}`}
                          className={`border-b border-border hover:bg-muted/30 ${sel.isSelected(item.challan_id) ? "bg-primary/5" : ""} ${overdue ? "text-red-400" : "text-foreground"}`}>
                          <td className="px-3 py-2.5">
                            {isDeletable && item.item_idx === 0 ? (
                              <SelectCheckbox
                                label={`Select challan ${item.challan_number}`}
                                checked={sel.isSelected(item.challan_id)}
                                onChange={() => sel.toggle(item.challan_id)}
                              />
                            ) : null}
                          </td>
                          <td className="px-3 py-2.5 font-bold text-primary cursor-pointer hover:underline"
                            onClick={() => handleOpenChallanDetail(c)}>
                            {item.challan_number || "—"}
                          </td>
                          <td className="px-3 py-2.5 text-muted-foreground">{item.date || "—"}</td>
                          <td className={`px-3 py-2.5 ${overdue ? "text-red-400 font-bold" : "text-muted-foreground"}`}>
                            {item.due_date || "—"}
                            {overdue && <span className="ml-1 text-[9px] border border-red-700 text-red-400 px-1 uppercase">Overdue</span>}
                          </td>
                          <td className="px-3 py-2.5">{item.job_worker_name || <span className="text-muted-foreground">—</span>}</td>
                          <td className="px-3 py-2.5 font-semibold text-zinc-100">{item.product_name || "—"}</td>
                          <td className="px-3 py-2.5 font-mono text-zinc-300">{item.sku || "—"}</td>
                          <td className="px-3 py-2.5 text-zinc-400">{item.unit || "pcs"}</td>
                          <td className="px-3 py-2.5 font-bold text-zinc-100">{item.quantity}</td>
                          <td className="px-3 py-2.5 font-bold text-primary">{item.quantity_pending ?? item.quantity}</td>
                          <td className="px-3 py-2.5">
                            <StatusBadge status={item.status} />
                            {item.deemed_supply && <div className="mt-1 text-[9px] text-red-400 uppercase">Deemed Supply</div>}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            {item.item_idx === 0 ? (
                              <div className="inline-flex gap-1 items-center">
                                {(item.status || "PENDING") !== "COMPLETED" && (
                                  <button onClick={() => handleOpenReceiptModal(c)}
                                    className="bg-muted hover:bg-primary/10 hover:text-primary text-muted-foreground border border-border px-2 py-1 font-mono text-[10px] font-bold rounded transition-colors">
                                    Log Receipt
                                  </button>
                                )}
                                <button
                                  title="Download PDF"
                                  onClick={() => downloadChallanPdf(`/job-work/challans/${item.challan_id}/pdf`, `${item.challan_number}.pdf`, item.challan_id)}
                                  disabled={pdfBusy === item.challan_id}
                                  className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-50 rounded transition-colors"
                                >
                                  <Download className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  title="Edit challan"
                                  disabled={(item.status || "PENDING") !== "PENDING"}
                                  onClick={() => openEditChallan(c)}
                                  className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-40 rounded transition-colors"
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  title="Delete challan"
                                  disabled={(item.status || "PENDING") !== "PENDING"}
                                  onClick={() => handleDeleteChallan(c)}
                                  className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center disabled:opacity-40 rounded transition-colors"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {challanTotal > PAGE_LIMIT && (
              <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                <span>Page {challanPage} of {Math.ceil(challanTotal / PAGE_LIMIT)} · {challanTotal} challans</span>
                <div className="flex gap-2">
                  <SecondaryButton onClick={() => setChallanPage(p => Math.max(1, p - 1))} disabled={challanPage === 1}>Prev</SecondaryButton>
                  <SecondaryButton onClick={() => setChallanPage(p => p + 1)} disabled={challanPage * PAGE_LIMIT >= challanTotal}>Next</SecondaryButton>
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* ── Receipts Tab ──────────────────────────────────────────────────────── */}
      {tab === "receipts" && (() => {
        const flatReceiptItems = receipts.flatMap(r =>
          (r.items || []).map((it, idx) => ({
            ...it,
            receipt_id: r.id,
            receipt_number: r.receipt_number,
            date: r.date,
            challan_number: r.challan_number,
            job_worker_name: r.job_worker_name,
            notes: r.notes,
            raw_receipt: r,
            item_idx: idx
          }))
        );
        return (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[220px] max-w-sm">
                <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  value={receiptSearch}
                  onChange={e => setReceiptSearch(e.target.value)}
                  placeholder="Search receipt no. / challan no. / job worker…"
                  className="w-full bg-background border border-input text-foreground text-xs pl-8 pr-3 py-2 focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <SecondaryButton
                icon={Download}
                onClick={() => exportExcel(
                  "/job-work/receipts/export",
                  { q: receiptSearch || undefined },
                  "job-work-receipts.xlsx",
                )}
              >
                Export Excel
              </SecondaryButton>
            </div>

            {flatReceiptItems.length === 0 ? <EmptyState message="No inward receipts logged yet" /> : (
              <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400">
                      <th className="p-3 w-10">
                        <SelectCheckbox
                          label="Select all receipts"
                          checked={receiptSel.allSelected}
                          indeterminate={receiptSel.someSelected}
                          onChange={receiptSel.toggleAll}
                        />
                      </th>
                      <th className="p-3 uppercase">Receipt No</th>
                      <th className="p-3 uppercase">Receipt Date</th>
                      <th className="p-3 uppercase">Challan No</th>
                      <th className="p-3 uppercase">Job Worker</th>
                      <th className="p-3 uppercase">Item Name</th>
                      <th className="p-3 uppercase">Sent Qty</th>
                      <th className="p-3 uppercase">Received Qty</th>
                      <th className="p-3 uppercase text-green-500">Accepted Qty</th>
                      <th className="p-3 uppercase">Rejected Qty</th>
                      <th className="p-3 uppercase">Scrap Qty</th>
                      <th className="p-3 uppercase text-primary">Pending Qty</th>
                      <th className="p-3 uppercase">Status</th>
                      <th className="p-3 uppercase">Remarks</th>
                      <th className="p-3 uppercase text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flatReceiptItems.map((item, index) => (
                      <tr key={`${item.receipt_id}-${item.product_id || 'custom'}-${index}`}
                        className={`border-b border-zinc-900 hover:bg-zinc-900/20 text-zinc-100 ${receiptSel.isSelected(item.receipt_id) ? "bg-primary/5" : ""}`}>
                        <td className="p-3">
                          {item.item_idx === 0 ? (
                            <SelectCheckbox
                              label={`Select receipt ${item.receipt_number}`}
                              checked={receiptSel.isSelected(item.receipt_id)}
                              onChange={() => receiptSel.toggle(item.receipt_id)}
                            />
                          ) : null}
                        </td>
                        <td className="p-3 font-bold text-green-500 cursor-pointer hover:underline"
                          onClick={() => setDetailReceipt(item.raw_receipt)}>
                          {item.receipt_number || "—"}
                        </td>
                        <td className="p-3 text-zinc-300">{item.date || "—"}</td>
                        <td className="p-3 text-primary font-bold">{item.challan_number || "—"}</td>
                        <td className="p-3 text-zinc-300">{item.job_worker_name || "—"}</td>
                        <td className="p-3 font-semibold">{item.product_name || "—"}</td>
                        <td className="p-3 text-zinc-400">{item.quantity_sent}</td>
                        <td className="p-3 text-green-400 font-bold">{item.quantity_received}</td>
                        <td className="p-3 text-green-500 font-bold">{item.accepted_quantity}</td>
                        <td className="p-3 text-red-400">{item.rejected_quantity}</td>
                        <td className="p-3 text-yellow-400">{item.scrap_quantity}</td>
                        <td className="p-3 text-primary font-bold">{item.quantity_pending}</td>
                        <td className="p-3">
                          {item.item_idx === 0 ? <StatusBadge status={item.raw_receipt.status} /> : null}
                        </td>
                        <td className="p-3 text-zinc-400">{item.notes || "—"}</td>
                        <td className="p-3 text-right">
                          {item.item_idx === 0 ? (
                            <div className="inline-flex gap-1 items-center">
                              <button
                                title="Download PDF"
                                onClick={() => downloadReceiptPdf(`/job-work/receipts/${item.receipt_id}/pdf`, `${item.receipt_number}.pdf`, item.receipt_id)}
                                disabled={receiptPdfBusy === item.receipt_id}
                                className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-50 rounded transition-colors"
                              >
                                <Download className="w-3.5 h-3.5" />
                              </button>
                              <button
                                title="Edit receipt"
                                onClick={() => handleEditReceiptClick(item.raw_receipt)}
                                className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center rounded transition-colors"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                title="Delete receipt"
                                onClick={() => handleDeleteReceipt(item.raw_receipt)}
                                className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center rounded transition-colors"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {receiptTotal > PAGE_LIMIT && (
              <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                <span>Page {receiptPage} of {Math.ceil(receiptTotal / PAGE_LIMIT)} · {receiptTotal} receipts</span>
                <div className="flex gap-2">
                  <SecondaryButton onClick={() => setReceiptPage(p => Math.max(1, p - 1))} disabled={receiptPage === 1}>Prev</SecondaryButton>
                  <SecondaryButton onClick={() => setReceiptPage(p => p + 1)} disabled={receiptPage * PAGE_LIMIT >= receiptTotal}>Next</SecondaryButton>
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* ── Pending Report ────────────────────────────────────────────────────── */}
      {tab === "pending" && (
        <div className="space-y-4">
          {pendingReport.length === 0 ? <EmptyState message="No pending materials at job workers" /> : (
            <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400">
                    <th className="p-3 uppercase">Challan No</th>
                    <th className="p-3 uppercase">Job Worker</th>
                    <th className="p-3 uppercase">Item</th>
                    <th className="p-3 uppercase">Sent Qty</th>
                    <th className="p-3 uppercase">Total Received Qty</th>
                    <th className="p-3 uppercase text-primary">Pending Qty</th>
                    <th className="p-3 uppercase">Due Date</th>
                    <th className="p-3 uppercase">Days Pending</th>
                    <th className="p-3 uppercase">Overdue Status</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingReport.map((p, i) => {
                    const overdue = p.is_overdue;
                    return (
                      <tr key={i} className={`border-b border-zinc-900 hover:bg-zinc-900/20 ${overdue ? "text-red-300" : "text-zinc-100"}`}>
                        <td className="p-3 font-bold text-primary">{p.challan_number}</td>
                        <td className="p-3">{p.job_worker_name}</td>
                        <td className="p-3 font-semibold">{p.product_name}</td>
                        <td className="p-3">{p.quantity_sent}</td>
                        <td className="p-3 text-green-500">{num(p.quantity_received)}</td>
                        <td className="p-3 font-bold text-primary">{num(p.quantity_pending)}</td>
                        <td className={`p-3 ${overdue ? "text-red-400 font-bold" : "text-zinc-400"}`}>{p.due_date || "—"}</td>
                        <td className="p-3 font-mono">{p.days_pending !== null ? `${p.days_pending} days` : "—"}</td>
                        <td className={`p-3 font-bold ${overdue ? "text-red-400" : "text-green-400"}`}>{p.overdue_status || (overdue ? "Overdue" : "Active")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Job Work Report Tab ───────────────────────────────────────────────── */}
      {tab === "report" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1">From</label>
              <input
                type="date"
                value={reportRange.date_from}
                onChange={e => setReportRange(r => ({ ...r, date_from: e.target.value }))}
                className="bg-background border border-input text-foreground text-xs px-3 py-2 focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1">To</label>
              <input
                type="date"
                value={reportRange.date_to}
                onChange={e => setReportRange(r => ({ ...r, date_to: e.target.value }))}
                className="bg-background border border-input text-foreground text-xs px-3 py-2 focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <PrimaryButton onClick={() => loadReport(reportRange)}>{reportLoading ? "Loading…" : "Generate Report"}</PrimaryButton>
            <SecondaryButton
              icon={Download}
              disabled={pdfBusy}
              onClick={() => {
                const params = new URLSearchParams();
                if (reportRange.date_from) params.set("date_from", reportRange.date_from);
                if (reportRange.date_to) params.set("date_to", reportRange.date_to);
                const qs = params.toString();
                downloadChallanPdf(
                  `/job-work/reports/summary/pdf${qs ? `?${qs}` : ""}`,
                  "job-work-report.pdf",
                  "jw-report",
                );
              }}
            >
              Download PDF
            </SecondaryButton>
          </div>

          {report && (
            <div className="space-y-6">
              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
                {[
                  { label: "Challans", value: report.summary.total_challans },
                  { label: "Job Workers", value: report.summary.total_job_workers },
                  { label: "Taxable Value", value: `₹${inr(report.summary.total_taxable_value)}` },
                  { label: "GST (ref)", value: `₹${inr(report.summary.total_gst)}` },
                  { label: "Overdue", value: report.summary.overdue_challans, danger: report.summary.overdue_challans > 0 },
                ].map(s => (
                  <div key={s.label} className="bg-card border border-border p-4 rounded-md text-card-foreground">
                    <div className={`font-mono font-black text-2xl ${s.danger ? "text-red-400" : "text-foreground"}`}>{s.value}</div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-1">{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Combined history: one row per challan (Sent / Received / Pending / Status) */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Job Work Report — Challan History</div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Challan No</th>
                        <th className="p-3 text-left uppercase">Date</th>
                        <th className="p-3 text-left uppercase">Due Date</th>
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-right uppercase">Sent Qty</th>
                        <th className="p-3 text-right uppercase">Received Qty</th>
                        <th className="p-3 text-right uppercase text-primary">Pending Qty</th>
                        <th className="p-3 text-left uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(!report.challans || report.challans.length === 0) && (
                        <tr><td colSpan={8} className="p-6 text-center text-muted-foreground">No job-work challans in this period</td></tr>
                      )}
                      {(report.challans || []).map((c) => (
                        <tr key={c.challan_id} className="border-b border-border hover:bg-muted/20 text-foreground">
                          <td className="p-3 font-bold text-primary">{c.challan_number || "—"}</td>
                          <td className="p-3">{c.date || "—"}</td>
                          <td className="p-3">{c.due_date || "—"}</td>
                          <td className="p-3">{c.job_worker_name}</td>
                          <td className="p-3 text-right">{num(c.quantity_sent)}</td>
                          <td className="p-3 text-right text-green-500">{num(c.quantity_received)}</td>
                          <td className="p-3 text-right font-bold text-primary">{num(c.quantity_pending)}</td>
                          <td className="p-3"><StatusBadge status={c.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Job worker summary */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Job Worker Summary</div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-right uppercase">Challans</th>
                        <th className="p-3 text-right uppercase">Sent</th>
                        <th className="p-3 text-right uppercase">Received</th>
                        <th className="p-3 text-right uppercase text-primary">Pending</th>
                        <th className="p-3 text-right uppercase">Scrap</th>
                        <th className="p-3 text-right uppercase">Taxable</th>
                        <th className="p-3 text-right uppercase">GST (ref)</th>
                        <th className="p-3 text-right uppercase">Overdue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.job_workers.length === 0 && (
                        <tr><td colSpan={9} className="p-6 text-center text-muted-foreground">No job-work challans in this period</td></tr>
                      )}
                      {report.job_workers.map((w, i) => (
                        <tr key={w.job_worker_id || i} className="border-b border-border hover:bg-muted/20 text-foreground">
                          <td className="p-3">{w.job_worker_name}</td>
                          <td className="p-3 text-right">{w.challans}</td>
                          <td className="p-3 text-right">{num(w.qty_sent)}</td>
                          <td className="p-3 text-right text-green-500">{num(w.qty_received)}</td>
                          <td className="p-3 text-right font-bold text-primary">{num(w.qty_pending)}</td>
                          <td className="p-3 text-right text-muted-foreground">{num(w.scrap)}</td>
                          <td className="p-3 text-right">₹{inr(w.taxable_value)}</td>
                          <td className="p-3 text-right text-muted-foreground">₹{inr(w.total_gst)}</td>
                          <td className={`p-3 text-right ${w.overdue > 0 ? "text-red-400 font-bold" : "text-muted-foreground"}`}>{w.overdue}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* GST summary */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  GST Summary <span className="normal-case tracking-normal">(reference only — no tax charged on a §143 challan)</span>
                </div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-right uppercase">Taxable Value</th>
                        <th className="p-3 text-right uppercase">CGST</th>
                        <th className="p-3 text-right uppercase">SGST</th>
                        <th className="p-3 text-right uppercase">IGST</th>
                        <th className="p-3 text-right uppercase">Total GST</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="text-foreground">
                        <td className="p-3 text-right">₹{inr(report.gst_summary.taxable_value)}</td>
                        <td className="p-3 text-right">₹{inr(report.gst_summary.cgst)}</td>
                        <td className="p-3 text-right">₹{inr(report.gst_summary.sgst)}</td>
                        <td className="p-3 text-right">₹{inr(report.gst_summary.igst)}</td>
                        <td className="p-3 text-right font-bold">₹{inr(report.gst_summary.total_gst)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Aging */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Aging of Pending Material (days since challan date)</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {report.aging.map(a => {
                    const danger = a.bucket === "180+" && a.quantity_pending > 0;
                    const warn = a.bucket === "91-180" && a.quantity_pending > 0;
                    return (
                      <div key={a.bucket} className="bg-card border border-border p-4 rounded-md text-card-foreground">
                        <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{a.bucket} days</div>
                        <div className={`font-mono font-black text-xl mt-1 ${danger ? "text-red-400" : warn ? "text-yellow-400" : "text-foreground"}`}>{num(a.quantity_pending)}</div>
                        <div className="font-mono text-[11px] text-muted-foreground mt-0.5">₹{inr(a.value_pending)}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── ITC-04 Tab ────────────────────────────────────────────────────────── */}
      {tab === "itc04" && (
        <div className="space-y-4">
          <div className="flex items-end gap-4">
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Period (MMYYYY)</label>
              <input
                value={itc04Period}
                onChange={e => setItc04Period(e.target.value)}
                placeholder="e.g. 062025"
                maxLength={6}
                className="bg-background border border-input text-foreground text-xs px-3 py-2 focus:outline-none focus:border-primary w-36 transition-colors"
              />
            </div>
            <PrimaryButton onClick={() => loadItc04(itc04Period)}>Generate ITC-04</PrimaryButton>
          </div>

          {itc04 && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Challans Issued", value: itc04.summary.total_challans_issued },
                  { label: "Receipts Received", value: itc04.summary.total_receipts },
                  { label: "Taxable Value Sent", value: `₹${inr(itc04.summary.total_taxable_value_sent)}` },
                  { label: "Overdue Challans", value: itc04.summary.overdue_challans, danger: itc04.summary.overdue_challans > 0 },
                ].map(s => (
                  <div key={s.label} className="bg-card border border-border p-4 rounded-md text-card-foreground">
                    <div className={`font-mono font-black text-2xl ${s.danger ? "text-red-400" : "text-foreground"}`}>{s.value}</div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-1">{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Table 4 */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  Table 4 — Goods Dispatched to Job Worker ({itc04.period_label})
                </div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Challan No</th>
                        <th className="p-3 text-left uppercase">Date</th>
                        <th className="p-3 text-left uppercase">Due Date</th>
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-left uppercase">Product</th>
                        <th className="p-3 text-right uppercase">Qty Sent</th>
                        <th className="p-3 text-right uppercase">Taxable Value</th>
                        <th className="p-3 text-left uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itc04.table4_outward_challans.length === 0 && (
                        <tr><td colSpan={8} className="p-6 text-center text-muted-foreground">No outward challans in this period</td></tr>
                      )}
                      {itc04.table4_outward_challans.map((row, i) => (
                        <tr key={i} className={`border-b border-border hover:bg-muted/20 ${row.is_overdue ? "text-red-300" : "text-foreground"}`}>
                          <td className="p-3 font-bold text-primary">{row.challan_number}</td>
                          <td className="p-3">{row.challan_date}</td>
                          <td className={`p-3 ${row.is_overdue ? "text-red-400 font-bold" : "text-muted-foreground"}`}>{row.due_date || "—"}</td>
                          <td className="p-3">{row.job_worker_name}</td>
                          <td className="p-3">{row.product_name}</td>
                          <td className="p-3 text-right">{num(row.quantity_sent, 4)} {row.unit}</td>
                          <td className="p-3 text-right">₹{inr(row.taxable_value)}</td>
                          <td className="p-3">
                            <StatusBadge status={row.challan_status} />
                            {row.is_overdue && <span className="ml-1 text-[9px] text-red-400 uppercase border border-red-800 px-1">Deemed Supply</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Table 5 */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  Table 5 — Goods Received Back from Job Worker ({itc04.period_label})
                </div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Receipt No</th>
                        <th className="p-3 text-left uppercase">Date</th>
                        <th className="p-3 text-left uppercase">Orig. Challan</th>
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-left uppercase">Product</th>
                        <th className="p-3 text-right uppercase">Qty Received</th>
                        <th className="p-3 text-right uppercase">Scrap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itc04.table5_inward_receipts.length === 0 && (
                        <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No inward receipts in this period</td></tr>
                      )}
                      {itc04.table5_inward_receipts.map((row, i) => (
                        <tr key={i} className="border-b border-border hover:bg-muted/20 text-foreground">
                          <td className="p-3 font-bold text-green-500">{row.receipt_number}</td>
                          <td className="p-3">{row.receipt_date}</td>
                          <td className="p-3 text-muted-foreground">{row.original_challan_number}</td>
                          <td className="p-3">{row.job_worker_name}</td>
                          <td className="p-3">{row.product_name}</td>
                          <td className="p-3 text-right">{num(row.quantity_received, 4)} {row.unit}</td>
                          <td className="p-3 text-right text-muted-foreground">{row.scrap_quantity > 0 ? num(row.scrap_quantity, 4) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="text-muted-foreground font-mono text-[10px]">
                Note: ITC-04 must be filed quarterly. This report covers challans issued/received in {itc04.period_label}.
                Deemed supply arises when goods are not returned within the statutory window (365 days for inputs, 1095 days for capital goods).
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Modal: New / Edit Challan ──────────────────────────────────────────── */}
      <Modal
        open={isChallanModalOpen}
        onClose={() => setIsChallanModalOpen(false)}
        title={editingChallanId ? "Edit Job Work Challan" : "Generate Job Work Challan"}
        size="full"
        bodyClassName="p-6 bg-[var(--bg)]"
        footer={
          <>
            <SecondaryButton onClick={() => setIsChallanModalOpen(false)} className="h-[46px]">Cancel</SecondaryButton>
            <PrimaryButton type="submit" form="jw-challan-form" className="h-[46px]" disabled={savingChallan}>
              {savingChallan ? "Saving…" : (editingChallanId ? "Save Changes" : "Generate Challan")}
            </PrimaryButton>
          </>
        }
      >
        {(() => {
          const taxable = newChallan.items.reduce((s, it) => s + lineTaxable(it), 0);
          const gst = newChallan.items.reduce((s, it) => s + lineTaxable(it) * (parseFloat(it.gst_rate) || 0) / 100, 0);
          const t = newChallan.gst_type || "auto";
          const gstLabel = t === "inter" ? "IGST (reference only)"
            : t === "intra" ? "CGST + SGST (reference only)"
            : "GST · auto split (reference only)";

          return (
        <form id="jw-challan-form" ref={challanFormRef} onSubmit={handleCreateChallan} className="flex flex-col gap-6">
          {/* ── Section: Job worker & challan details ───────────────────── */}
          <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
            {/* Row 1: Job Worker (full width) · Row 2: GSTIN 80% + Verify 20%
                · Row 3: Challan Date 50% + GST Type 50%. Collapses to one
                column on mobile. */}
            <div className="flex flex-col gap-4">
              <Field label="Outsource Job Worker" required>
                <Select
                  className="h-[46px]"
                  value={newChallan.job_worker_id}
                  onChange={e => {
                    const id = e.target.value;
                    const jw = vendors.find(s => s.id === id);
                    // Pre-fill the GSTIN box from the chosen party (still editable);
                    // don't clobber a value the user has already typed for the same row.
                    setNewChallan(p => ({
                      ...p,
                      job_worker_id: id,
                      job_worker_gstin: jw?.gstin || p.job_worker_gstin || "",
                    }));
                  }}
                  required
                >
                  <option value="">Select outsourced partner…</option>
                  {vendors.map(s => {
                    const label = s.company ? `${s.company} (${s.name})` : s.name;
                    const tag = s.party_type === "customer" ? "Customer" : "Vendor";
                    return <option key={s.id} value={s.id}>{label} — {tag}</option>;
                  })}
                </Select>
              </Field>

              {/* Manually enter / override the job worker's GST number. Pre-fills
                  from the party when available, but you can type it for a party
                  that has none on file. Drives the Auto GST-type state detection
                  (first 2 digits = state code). GSTIN ~80% + Verify ~20%. */}
              <Field
                label="Job Worker GSTIN"
                hint="Type the GST number here if the party hasn't shared it. Used for the challan & ITC-04."
              >
                <div className="grid grid-cols-1 sm:grid-cols-[4fr_1fr] gap-2">
                  <Input
                    type="text"
                    value={newChallan.job_worker_gstin}
                    onChange={e => setNewChallan(p => ({ ...p, job_worker_gstin: e.target.value.toUpperCase().trim() }))}
                    placeholder="e.g. 27ABCDE1234F1Z5 (optional)"
                    maxLength={15}
                    className="h-[46px] uppercase"
                  />
                  <SecondaryButton
                    type="button"
                    className="h-[46px] w-full"
                    icon={gstFetching ? Loader2 : Search}
                    onClick={fetchJobWorkerGstin}
                    disabled={gstFetching || !(newChallan.job_worker_gstin || "").trim()}
                  >
                    {gstFetching ? "Verifying…" : "Verify"}
                  </SecondaryButton>
                </div>
              </Field>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Challan Date" required>
                  <Input className="h-[46px]" type="date" value={newChallan.date} onChange={e => setNewChallan(p => ({ ...p, date: e.target.value }))} required />
                </Field>
                <Field label="GST Type">
                  <Select className="h-[46px]" value={newChallan.gst_type} onChange={e => setNewChallan(p => ({ ...p, gst_type: e.target.value }))}>
                    <option value="auto">Auto (from GSTIN)</option>
                    <option value="intra">Intra-state (CGST+SGST)</option>
                    <option value="inter">Inter-state (IGST)</option>
                  </Select>
                </Field>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Vehicle No">
                  <Input className="h-[46px]" type="text" value={newChallan.vehicle_no || ""} onChange={e => setNewChallan(p => ({ ...p, vehicle_no: e.target.value }))} placeholder="e.g. MH-12-AB-1234 (optional)" />
                </Field>
                <Field label="Transport / Transporter">
                  <Input className="h-[46px]" type="text" value={newChallan.transport || ""} onChange={e => setNewChallan(p => ({ ...p, transport: e.target.value }))} placeholder="e.g. VRL Logistics (optional)" />
                </Field>
              </div>
            </div>

            {/* Selected job worker summary card */}
            {(() => {
              const jw = vendors.find(s => s.id === newChallan.job_worker_id);
              if (!jw) return null;
              const stateLine = [jw.state, jw.state_code && `(Code: ${jw.state_code})`].filter(Boolean).join(" ");
              return (
                <div className="mt-4 rounded-lg border border-border bg-[var(--bg)] px-4 py-3 text-xs text-muted-foreground space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">{jw.company ? `${jw.company} (${jw.name})` : jw.name}</span>
                    <span className="font-mono text-[9px] uppercase keep-caps tracking-wider border border-border rounded px-1.5 py-0.5 text-muted-foreground">
                      {jw.party_type === "customer" ? "Customer" : "Vendor"}
                    </span>
                  </div>
                  {jw.address
                    ? jw.address.split("\n").map((line, i) => <div key={i}>{line}</div>)
                    : <div className="italic">No address on file for this job worker.</div>}
                  {stateLine && <div>State: {stateLine}</div>}
                  {jw.gstin && (
                    <div className="pt-0.5">
                      <span className="font-semibold text-foreground">On-file GSTIN: {jw.gstin}</span>
                    </div>
                  )}
                </div>
              );
            })()}

            {newChallan.gst_type === "auto" && !(newChallan.job_worker_gstin || vendors.find(s => s.id === newChallan.job_worker_id)?.gstin) && (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-700">
                <AlertTriangle className="w-4 h-4 mt-px flex-shrink-0" />
                <span>No GSTIN on file — Auto defaults to Intra-state (CGST+SGST). Pick a GST Type above to set it manually.</span>
              </div>
            )}
          </section>

          {/* ── Section: Material line items ────────────────────────────── */}
          <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h4 className="font-display font-semibold text-sm text-foreground">Material Line Items</h4>
              <span className="text-xs text-muted-foreground">{newChallan.items.length} item{newChallan.items.length === 1 ? "" : "s"}</span>
            </div>

            {/* Only the table scrolls horizontally, and only when the viewport is
                narrower than the column set. The grid uses a fixed colgroup so
                every row aligns perfectly. */}
            <div className="overflow-x-auto rounded-lg border border-border">
              <table data-grid-managed className="w-full text-left text-xs" style={{ minWidth: "1170px" }}>
                <colgroup>
                  <col style={{ width: "260px" }} />
                  <col style={{ width: "220px" }} />
                  <col style={{ width: "120px" }} />
                  <col style={{ width: "90px" }} />
                  <col style={{ width: "90px" }} />
                  <col style={{ width: "120px" }} />
                  <col style={{ width: "90px" }} />
                  <col style={{ width: "120px" }} />
                  <col style={{ width: "70px" }} />
                </colgroup>
                <thead className="sticky top-0 z-10">
                  <tr className="border-b border-border bg-muted text-muted-foreground">
                    <th className="px-3 py-2.5 font-semibold">Product</th>
                    <th className="px-3 py-2.5 font-semibold">Description</th>
                    <th className="px-3 py-2.5 font-semibold">HSN Code</th>
                    <th className="px-3 py-2.5 font-semibold text-right">Quantity</th>
                    <th className="px-3 py-2.5 font-semibold">Unit</th>
                    <th className="px-3 py-2.5 font-semibold text-right">Rate ₹</th>
                    <th className="px-3 py-2.5 font-semibold text-right">GST %</th>
                    <th className="px-3 py-2.5 font-semibold text-right">Taxable ₹</th>
                    <th className="px-3 py-2.5 font-semibold text-center">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {newChallan.items.map((item, idx) => {
                    const disabledIds = newChallan.items.filter((_, i) => i !== idx).map(it => it.product_id).filter(Boolean);
                    const flags = item.is_custom ? null : flagsFor(item.product_id);
                    const showTracking = !item.is_custom && item.product_id && flags &&
                      (flags.track_batch || flags.track_serial || flags.track_expiry);

                    const patch = (changes) => setNewChallan(p => ({
                      ...p, items: p.items.map((it, i) => (i === idx ? { ...it, ...changes } : it)),
                    }));

                    return (
                      <Fragment key={idx}>
                      <tr className={`align-top ${showTracking ? "" : "border-b border-border"}`}>
                        <td className="px-3 py-2 align-top">
                          {item.is_custom ? (
                            <div className="space-y-1.5">
                              <Input
                                type="text"
                                value={item.product_name}
                                placeholder="Product name *"
                                onChange={e => patch({ product_name: e.target.value })}
                                required
                                className="h-10"
                                ref={challanGridNav.registerCell(idx, 0)}
                                onKeyDown={challanGridNav.handleKeyDown(idx, 0)}
                              />
                              <span className="inline-flex items-center gap-1 text-[10px] text-primary">
                                <PencilLine className="w-3 h-3" /> Custom product
                              </span>
                            </div>
                          ) : (
                            <div className="space-y-1">
                              <SearchableProductSelect
                                products={products}
                                loading={productsLoading}
                                value={item.product_id}
                                disabledIds={disabledIds}
                                onChange={(id) => patch(productPatch(id))}
                                triggerRef={challanGridNav.registerCell(idx, 0)}
                                onKeyDown={challanGridNav.handleKeyDown(idx, 0)}
                              />
                              {!productsLoading && products.length === 0 && (
                                <button
                                  type="button"
                                  onClick={() => patch({ is_custom: true, product_id: "" })}
                                  className="text-[10px] text-primary hover:underline"
                                >
                                  No inventory products — add as custom
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <Input
                            type="text"
                            value={item.description || ""}
                            placeholder={item.is_custom ? "Work / description (optional)" : "Optional"}
                            onChange={e => patch({ description: e.target.value })}
                            className="h-10"
                            ref={challanGridNav.registerCell(idx, 1)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 1)}
                          />
                          {item.is_custom && (
                            <Input
                              type="text"
                              value={item.remarks || ""}
                              placeholder="Remarks (optional)"
                              onChange={e => patch({ remarks: e.target.value })}
                              className="h-10 mt-1.5"
                            />
                          )}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <Input
                            type="text"
                            value={item.hsn_code || ""}
                            placeholder="e.g. 7308"
                            onChange={e => patch({ hsn_code: e.target.value })}
                            className="h-10 w-full"
                            ref={challanGridNav.registerCell(idx, 2)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 2)}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <NumericInput
                            compact
                            value={item.quantity}
                            onChange={v => patch({ quantity: v })}
                            placeholder="0"
                            className="h-10 w-full"
                            ref={challanGridNav.registerCell(idx, 3)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 3)}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <Select
                            value={item.unit || "pcs"}
                            onChange={e => patch({ unit: e.target.value })}
                            className="h-10 px-2"
                            aria-label="Unit of measure"
                            ref={challanGridNav.registerCell(idx, 4)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 4)}
                          >
                            {UOM_OPTIONS.map(u => <option key={u} value={u}>{uomLabel(u)}</option>)}
                          </Select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <NumericInput
                            compact
                            value={item.rate}
                            onChange={v => patch({ rate: v })}
                            placeholder="0.00"
                            className="h-10 w-full"
                            ref={challanGridNav.registerCell(idx, 5)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 5)}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <NumericInput
                            compact
                            value={item.gst_rate}
                            onChange={v => patch({ gst_rate: v })}
                            placeholder="0"
                            max={100}
                            className="h-10 w-full"
                            ref={challanGridNav.registerCell(idx, 6)}
                            onKeyDown={challanGridNav.handleKeyDown(idx, 6)}
                          />
                        </td>
                        <td className="px-3 py-2 text-right tabular text-sm font-semibold align-middle text-foreground">
                          {lineTaxable(item) > 0 ? `₹${inr(lineTaxable(item))}` : "—"}
                        </td>
                        <td className="px-3 py-2 text-center align-middle">
                          <button
                            type="button"
                            onClick={() => {
                              if (newChallan.items.length > 1) {
                                setNewChallan(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }));
                              } else {
                                toast.warning("Challan must contain at least one item.");
                              }
                            }}
                            className="w-9 h-9 rounded-lg border border-border text-[var(--danger)] hover:border-[var(--danger)] hover:bg-[#FEE2E2] transition-colors flex items-center justify-center mx-auto bg-background"
                            title="Delete Row"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                      {showTracking && (() => {
                        // Tracking cells extend this row's grid columns past the
                        // fixed 0-6 (see challanTrackingColsForRow) — assign each
                        // visible tracking field the next column index in the
                        // same batch → expiry → serial order that hook uses.
                        let col = 6;
                        const batchCol = flags.track_batch ? ++col : -1;
                        const expiryCol = flags.track_expiry ? ++col : -1;
                        const serialCol = flags.track_serial ? ++col : -1;
                        return (
                        <tr className="border-b border-border bg-muted/30">
                          <td colSpan={9} className="px-3 py-3">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                              {flags.track_batch && (
                                <Field label="Batch No." required>
                                  <Input required value={item.batch_id || ""} data-testid={`jw-batch-${idx}`}
                                    onChange={e => patch({ batch_id: e.target.value })} className="h-10"
                                    ref={challanGridNav.registerCell(idx, batchCol)}
                                    onKeyDown={challanGridNav.handleKeyDown(idx, batchCol)} />
                                </Field>
                              )}
                              {flags.track_expiry && (
                                <Field label="Expiry Date" required>
                                  <Input required type="date" value={item.expiry_date || ""} data-testid={`jw-expiry-${idx}`}
                                    onChange={e => patch({ expiry_date: e.target.value })} className="h-10"
                                    ref={challanGridNav.registerCell(idx, expiryCol)}
                                    onKeyDown={challanGridNav.handleKeyDown(idx, expiryCol)} />
                                </Field>
                              )}
                              {flags.track_serial && (
                                <Field label="Serial No." required>
                                  <Input required value={item.serial_id || ""} data-testid={`jw-serial-${idx}`}
                                    onChange={e => patch({ serial_id: e.target.value })} className="h-10"
                                    ref={challanGridNav.registerCell(idx, serialCol)}
                                    onKeyDown={challanGridNav.handleKeyDown(idx, serialCol)} />
                                </Field>
                              )}
                            </div>
                          </td>
                        </tr>
                        );
                      })()}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Add-row actions: side-by-side, equal height */}
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <SecondaryButton
                icon={Plus}
                className="h-[46px] w-full"
                onClick={() => setNewChallan(p => ({ ...p, items: [...p.items, blankExistingItem()] }))}
              >
                Add Existing Product
              </SecondaryButton>
              <SecondaryButton
                icon={PencilLine}
                className="h-[46px] w-full"
                onClick={() => setNewChallan(p => ({ ...p, items: [...p.items, blankCustomItem()] }))}
              >
                Add Custom Product
              </SecondaryButton>
            </div>
          </section>

          {/* ── Section: Totals summary card (right-aligned) ────────────── */}
          <div className="flex justify-end">
            <div className="w-full max-w-sm rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="space-y-2.5 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Total Taxable Value</span>
                  <span className="tabular font-medium text-foreground">₹{inr(taxable)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">{gstLabel}</span>
                  <span className="tabular font-medium text-foreground">₹{inr(gst)}</span>
                </div>
                <div className="border-t border-border pt-2.5 flex items-center justify-between">
                  <span className="font-semibold text-foreground">Grand Total</span>
                  <span className="tabular font-display font-bold text-lg text-foreground">₹{inr(taxable + gst)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* ── Section: Notes ─────────────────────────────────────────── */}
          <Field label="Notes">
            <Textarea
              value={newChallan.notes}
              onChange={e => setNewChallan(p => ({ ...p, notes: e.target.value }))}
              placeholder="e.g. Galvanizing, fabrication instructions"
              className="w-full min-h-[120px]"
            />
          </Field>

          {/* ── Section: Important notes (highlighted info box) ─────────── */}
          <div className="rounded-xl border border-[#BFDBFE] bg-[#EFF6FF] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0 text-[#1E40AF]" />
              <div className="text-sm text-[#1E3A8A]">
                <div className="font-semibold mb-1.5">Important Notes</div>
                <ul className="list-disc pl-5 space-y-1 text-[13px] leading-relaxed text-[#1E40AF]">
                  <li>No tax is charged on a §143 job-work challan — GST figures above are for reference only.</li>
                  <li>Goods must be received back within the statutory window (365 days for inputs, 1095 days for capital goods) or deemed-supply provisions apply.</li>
                  <li>Each challan is reported in the quarterly ITC-04 return; keep the GSTIN accurate.</li>
                </ul>
              </div>
            </div>
          </div>
        </form>
          );
        })()}
      </Modal>

      {/* ── Modal: Record / Edit Receipt ──────────────────────────────────────── */}
      <Modal open={isReceiptModalOpen} onClose={() => setIsReceiptModalOpen(false)} title={editingReceiptId ? "Edit Material Inward Receipt" : "Record Material Inward Receipt"}>
        {selectedChallan && (
          <form ref={receiptFormRef} onSubmit={handleCreateReceipt} className="space-y-4">
            <div className="font-mono text-xs text-muted-foreground">
              From: <span className="text-foreground font-bold">{selectedChallan.job_worker_name}</span>
              {" · "}Challan: <span className="text-foreground font-bold">{selectedChallan.challan_number}</span>
              {selectedChallan.is_overdue && (
                <div className="mt-1 flex items-center gap-1 text-red-400 text-[10px]">
                  <AlertTriangle className="w-3 h-3" /> This challan is overdue — deemed supply provisions may apply.
                </div>
              )}
            </div>

            <Field label="Inward Date" required>
              <Input type="date" value={newReceipt.date} onChange={e => setNewReceipt(p => ({ ...p, date: e.target.value }))} required />
            </Field>

            <div data-grid-managed className="space-y-3">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground block">Receive Quantities</span>
              {newReceipt.items.map((item, idx) => {
                const setItem = (changes) => {
                  const updated = [...newReceipt.items];
                  updated[idx] = { ...updated[idx], ...changes };
                  setNewReceipt(p => ({ ...p, items: updated }));
                };
                const flags = item.is_custom ? null : flagsFor(item.product_id);
                const showTracking = !item.is_custom && item.product_id && flags &&
                  (flags.track_batch || flags.track_serial || flags.track_expiry);
                // Tracking cells extend this row's grid columns past the fixed
                // 0-3 (Received/Accepted/Rejected/Scrap) — see
                // receiptTrackingColsForRow, same batch → expiry → serial order.
                let trackCol = 3;
                const batchCol = flags?.track_batch ? ++trackCol : -1;
                const expiryCol = flags?.track_expiry ? ++trackCol : -1;
                const serialCol = flags?.track_serial ? ++trackCol : -1;
                return (
                <div key={idx} className="bg-card p-3 border border-border space-y-2 text-card-foreground">
                  <div className="font-bold text-foreground">{item.product_name} ({item.sku})</div>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                    <Field label="Sent"><Input value={item.quantity_sent} disabled readOnly /></Field>
                    <Field label="Already Recv"><Input value={item.quantity_already_received || 0} disabled readOnly /></Field>
                    <Field label="Received Qty" required>
                      <NumericInput value={item.quantity_received}
                        onChange={v => setItem({ quantity_received: v })}
                        placeholder="0"
                        ref={receiptGridNav.registerCell(idx, 0)}
                        onKeyDown={receiptGridNav.handleKeyDown(idx, 0)} />
                    </Field>
                    <Field label="Accepted Qty" hint="Leave blank = received minus rejected/scrap">
                      <NumericInput value={item.accepted_quantity ?? ""}
                        onChange={v => setItem({ accepted_quantity: v === "" ? null : v })}
                        placeholder="Auto"
                        ref={receiptGridNav.registerCell(idx, 1)}
                        onKeyDown={receiptGridNav.handleKeyDown(idx, 1)} />
                    </Field>
                    <Field label="Rejected Qty">
                      <NumericInput value={item.rejected_quantity}
                        onChange={v => setItem({ rejected_quantity: v })}
                        placeholder="0"
                        ref={receiptGridNav.registerCell(idx, 2)}
                        onKeyDown={receiptGridNav.handleKeyDown(idx, 2)} />
                    </Field>
                    <Field label="Scrap Qty">
                      <NumericInput value={item.scrap_quantity}
                        onChange={v => setItem({ scrap_quantity: v })}
                        placeholder="0"
                        ref={receiptGridNav.registerCell(idx, 3)}
                        onKeyDown={receiptGridNav.handleKeyDown(idx, 3)} />
                    </Field>
                  </div>
                  {showTracking && (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-2 border-t border-border">
                      {flags.track_batch && (
                        <Field label="Batch No." required>
                          <Input required value={item.batch_id || ""} data-testid={`jwr-batch-${idx}`}
                            onChange={e => setItem({ batch_id: e.target.value })}
                            ref={receiptGridNav.registerCell(idx, batchCol)}
                            onKeyDown={receiptGridNav.handleKeyDown(idx, batchCol)} />
                        </Field>
                      )}
                      {flags.track_expiry && (
                        <Field label="Expiry Date" required>
                          <Input required type="date" value={item.expiry_date || ""} data-testid={`jwr-expiry-${idx}`}
                            onChange={e => setItem({ expiry_date: e.target.value })}
                            ref={receiptGridNav.registerCell(idx, expiryCol)}
                            onKeyDown={receiptGridNav.handleKeyDown(idx, expiryCol)} />
                        </Field>
                      )}
                      {flags.track_serial && (
                        <Field label="Serial No." required>
                          <Input required value={item.serial_id || ""} data-testid={`jwr-serial-${idx}`}
                            onChange={e => setItem({ serial_id: e.target.value })}
                            ref={receiptGridNav.registerCell(idx, serialCol)}
                            onKeyDown={receiptGridNav.handleKeyDown(idx, serialCol)} />
                        </Field>
                      )}
                    </div>
                  )}
                </div>
                );
              })}
            </div>

            <Field label="Remarks">
              <Textarea value={newReceipt.notes} onChange={e => setNewReceipt(p => ({ ...p, notes: e.target.value }))} placeholder="Damage, delivery notes, etc." rows={2} />
            </Field>

            <div className="flex justify-end gap-2 pt-4">
              <SecondaryButton onClick={() => { setIsReceiptModalOpen(false); setEditingReceiptId(null); }}>Cancel</SecondaryButton>
              <PrimaryButton type="submit" disabled={savingReceipt}>{savingReceipt ? "Saving…" : (editingReceiptId ? "Save Changes" : "Log Receipt Return")}</PrimaryButton>
            </div>
          </form>
        )}
      </Modal>

      {/* ── Modal: Challan Detail (view / edit) ────────────────────────────────── */}
      <Modal
        open={!!detailChallan}
        onClose={() => setDetailChallan(null)}
        title={detailChallan ? `Challan ${detailChallan.challan_number}` : "Challan"}
        size="lg"
      >
        {detailChallan && (() => {
          const editable = (detailChallan.status || "PENDING") === "PENDING" && detailReceiptCount === 0;
          return (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                <div><span className="text-muted-foreground">Job Worker:</span> <span className="font-bold text-foreground">{detailChallan.job_worker_name || "—"}</span></div>
                <div><span className="text-muted-foreground">GSTIN:</span> <span className="text-foreground">{detailChallan.job_worker_gstin || "—"}</span></div>
                <div><span className="text-muted-foreground">Status:</span> <StatusBadge status={detailChallan.status} /></div>
                <div><span className="text-muted-foreground">Challan Date:</span> <span className="text-foreground">{detailChallan.date || "—"}</span></div>
                <div><span className="text-muted-foreground">Due Date:</span> <span className="text-foreground">{detailChallan.due_date || "—"}</span></div>
                <div><span className="text-muted-foreground">Receipts Logged:</span> <span className="text-foreground">{detailReceiptCount}</span></div>
                <div><span className="text-muted-foreground">Nature:</span> <span className="text-foreground">{detailChallan.nature === "capital_goods" ? "Capital Goods" : "Inputs"}</span></div>
                <div><span className="text-muted-foreground">GST Type:</span> <span className="text-foreground">{detailChallan.is_inter_state ? "Inter-state (IGST)" : "Intra-state (CGST+SGST)"}{detailChallan.gst_type && detailChallan.gst_type !== "auto" ? " · manual" : ""}</span></div>
              </div>

              <div className="border border-border overflow-x-auto rounded-md">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                      <th className="p-2.5 uppercase">Product</th>
                      <th className="p-2.5 uppercase">Description</th>
                      <th className="p-2.5 uppercase text-right">Qty</th>
                      <th className="p-2.5 uppercase text-right">Rate</th>
                      <th className="p-2.5 uppercase text-right">GST %</th>
                      <th className="p-2.5 uppercase text-right">Taxable Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailChallan.items?.map((it, i) => (
                      <tr key={it.product_id || `d-${i}`} className="border-b border-border">
                        <td className="p-2.5 text-foreground">{it.product_name}{it.is_custom && <span className="ml-1 text-[9px] text-primary">Custom</span>}</td>
                        <td className="p-2.5 text-muted-foreground">{it.description || "—"}</td>
                        <td className="p-2.5 text-right text-foreground">{it.quantity} {it.unit || "pcs"}</td>
                        <td className="p-2.5 text-right text-muted-foreground">{it.rate > 0 ? `₹${inr(it.rate)}` : "—"}</td>
                        <td className="p-2.5 text-right text-muted-foreground">{(it.gst_rate ?? "") !== "" ? `${it.gst_rate}%` : "—"}</td>
                        <td className="p-2.5 text-right text-muted-foreground">{it.taxable_value > 0 ? `₹${inr(it.taxable_value)}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* GST breakdown — reference only, no tax charged on a §143 challan */}
              {(detailChallan.total_taxable_value > 0 || detailChallan.total_gst > 0) && (
                <div className="flex justify-end">
                  <div className="w-full sm:w-72 border border-border rounded-md divide-y divide-border font-mono text-xs">
                    <div className="flex justify-between px-3 py-1.5">
                      <span className="text-muted-foreground">Taxable Value</span>
                      <span className="text-foreground">₹{inr(detailChallan.total_taxable_value)}</span>
                    </div>
                    {detailChallan.is_inter_state ? (
                      <div className="flex justify-between px-3 py-1.5">
                        <span className="text-muted-foreground">IGST</span>
                        <span className="text-foreground">₹{inr(detailChallan.total_igst)}</span>
                      </div>
                    ) : (
                      <>
                        <div className="flex justify-between px-3 py-1.5">
                          <span className="text-muted-foreground">CGST</span>
                          <span className="text-foreground">₹{inr(detailChallan.total_cgst)}</span>
                        </div>
                        <div className="flex justify-between px-3 py-1.5">
                          <span className="text-muted-foreground">SGST</span>
                          <span className="text-foreground">₹{inr(detailChallan.total_sgst)}</span>
                        </div>
                      </>
                    )}
                    <div className="flex justify-between px-3 py-1.5 bg-muted/30">
                      <span className="text-foreground font-semibold">Grand Total</span>
                      <span className="text-foreground font-bold">₹{inr(detailChallan.grand_total)}</span>
                    </div>
                  </div>
                </div>
              )}
              <div className="text-[10px] text-muted-foreground font-mono">
                GST shown for reference / ITC-04 only — no tax is charged on goods sent under CGST §143.
              </div>

              {detailChallan.notes && (
                <div className="font-mono text-xs"><span className="text-muted-foreground">Notes:</span> <span className="text-foreground">{detailChallan.notes}</span></div>
              )}

              {!editable && (
                <div className="flex items-start gap-1.5 text-[11px] text-amber-400 font-mono">
                  <AlertTriangle className="w-3.5 h-3.5 mt-px flex-shrink-0" />
                  {detailReceiptCount > 0
                    ? "This challan has material receipts logged and can no longer be edited."
                    : `Only PENDING challans can be edited (current status: ${detailChallan.status}).`}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <SecondaryButton onClick={() => setDetailChallan(null)}>Close</SecondaryButton>
                <SecondaryButton
                  icon={Download}
                  disabled={pdfBusy}
                  testid={`challan-pdf-${detailChallan.id}`}
                  onClick={() => downloadChallanPdf(
                    `/job-work/challans/${detailChallan.id}/pdf`,
                    `${detailChallan.challan_number}.pdf`,
                    detailChallan.id,
                  )}
                >
                  Download PDF
                </SecondaryButton>
                {editable && (
                  <PrimaryButton icon={PencilLine} onClick={() => openEditChallan(detailChallan)}>Edit Challan</PrimaryButton>
                )}
              </div>
            </div>
          );
        })()}
      </Modal>

      <BulkDeleteBar
        count={tab === "challans" ? sel.count : 0}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={handleBulkDelete}
        noun="challan"
      />
      <BulkDeleteBar
        count={tab === "receipts" ? receiptSel.count : 0}
        deleting={receiptSel.deleting}
        onClear={receiptSel.clear}
        onDelete={handleBulkDeleteReceipts}
        noun="receipt"
      />

      {/* ── Modal: Receipt Detail (read-only) ──────────────────────────────────── */}
      <Modal
        open={!!detailReceipt}
        onClose={() => setDetailReceipt(null)}
        title={detailReceipt ? `Receipt ${detailReceipt.receipt_number}` : "Receipt"}
      >
        {detailReceipt && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3 font-mono text-xs">
              <div><span className="text-muted-foreground">Receipt Date:</span> <span className="text-foreground">{detailReceipt.date || "—"}</span></div>
              <div><span className="text-muted-foreground">Challan No:</span> <span className="text-foreground">{detailReceipt.challan_number || "—"}</span></div>
            </div>
            <div className="border border-border overflow-x-auto rounded-md">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                    <th className="p-2.5 uppercase">Product</th>
                    <th className="p-2.5 uppercase text-right">Received</th>
                    <th className="p-2.5 uppercase text-right">Scrap</th>
                  </tr>
                </thead>
                <tbody>
                  {detailReceipt.items?.map((it, i) => (
                    <tr key={it.product_id || `dr-${i}`} className="border-b border-border">
                      <td className="p-2.5 text-foreground">{it.product_name}</td>
                      <td className="p-2.5 text-right text-foreground">{it.quantity_received}</td>
                      <td className="p-2.5 text-right text-muted-foreground">{it.scrap_quantity || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {detailReceipt.notes && (
              <div className="font-mono text-xs"><span className="text-muted-foreground">Notes:</span> <span className="text-foreground">{detailReceipt.notes}</span></div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <SecondaryButton onClick={() => setDetailReceipt(null)}>Close</SecondaryButton>
              <SecondaryButton
                icon={Download}
                disabled={receiptPdfBusy}
                onClick={() => downloadReceiptPdf(
                  `/job-work/receipts/${detailReceipt.id}/pdf`,
                  `${detailReceipt.receipt_number}.pdf`,
                  detailReceipt.id,
                )}
              >
                Download PDF
              </SecondaryButton>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
