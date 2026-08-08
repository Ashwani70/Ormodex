// Standard Unit of Measure (UOM) catalogue, shared by every voucher line-item
// table (Purchase Orders, GRNs, Purchase Bills, Sales Orders, Invoices, Credit
// Notes, Purchase Returns, Job Work) and the New Product form.
//
// This mirrors backend/routers/inventory.py's STANDARD_UOMS exactly — keep
// the two lists in sync. The live `/api/inventory/uoms` endpoint returns this
// same standard list plus any custom UOMs a user has created, so pages that
// can fetch it at load time should prefer that over this static fallback.

export const STANDARD_UOMS = [
  "Nos", "Pcs", "Kg", "Gram", "Meter", "Feet", "Inch",
  "Litre", "Box", "Bundle", "Pair", "Roll", "Set", "Bag", "Ton",
];

export const DEFAULT_UOM = "Nos";
