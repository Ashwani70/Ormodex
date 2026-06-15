import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Bell, X, Package, Receipt, AlertTriangle, TrendingUp, CheckCircle } from "lucide-react";

const TYPE_CONFIG = {
  LOW_STOCK_ALERT: { icon: Package, color: "text-orange-400", bg: "border-orange-800/40 bg-orange-950/20", label: "Inventory" },
  UNPAID_INVOICES: { icon: Receipt, color: "text-red-400", bg: "border-red-800/40 bg-red-950/20", label: "Finance" },
  PENDING_APPROVALS: { icon: AlertTriangle, color: "text-yellow-400", bg: "border-yellow-800/40 bg-yellow-950/20", label: "Approvals" },
  SALES_SUMMARY: { icon: TrendingUp, color: "text-green-400", bg: "border-green-800/40 bg-green-950/20", label: "Sales" },
  TOP_CUSTOMER: { icon: TrendingUp, color: "text-blue-400", bg: "border-blue-800/40 bg-blue-950/20", label: "CRM" },
};

const TYPE_ROUTES = {
  LOW_STOCK_ALERT: "/products",
  UNPAID_INVOICES: "/invoices",
  PENDING_APPROVALS: "/expenses",
  SALES_SUMMARY: "/mis-reports",
  TOP_CUSTOMER: "/customers",
};

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export default function NotificationPanel() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [read, setRead] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const panelRef = useRef(null);
  const navigate = useNavigate();

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Load notifications from business insights
  const loadNotifications = async () => {
    setLoading(true);
    try {
      const r = await api.get("/ai/business-insights");
      const items = (r.data.insights || []).map((ins, idx) => ({
        id: idx,
        type: ins.type,
        title: ins.title,
        value: ins.value,
        count: ins.count,
        name: ins.name,
        priority: ins.priority,
        timestamp: new Date(),
      }));
      setNotifications(items);
    } catch (e) {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotifications();
    // Refresh every 5 minutes
    const interval = setInterval(loadNotifications, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const unreadCount = notifications.filter(n => !read.has(n.id)).length;

  const markAllRead = () => {
    setRead(new Set(notifications.map(n => n.id)));
  };

  const handleClick = (notif) => {
    setRead(prev => new Set([...prev, notif.id]));
    const route = TYPE_ROUTES[notif.type];
    if (route) {
      navigate(route);
      setOpen(false);
    }
  };

  const formatValue = (notif) => {
    if (notif.type === "LOW_STOCK_ALERT" || notif.type === "PENDING_APPROVALS") {
      return `${notif.value} item${notif.value !== 1 ? "s" : ""}`;
    }
    if (typeof notif.value === "number" && notif.value > 1000) {
      return `₹${inr(notif.value)}`;
    }
    return notif.name || notif.value;
  };

  return (
    <div className="relative" ref={panelRef}>
      {/* Bell button */}
      <button
        onClick={() => { setOpen(!open); if (!open) loadNotifications(); }}
        className="relative p-2 text-zinc-400 hover:text-yellow-400 transition-colors border border-transparent hover:border-zinc-700"
        title="Notifications"
        id="notifications-bell"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[8px] font-bold rounded-full flex items-center justify-center leading-none">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 top-10 z-50 w-80 bg-zinc-950 border border-zinc-700 shadow-2xl shadow-black/50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-black">
            <div className="flex items-center gap-2">
              <Bell className="w-3.5 h-3.5 text-yellow-400" />
              <span className="text-sm font-semibold text-white">Notifications</span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 bg-red-500/20 border border-red-500/40 text-red-400 text-[9px] font-mono">
                  {unreadCount} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="text-[9px] font-mono text-zinc-500 hover:text-yellow-400 px-2 py-1 transition-colors"
                >
                  Mark all read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-zinc-600 hover:text-white transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <div className="px-4 py-6 text-center">
                <div className="w-5 h-5 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <span className="text-xs text-zinc-500 font-mono">Loading...</span>
              </div>
            ) : notifications.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <CheckCircle className="w-8 h-8 text-green-500 mx-auto mb-2 opacity-60" />
                <div className="text-sm text-zinc-500">All caught up!</div>
                <div className="text-xs text-zinc-700 mt-1 font-mono">No alerts at this time</div>
              </div>
            ) : (
              notifications.map((notif) => {
                const cfg = TYPE_CONFIG[notif.type] || TYPE_CONFIG.SALES_SUMMARY;
                const Icon = cfg.icon;
                const isRead = read.has(notif.id);
                return (
                  <button
                    key={notif.id}
                    onClick={() => handleClick(notif)}
                    className={`w-full text-left flex items-start gap-3 px-4 py-3 border-b border-zinc-900 hover:bg-zinc-900 transition-colors ${
                      isRead ? "opacity-60" : ""
                    }`}
                  >
                    <div className={`w-7 h-7 flex items-center justify-center flex-shrink-0 border ${cfg.bg} mt-0.5`}>
                      <Icon className={`w-3.5 h-3.5 ${cfg.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-white truncate">{notif.title}</span>
                        {!isRead && <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full flex-shrink-0" />}
                      </div>
                      <div className={`text-xs font-bold mt-0.5 ${cfg.color}`}>{formatValue(notif)}</div>
                      <div className="text-[9px] font-mono text-zinc-600 mt-0.5 uppercase tracking-wider">
                        {cfg.label} • Click to view
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-zinc-800 bg-black">
            <button
              onClick={() => { loadNotifications(); }}
              className="text-[9px] font-mono text-zinc-600 hover:text-yellow-400 uppercase tracking-wider transition-colors"
            >
              ↻ Refresh alerts
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
