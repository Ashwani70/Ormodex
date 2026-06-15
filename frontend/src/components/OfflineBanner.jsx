import { WifiOff } from "lucide-react";

// Inline banner shown on online-only screens when the browser is offline.
// Writes are disabled while this is visible (see each screen's submit guard).
export default function OfflineBanner({ online }) {
  if (online) return null;
  return (
    <div
      data-testid="offline-banner"
      className="mb-4 flex items-center gap-2 border border-red-900 bg-red-950/40 text-red-300 font-mono text-xs px-3 py-2"
      style={{ borderRadius: "var(--radius)" }}
    >
      <WifiOff className="w-4 h-4" />
      Offline — viewing cached data only. Saving is disabled until you reconnect.
    </div>
  );
}
