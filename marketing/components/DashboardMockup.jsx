// Pure-CSS dark ERP dashboard mockup (no image asset needed). Rendered inside the
// ParallaxTilt in the hero for a 3D "floating product" effect. Swap for a real
// <Image/> screenshot when available.
export default function DashboardMockup() {
  const bars = [42, 66, 50, 82, 60, 92, 74, 58];
  return (
    <div className="glass-strong rounded-2xl p-3 shadow-card">
      {/* window chrome */}
      <div className="mb-3 flex items-center gap-1.5 px-1">
        <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-400/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-green-400/80" />
        <span className="ml-3 rounded bg-white/5 px-2 py-0.5 text-[10px] font-medium text-slate-400">
          app.gravityone.com/dashboard
        </span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {/* sidebar */}
        <div className="col-span-1 space-y-2 rounded-lg bg-ink/80 p-2.5">
          <div className="h-2 w-3/4 rounded bg-gradient-to-r from-primary-light to-accent" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className={`h-1.5 rounded ${i === 1 ? "bg-primary" : "bg-white/10"}`}
              style={{ width: `${58 + (i % 3) * 14}%` }}
            />
          ))}
        </div>
        {/* main */}
        <div className="col-span-3 space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {[
              ["Revenue", "₹48.2L", "text-accent"],
              ["Orders", "1,284", "text-primary-light"],
              ["Stock", "98.6%", "text-violet-light"],
            ].map(([k, v, c]) => (
              <div key={k} className="rounded-lg border border-white/5 bg-white/5 p-2.5">
                <div className="text-[9px] uppercase tracking-wide text-slate-500">{k}</div>
                <div className={`text-sm font-bold ${c}`}>{v}</div>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-white/5 bg-white/[0.03] p-3">
            <div className="mb-2 flex items-end justify-between gap-1.5" style={{ height: 92 }}>
              {bars.map((h, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-t bg-gradient-to-t from-primary to-accent"
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
            <div className="flex gap-2">
              <div className="h-1.5 w-1/2 rounded bg-white/10" />
              <div className="h-1.5 w-1/4 rounded bg-white/5" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
