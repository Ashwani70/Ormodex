import { useCallback, useRef, useState } from "react";
import api from "@/lib/api";

// Resolves batch/serial/expiry tracking flags for products via the backend
// (/inventory/v2/tracking-flags), which reads them from the linked stock_item —
// the source of truth. Flags are cached per product_id so re-selecting the same
// product doesn't re-fetch. Returns { flagsByProduct, ensureFlags } where
// ensureFlags(ids) fetches any not-yet-known ids and resolves to the merged map.
//
// A flag object is { track_batch, track_serial, track_expiry }. Unknown products
// default to all-false (no extra fields shown/required).

export const NO_FLAGS = { track_batch: false, track_serial: false, track_expiry: false };

export default function useTrackingFlags() {
  const [flagsByProduct, setFlagsByProduct] = useState({});
  // Ref mirror so ensureFlags can dedupe without depending on render state.
  const knownRef = useRef({});

  const ensureFlags = useCallback(async (productIds) => {
    const ids = [...new Set((productIds || []).filter(Boolean))];
    const missing = ids.filter((id) => !(id in knownRef.current));
    if (missing.length === 0) return knownRef.current;
    try {
      const { data } = await api.post("/inventory/v2/tracking-flags", { product_ids: missing });
      const fetched = data?.products || {};
      const merged = { ...knownRef.current };
      for (const id of missing) merged[id] = fetched[id] || NO_FLAGS;
      knownRef.current = merged;
      setFlagsByProduct(merged);
      return merged;
    } catch {
      // On failure, treat the missing ids as untracked so the form stays usable;
      // the server still enforces the real rules on submit.
      const merged = { ...knownRef.current };
      for (const id of missing) merged[id] = NO_FLAGS;
      knownRef.current = merged;
      setFlagsByProduct(merged);
      return merged;
    }
  }, []);

  const flagsFor = useCallback(
    (productId) => flagsByProduct[productId] || NO_FLAGS,
    [flagsByProduct],
  );

  return { flagsByProduct, ensureFlags, flagsFor };
}
