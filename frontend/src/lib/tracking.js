// Shared client-side mirror of the server's batch/serial/expiry tracking rules.
// The backend is the real enforcer; this just gives immediate feedback so the
// user isn't bounced by a 400. A flag object is
// { track_batch, track_serial, track_expiry } resolved from the linked stock_item.

const RULES = [
  ["track_batch", "batch_id", "Batch number"],
  ["track_serial", "serial_id", "Serial number"],
  ["track_expiry", "expiry_date", "Expiry date"],
];

const isBlank = (v) => v === undefined || v === null || (typeof v === "string" && v.trim() === "");

// Returns the labels of fields the line is missing given its flags, e.g.
// ["Batch number"]. Empty array means the line satisfies its tracking rules.
export function missingTrackingFields(line, flags) {
  if (!flags) return [];
  const out = [];
  for (const [flag, field, label] of RULES) {
    if (flags[flag] && isBlank(line[field])) out.push(label);
  }
  return out;
}
