// Declarative config for the 10 master screens, rendered by <MasterScreen/>.
// Field types: text | number | select | checkbox | date | ref.
// `ref` populates a dropdown from another master endpoint (see refSources).
// `hidden(form)` conditionally hides a field; `render(row)` customises a column.

const yesNo = (key, label) => ({ key, label, render: (r) => (r[key] ? "Yes" : "—") });

export const MASTERS = {
  // ───────────── Accounting ─────────────
  groups: {
    title: "Account Groups", singular: "Group", eyebrow: "Accounting Masters",
    description: "Tree of accounting groups (Tally-style). Nature drives the financial statements.",
    endpoint: "/masters/groups",
    refSources: { groups: "/masters/groups" },
    columns: [
      { key: "name", label: "Name" },
      { key: "nature", label: "Nature" },
      { key: "parent_group_id", label: "Parent", render: (r, h) => r.parent_group_id ? h.refLabel("groups", r.parent_group_id) : "—" },
      yesNo("is_revenue", "Revenue"),
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "nature", label: "Nature", type: "select", required: true, options: ["Asset", "Liability", "Income", "Expense"] },
      { key: "parent_group_id", label: "Parent Group", type: "ref", ref: "groups", placeholder: "Top level" },
      { key: "is_primary", label: "Is Primary", type: "checkbox" },
      { key: "affects_gross_profit", label: "Affects Gross Profit", type: "checkbox" },
      { key: "is_revenue", label: "Is Revenue", type: "checkbox" },
    ],
  },

  ledgers: {
    title: "Ledgers", singular: "Ledger", eyebrow: "Accounting Masters",
    description: "Ledger accounts under a group, with GST / PAN / TDS attributes.",
    endpoint: "/masters/ledgers",
    refSources: { groups: "/masters/groups", products: "/products", coa: "/accounting/chart-of-accounts" },
    columns: [
      { key: "name", label: "Name" },
      { key: "group_id", label: "Group", render: (r, h) => h.refLabel("groups", r.group_id) },
      { key: "coa_account_id", label: "CoA Account", render: (r, h) => h.refLabel("coa", r.coa_account_id) },
      { key: "opening_balance", label: "Opening", render: (r) => `${r.opening_balance ?? 0} ${r.dr_cr || ""}` },
      { key: "gstin", label: "GSTIN" },
      { key: "product_id", label: "Linked Item", render: (r, h) => r.product_id ? h.refLabel("products", r.product_id) : (r.product_name_manual || "—") },
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "group_id", label: "Group", type: "ref", ref: "groups", required: true },
      { key: "coa_account_id", label: "Chart of Accounts Account", type: "ref", ref: "coa", required: true, renderOption: (a) => `${a.code} — ${a.name}`, hint: "Required so this ledger's postings can appear on Trial Balance / P&L / Balance Sheet" },
      { key: "opening_balance", label: "Opening Balance", type: "number" },
      { key: "dr_cr", label: "Dr / Cr", type: "select", options: ["Dr", "Cr"], default: "Dr" },
      { key: "gstin", label: "GSTIN", type: "text" },
      { key: "pan", label: "PAN", type: "text" },
      { key: "state", label: "State", type: "text" },
      { key: "gst_registration_type", label: "GST Reg. Type", type: "select", options: ["Regular", "Composition", "Unregistered", "Consumer", "SEZ", "Overseas"] },
      { key: "tds_applicable", label: "TDS Applicable", type: "checkbox" },
      { key: "product_id", label: "Link to Item / Product (optional)", type: "ref", ref: "products", renderOption: (p) => p.sku ? `${p.name} (${p.sku})` : p.name, manualToggle: true, manualKey: "product_name_manual", manualPlaceholder: "Type item name manually…", hint: "Pick from inventory or type manually" },
    ],
  },

  currencies: {
    title: "Currencies", singular: "Currency", eyebrow: "Accounting Masters",
    description: "Currencies used across the books. Exactly one base currency per tenant.",
    endpoint: "/masters/currencies",
    columns: [
      { key: "iso_code", label: "ISO" },
      { key: "symbol", label: "Symbol" },
      { key: "formal_name", label: "Name" },
      { key: "decimal_places", label: "Decimals" },
      yesNo("is_base_currency", "Base"),
    ],
    fields: [
      // Searchable currency picker: selecting a currency auto-fills the fields
      // below. ISO Code is required and must be unique (backend enforces too).
      { key: "iso_code", label: "ISO Code", type: "currency-picker", required: true, unique: true },
      { key: "symbol", label: "Symbol", type: "text", required: true, placeholder: "₹", readOnly: true },
      { key: "formal_name", label: "Formal Name", type: "text", required: true, readOnly: true },
      { key: "decimal_places", label: "Decimal Places", type: "number", default: 2, step: "1", readOnly: true, nonNegativeInt: true },
      { key: "is_base_currency", label: "Is Base Currency", type: "checkbox" },
    ],
  },

  rates: {
    title: "Rates of Exchange", singular: "Rate", eyebrow: "Accounting Masters",
    description: "Dated exchange rates per currency (standard / selling / buying).",
    endpoint: "/masters/rates",
    refSources: { currencies: "/masters/currencies" },
    columns: [
      { key: "currency_id", label: "Currency", render: (r, h) => h.refLabel("currencies", r.currency_id) },
      { key: "effective_date", label: "Effective" },
      { key: "std_rate", label: "Std Rate" },
      { key: "selling_rate", label: "Selling" },
      { key: "buying_rate", label: "Buying" },
    ],
    fields: [
      { key: "currency_id", label: "Currency", type: "ref", ref: "currencies", required: true },
      { key: "effective_date", label: "Effective Date", type: "date", required: true },
      { key: "std_rate", label: "Standard Rate", type: "number", required: true },
      { key: "selling_rate", label: "Selling Rate", type: "number" },
      { key: "buying_rate", label: "Buying Rate", type: "number" },
    ],
  },

  "voucher-types": {
    title: "Voucher Types", singular: "Voucher Type", eyebrow: "Accounting Masters",
    description: "Configure voucher numbering, prefixes and print options.",
    endpoint: "/masters/voucher-types",
    columns: [
      { key: "name", label: "Name" },
      { key: "parent_type", label: "Parent Type" },
      { key: "numbering_method", label: "Numbering" },
      { key: "prefix", label: "Prefix" },
      yesNo("is_active", "Active"),
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "parent_type", label: "Parent Type", type: "select", required: true, options: [
        "Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note",
        "Stock Journal", "Physical Stock", "Delivery Note", "Receipt Note", "Sales Order",
        "Purchase Order", "Quotation", "Job Work", "Memorandum", "Reversing Journal", "Payroll", "Attendance",
      ] },
      { key: "numbering_method", label: "Numbering Method", type: "select", options: ["auto", "manual", "none"], default: "auto" },
      { key: "prefix", label: "Prefix", type: "text" },
      { key: "suffix", label: "Suffix", type: "text" },
      { key: "restart_rule", label: "Restart Rule", type: "select", options: ["never", "yearly", "monthly"], default: "yearly" },
      { key: "use_effective_date", label: "Use Effective Date", type: "checkbox" },
      { key: "is_active", label: "Active", type: "checkbox", default: true },
    ],
  },

  // ───────────── Inventory ─────────────
  "stock-groups": {
    title: "Stock Groups", singular: "Stock Group", eyebrow: "Inventory Masters",
    description: "Tree of stock groups. 'Add quantities' controls qty rollups.",
    endpoint: "/masters/stock-groups",
    refSources: { "stock-groups": "/masters/stock-groups" },
    columns: [
      { key: "name", label: "Name" },
      { key: "parent_group_id", label: "Parent", render: (r, h) => r.parent_group_id ? h.refLabel("stock-groups", r.parent_group_id) : "—" },
      yesNo("add_quantities", "Add Qty"),
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "parent_group_id", label: "Parent Group", type: "ref", ref: "stock-groups", placeholder: "Top level" },
      { key: "add_quantities", label: "Add Quantities", type: "checkbox", default: true },
    ],
  },

  "stock-categories": {
    title: "Stock Categories", singular: "Stock Category", eyebrow: "Inventory Masters",
    description: "Tree of stock categories (cross-cuts stock groups).",
    endpoint: "/masters/stock-categories",
    refSources: { "stock-categories": "/masters/stock-categories" },
    columns: [
      { key: "name", label: "Name" },
      { key: "parent_category_id", label: "Parent", render: (r, h) => r.parent_category_id ? h.refLabel("stock-categories", r.parent_category_id) : "—" },
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "parent_category_id", label: "Parent Category", type: "ref", ref: "stock-categories", placeholder: "Top level" },
    ],
  },

  units: {
    title: "Units of Measure", singular: "Unit", eyebrow: "Inventory Masters",
    description: "Simple and compound units. Compound units convert to a base unit.",
    endpoint: "/masters/units",
    refSources: { units: "/masters/units" },
    columns: [
      { key: "symbol", label: "Symbol" },
      { key: "formal_name", label: "Name" },
      { key: "type", label: "Type" },
      { key: "base_unit_id", label: "Base Unit", render: (r, h) => r.base_unit_id ? h.refLabel("units", r.base_unit_id) : "—" },
    ],
    fields: [
      { key: "symbol", label: "Symbol", type: "text", required: true, placeholder: "kg" },
      { key: "formal_name", label: "Formal Name", type: "text", required: true },
      { key: "decimal_places", label: "Decimal Places", type: "number", default: 2, step: "1" },
      { key: "type", label: "Type", type: "select", options: ["simple", "compound"], default: "simple" },
      { key: "base_unit_id", label: "Base Unit", type: "ref", ref: "units", hidden: (f) => f.type !== "compound", required: true },
      { key: "conversion_factor", label: "Conversion Factor", type: "number", hidden: (f) => f.type !== "compound", required: true },
    ],
  },

  "stock-items": {
    title: "Stock Items", singular: "Stock Item", eyebrow: "Inventory Masters",
    description: "Item master with HSN/SAC, GST, valuation method and batch/serial tracking.",
    endpoint: "/masters/stock-items",
    refSources: {
      "stock-groups": "/masters/stock-groups",
      "stock-categories": "/masters/stock-categories",
      units: "/masters/units",
    },
    columns: [
      { key: "name", label: "Name" },
      { key: "hsn_sac", label: "HSN/SAC" },
      { key: "gst_rate", label: "GST %" },
      { key: "valuation_method", label: "Valuation" },
      { key: "base_unit_id", label: "Unit", render: (r, h) => h.refLabel("units", r.base_unit_id) },
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "base_unit_id", label: "Base Unit", type: "ref", ref: "units", required: true },
      { key: "stock_group_id", label: "Stock Group", type: "ref", ref: "stock-groups" },
      { key: "category_id", label: "Category", type: "ref", ref: "stock-categories" },
      { key: "hsn_sac", label: "HSN / SAC", type: "text" },
      { key: "gst_rate", label: "GST Rate %", type: "number" },
      { key: "opening_qty", label: "Opening Qty", type: "number" },
      { key: "opening_rate", label: "Opening Rate", type: "number" },
      { key: "valuation_method", label: "Valuation Method", type: "select", options: ["FIFO", "Avg", "LIFO", "Std"], default: "Avg" },
      { key: "reorder_level", label: "Reorder Level", type: "number" },
      { key: "batch_enabled", label: "Batch Tracking", type: "checkbox" },
      { key: "serial_enabled", label: "Serial Tracking", type: "checkbox" },
    ],
  },

  locations: {
    title: "Locations / Warehouses", singular: "Location", eyebrow: "Inventory Masters",
    description: "Tree of storage locations. Flags for negative stock and third-party warehouses.",
    endpoint: "/masters/locations",
    refSources: { locations: "/masters/locations" },
    columns: [
      { key: "name", label: "Name" },
      { key: "parent_location_id", label: "Parent", render: (r, h) => r.parent_location_id ? h.refLabel("locations", r.parent_location_id) : "—" },
      yesNo("allow_negative_stock", "Neg. Stock"),
      yesNo("is_third_party", "3rd Party"),
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "parent_location_id", label: "Parent Location", type: "ref", ref: "locations", placeholder: "Top level" },
      { key: "allow_negative_stock", label: "Allow Negative Stock", type: "checkbox" },
      { key: "is_third_party", label: "Third-Party Location", type: "checkbox" },
    ],
  },

  // ───────────── Statutory (list) ─────────────
  "gst-registrations": {
    title: "GST Registrations", singular: "GST Registration", eyebrow: "Statutory Masters",
    description: "GSTINs the business is registered under, with e-invoice / e-way applicability.",
    endpoint: "/masters/gst-registrations",
    columns: [
      { key: "gstin", label: "GSTIN" },
      { key: "registration_type", label: "Type" },
      { key: "state", label: "State" },
      { key: "periodicity", label: "Periodicity" },
      yesNo("e_invoice_applicable", "E-Invoice"),
    ],
    fields: [
      { key: "gstin", label: "GSTIN", type: "text", required: true, placeholder: "15-digit GSTIN" },
      { key: "registration_type", label: "Registration Type", type: "select", required: true, options: ["Regular", "Composition", "SEZ", "Unregistered"] },
      { key: "state", label: "State", type: "text" },
      { key: "periodicity", label: "Filing Periodicity", type: "select", options: ["Monthly", "Quarterly"], default: "Monthly" },
      { key: "e_invoice_applicable", label: "E-Invoice Applicable", type: "checkbox" },
      { key: "e_way_applicable", label: "E-Way Bill Applicable", type: "checkbox" },
    ],
  },

  "gst-classifications": {
    title: "GST Classifications", singular: "GST Classification", eyebrow: "Statutory Masters",
    description: "HSN/SAC tax classifications with IGST / CGST / SGST / Cess rates.",
    endpoint: "/masters/gst-classifications",
    columns: [
      { key: "name", label: "Name" },
      { key: "hsn_sac", label: "HSN/SAC" },
      { key: "taxability", label: "Taxability" },
      { key: "igst_rate", label: "IGST %" },
      yesNo("is_reverse_charge", "RCM"),
    ],
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "hsn_sac", label: "HSN / SAC", type: "text", required: true },
      { key: "taxability", label: "Taxability", type: "select", options: ["Taxable", "Exempt", "Nil Rated", "Non-GST"], default: "Taxable" },
      { key: "igst_rate", label: "IGST %", type: "number" },
      { key: "cgst_rate", label: "CGST %", type: "number" },
      { key: "sgst_rate", label: "SGST %", type: "number" },
      { key: "cess_rate", label: "Cess %", type: "number" },
      { key: "is_reverse_charge", label: "Reverse Charge", type: "checkbox" },
    ],
  },

  "tds-nature-of-payment": {
    title: "TDS Nature of Payment", singular: "TDS Section", eyebrow: "Statutory Masters",
    description: "TDS sections with thresholds and rates (with / without PAN).",
    endpoint: "/masters/tds-nature-of-payment",
    columns: [
      { key: "section_code", label: "Section" },
      { key: "description", label: "Description" },
      { key: "threshold", label: "Threshold" },
      { key: "rate_with_pan", label: "Rate (PAN)" },
      { key: "rate_without_pan", label: "Rate (No PAN)" },
    ],
    fields: [
      { key: "section_code", label: "Section Code", type: "text", required: true, placeholder: "194C" },
      { key: "description", label: "Description", type: "text", required: true, fullWidth: true },
      { key: "threshold", label: "Threshold", type: "number" },
      { key: "rate_with_pan", label: "Rate with PAN %", type: "number" },
      { key: "rate_without_pan", label: "Rate without PAN %", type: "number", default: 20 },
      { key: "surcharge", label: "Surcharge %", type: "number" },
      { key: "cess", label: "Cess %", type: "number" },
    ],
  },

  "tcs-nature-of-goods": {
    title: "TCS Nature of Goods", singular: "TCS Nature", eyebrow: "Statutory Masters",
    description: "TCS natures of goods with collection rate and threshold.",
    endpoint: "/masters/tcs-nature-of-goods",
    columns: [
      { key: "nature_code", label: "Code" },
      { key: "description", label: "Description" },
      { key: "rate", label: "Rate %" },
      { key: "threshold", label: "Threshold" },
    ],
    fields: [
      { key: "nature_code", label: "Nature Code", type: "text", required: true, placeholder: "6CE" },
      { key: "description", label: "Description", type: "text", required: true, fullWidth: true },
      { key: "rate", label: "Rate %", type: "number" },
      { key: "threshold", label: "Threshold", type: "number" },
    ],
  },
};

// Singleton statutory details (one doc per tenant — get + upsert only).
// Rendered by <SingletonMaster/> (no list, single form).
export const SINGLETONS = {
  "company-gst-details": {
    title: "Company GST Details", eyebrow: "Statutory Details",
    description: "The company's own GST registration profile.",
    endpoint: "/masters/company-gst-details",
    fields: [
      { key: "gstin", label: "GSTIN", type: "text" },
      { key: "legal_name", label: "Legal Name", type: "text" },
      { key: "trade_name", label: "Trade Name", type: "text" },
      { key: "registration_type", label: "Registration Type", type: "select", options: ["Regular", "Composition", "SEZ", "Unregistered"] },
      { key: "state", label: "State", type: "text" },
      { key: "state_code", label: "State Code", type: "text" },
      { key: "periodicity", label: "Filing Periodicity", type: "select", options: ["Monthly", "Quarterly"] },
      { key: "gst_username", label: "GST Portal Username", type: "text" },
      { key: "e_invoice_applicable", label: "E-Invoice Applicable", type: "checkbox" },
      { key: "e_way_applicable", label: "E-Way Bill Applicable", type: "checkbox" },
    ],
  },
  "tds-details": {
    title: "TDS Details", eyebrow: "Statutory Details",
    description: "Deductor TAN and responsible-person details for TDS returns.",
    endpoint: "/masters/tds-details",
    fields: [
      { key: "tan", label: "TAN", type: "text" },
      { key: "deductor_type", label: "Deductor Type", type: "text" },
      { key: "responsible_person_name", label: "Responsible Person", type: "text" },
      { key: "responsible_person_pan", label: "Responsible Person PAN", type: "text" },
      { key: "responsible_person_designation", label: "Designation", type: "text" },
    ],
  },
  "tcs-details": {
    title: "TCS Details", eyebrow: "Statutory Details",
    description: "Collector TAN and responsible-person details for TCS returns.",
    endpoint: "/masters/tcs-details",
    fields: [
      { key: "tan", label: "TAN", type: "text" },
      { key: "collector_type", label: "Collector Type", type: "text" },
      { key: "responsible_person_name", label: "Responsible Person", type: "text" },
      { key: "responsible_person_pan", label: "Responsible Person PAN", type: "text" },
      { key: "responsible_person_designation", label: "Designation", type: "text" },
    ],
  },
  "pan-cin-details": {
    title: "PAN / CIN Details", eyebrow: "Statutory Details",
    description: "Company PAN, CIN, TAN and incorporation details.",
    endpoint: "/masters/pan-cin-details",
    fields: [
      { key: "pan", label: "PAN", type: "text" },
      { key: "cin", label: "CIN", type: "text" },
      { key: "tan", label: "TAN", type: "text" },
      { key: "company_type", label: "Company Type", type: "text" },
      { key: "incorporation_date", label: "Incorporation Date", type: "date" },
    ],
  },
};
