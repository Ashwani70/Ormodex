import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import ForcePasswordChange from "@/components/ForcePasswordChange";
import SplashScreen from "@/components/SplashScreen";
import useIdleTimer from "@/hooks/useIdleTimer";
import { isAdminRole } from "@/lib/navItems";

const IDLE_TIMEOUT_MS = 20 * 60 * 1000; // spec: 15-30 min inactivity auto-logout

export default function ProtectedRoute({ children, adminOnly = false, allowedRoles, allowedPermission }) {
  const { user, loading, mustChangePassword, logout } = useAuth();

  useIdleTimer(() => { logout(); }, IDLE_TIMEOUT_MS, !!user);

  if (loading || user === null) {
    // Branded startup splash while the session is being restored.
    return <SplashScreen variant="splash" message="Initialising your workspace…" />;
  }
  if (!user) return <Navigate to="/login" replace />;
  // Block all protected content until a sub-policy password has been changed.
  if (mustChangePassword) return <ForcePasswordChange />;

  if (adminOnly && !isAdminRole(user.role)) return <Navigate to="/" replace />;

  // Role & module-permission check (admin bypasses all checks)
  if (!isAdminRole(user.role)) {
    if (allowedRoles || allowedPermission) {
      const hasRole = allowedRoles ? allowedRoles.includes(user.role) : false;
      const hasPermission = allowedPermission ? user.module_permissions?.includes(allowedPermission) : false;
      if (!hasRole && !hasPermission) {
        return <Navigate to="/" replace />;
      }
    }
  }

  return children;
}
