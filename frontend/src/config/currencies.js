// Predefined currency catalogue for the Currency Master picker.
//
// Shape: { code, name, symbol, decimals }. The picker fills the Currency master
// fields (iso_code / symbol / formal_name / decimal_places) from a selection.
//
// This is intentionally a plain data file so it can be expanded to the full
// ISO 4217 set later (or sourced from a backend endpoint) without touching the
// component. The first block is the spec's required set; more common currencies
// follow to show the list scales.

export const CURRENCIES = [
  { code: "INR", name: "Indian Rupee", symbol: "₹", decimals: 2 },
  { code: "USD", name: "US Dollar", symbol: "$", decimals: 2 },
  { code: "AED", name: "UAE Dirham", symbol: "د.إ", decimals: 2 },
  { code: "EUR", name: "Euro", symbol: "€", decimals: 2 },
  { code: "GBP", name: "British Pound", symbol: "£", decimals: 2 },
  { code: "JPY", name: "Japanese Yen", symbol: "¥", decimals: 0 },
  { code: "AUD", name: "Australian Dollar", symbol: "A$", decimals: 2 },
  { code: "CAD", name: "Canadian Dollar", symbol: "C$", decimals: 2 },
  { code: "SGD", name: "Singapore Dollar", symbol: "S$", decimals: 2 },
  // --- common additions (extend toward full ISO 4217 as needed) ---
  { code: "CHF", name: "Swiss Franc", symbol: "CHF", decimals: 2 },
  { code: "CNY", name: "Chinese Yuan", symbol: "¥", decimals: 2 },
  { code: "HKD", name: "Hong Kong Dollar", symbol: "HK$", decimals: 2 },
  { code: "NZD", name: "New Zealand Dollar", symbol: "NZ$", decimals: 2 },
  { code: "ZAR", name: "South African Rand", symbol: "R", decimals: 2 },
  { code: "SAR", name: "Saudi Riyal", symbol: "﷼", decimals: 2 },
  { code: "QAR", name: "Qatari Riyal", symbol: "﷼", decimals: 2 },
  { code: "KWD", name: "Kuwaiti Dinar", symbol: "د.ك", decimals: 3 },
  { code: "BHD", name: "Bahraini Dinar", symbol: ".د.ب", decimals: 3 },
  { code: "OMR", name: "Omani Rial", symbol: "﷼", decimals: 3 },
  { code: "MYR", name: "Malaysian Ringgit", symbol: "RM", decimals: 2 },
  { code: "THB", name: "Thai Baht", symbol: "฿", decimals: 2 },
  { code: "LKR", name: "Sri Lankan Rupee", symbol: "Rs", decimals: 2 },
  { code: "BDT", name: "Bangladeshi Taka", symbol: "৳", decimals: 2 },
  { code: "NPR", name: "Nepalese Rupee", symbol: "रू", decimals: 2 },
];

// Fast lookup by ISO code (case-insensitive callers should upper-case first).
export const CURRENCY_BY_CODE = Object.fromEntries(
  CURRENCIES.map((c) => [c.code, c])
);

// "INR — Indian Rupee (₹)" — the option label format from the spec.
export const formatCurrencyOption = (c) => `${c.code} — ${c.name} (${c.symbol})`;
