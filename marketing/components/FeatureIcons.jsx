import React from "react";

// ── 1. Sales & CRM ──────────────────────────────────────────────────────────
export function SalesCrmIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="salesGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      {/* Background soft circle */}
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Funnel/Pipeline chart */}
      <path d="M12 14C12 13.4477 12.4477 13 13 13H35C35.5523 13 36 13.4477 36 14V17C36 17.3916 35.7712 17.747 35.4142 17.9098L27 21.75V31.5L21 34.5V21.75L12.5858 17.9098C12.2288 17.747 12 17.3916 12 17V14Z" fill="url(#salesGrad)" />
      {/* Users nodes connected */}
      <circle cx="34" cy="30" r="4" fill="#263238" stroke="#FFFFFF" strokeWidth="1.5" />
      <circle cx="14" cy="32" r="3" fill="#263238" stroke="#FFFFFF" strokeWidth="1.5" />
      {/* Connections */}
      <path d="M30 30H27M17 32H21" stroke="#263238" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ── 2. Purchase Management ──────────────────────────────────────────────────
export function PurchaseIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="purchaseGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#3D9140" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Purchase Document */}
      <rect x="14" y="11" width="20" height="26" rx="2" fill="url(#purchaseGrad)" />
      {/* Lines on doc */}
      <line x1="18" y1="17" x2="30" y2="17" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
      <line x1="18" y1="23" x2="26" y2="23" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
      <line x1="18" y1="29" x2="24" y2="29" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
      {/* Cart/Check overlay */}
      <circle cx="31" cy="31" r="7" fill="#263238" stroke="#FFFFFF" strokeWidth="1.5" />
      <path d="M28.5 31L30 32.5L33.5 29" stroke="#4CAF4F" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── 3. Inventory & Warehouse ────────────────────────────────────────────────
export function InventoryIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="invGrad1" x1="24" y1="10" x2="24" y2="38" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Isometric boxes */}
      {/* Box 1 (Bottom Left) */}
      <path d="M12 28L20 24L28 28L20 32L12 28Z" fill="#263238" />
      <path d="M12 28V34L20 38V32L12 28Z" fill="#37474F" />
      <path d="M20 32V38L28 34V28L20 32Z" fill="#455A64" />
      
      {/* Box 2 (Bottom Right) */}
      <path d="M22 21L30 17L38 21L30 25L22 21Z" fill="#7AC77B" />
      <path d="M22 21V27L30 31V25L22 21Z" fill="#4CAF4F" />
      <path d="M30 25V31L38 27V21L30 25Z" fill="#3D9140" />

      {/* Box 3 (Top / Stacked) */}
      <path d="M17 17L25 13L33 17L25 21L17 17Z" fill="url(#invGrad1)" />
      <path d="M17 17V23L25 27V21L17 17Z" fill="#4CAF4F" opacity="0.9" />
      <path d="M25 21V27L33 23V17L25 21Z" fill="#3D9140" opacity="0.9" />
    </svg>
  );
}

// ── 4. Production Planning ──────────────────────────────────────────────────
export function ProductionIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="prodGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Gear 1 (Large) */}
      <g transform="translate(20, 20)">
        <circle r="8" fill="url(#prodGrad)" />
        <circle r="4" fill="#E8F5E9" />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
          <rect key={angle} x="-2" y="-11" width="4" height="4" rx="1" fill="url(#prodGrad)" transform={`rotate(${angle})`} />
        ))}
      </g>
      {/* Gear 2 (Small, Interlocking) */}
      <g transform="translate(32, 30)">
        <circle r="5" fill="#263238" />
        <circle r="2.5" fill="#E8F5E9" />
        {[22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5].map((angle) => (
          <rect key={angle} x="-1.5" y="-7" width="3" height="3" rx="0.5" fill="#263238" transform={`rotate(${angle})`} />
        ))}
      </g>
      {/* Routing path/connection */}
      <path d="M12 34C12 28 16 26 20 26" stroke="#263238" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 3" />
      <circle cx="12" cy="34" r="2.5" fill="#263238" />
    </svg>
  );
}

// ── 5. Accounting & GST ─────────────────────────────────────────────────────
export function AccountingGstIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="accGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Balance Scale */}
      <path d="M14 34H34M24 14V34" stroke="#263238" strokeWidth="2" strokeLinecap="round" />
      {/* Center fulcrum */}
      <path d="M20 14H28" stroke="#263238" strokeWidth="2" strokeLinecap="round" />
      {/* Left scale */}
      <path d="M20 14L16 23M16 23C13.5 23 13.5 27 16 27C18.5 27 18.5 23 16 23Z" fill="url(#accGrad)" stroke="#263238" strokeWidth="1.5" />
      {/* Right scale */}
      <path d="M28 14L32 21M32 21C29.5 21 29.5 25 32 25C34.5 25 34.5 21 32 21Z" fill="url(#accGrad)" stroke="#263238" strokeWidth="1.5" />
      {/* Rupees indicator in middle */}
      <circle cx="24" cy="32" r="5" fill="#263238" stroke="#FFFFFF" strokeWidth="1" />
      <path d="M22.5 30H25.5M22.5 32H25.5M24 30V34M22.5 34C24 34 25.5 33 25.5 32.5" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

// ── 6. e-Invoicing ──────────────────────────────────────────────────────────
export function EInvoicingIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="einvoiceGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#3D9140" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Invoice */}
      <rect x="13" y="11" width="22" height="26" rx="2" fill="url(#einvoiceGrad)" />
      <line x1="17" y1="16" x2="27" y2="16" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
      <line x1="17" y1="21" x2="25" y2="21" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
      {/* Digital QR/Scan glow */}
      <rect x="23" y="25" width="8" height="8" rx="1" fill="#263238" stroke="#FFFFFF" strokeWidth="1.5" />
      {/* Tiny scan marks */}
      <rect x="25" y="27" width="2" height="2" fill="#4CAF4F" />
      <rect x="28" y="29" width="1" height="2" fill="#4CAF4F" />
      {/* Digital Lightning/Speed */}
      <path d="M33 13L29 18H33L30 23" stroke="#263238" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── 7. e-Way Bill Integration ───────────────────────────────────────────────
export function EWayBillIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="ewayGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Delivery Truck */}
      {/* Wheels */}
      <circle cx="20" cy="31" r="3.5" fill="#263238" stroke="#FFFFFF" strokeWidth="1" />
      <circle cx="31" cy="31" r="3.5" fill="#263238" stroke="#FFFFFF" strokeWidth="1" />
      {/* Truck Body */}
      <path d="M14 20C14 18.8954 14.8954 18 16 18H28V31H14V20Z" fill="url(#ewayGrad)" />
      {/* Cabin */}
      <path d="M28 21H32.5C33.8 21 35 22.2 35 23.5V31H28V21Z" fill="#263238" />
      {/* Window */}
      <path d="M29 23H32C32.5 23 33 23.5 33 24V27H29V23Z" fill="#E8F5E9" />
      {/* Speed lines */}
      <line x1="9" y1="21" x2="12" y2="21" stroke="#4CAF4F" strokeWidth="2" strokeLinecap="round" />
      <line x1="7" y1="25" x2="11" y2="25" stroke="#4CAF4F" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

// ── 8. HR & Payroll ─────────────────────────────────────────────────────────
export function HrPayrollIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="hrGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Employee nodes */}
      <circle cx="18" cy="18" r="4.5" fill="#263238" />
      <path d="M12 28.5C12 25 15 24 18 24C21 24 24 25 24 28.5V31H12V28.5Z" fill="#263238" />

      <circle cx="29" cy="21" r="3.5" fill="url(#hrGrad)" />
      <path d="M24.5 29.5C24.5 26.5 27 26.0 29 26.0C31 26.0 33.5 26.5 33.5 29.5V31.5H24.5V29.5Z" fill="url(#hrGrad)" />

      {/* Floating Salary/Check indicator */}
      <circle cx="34" cy="16" r="5" fill="#7AC77B" stroke="#FFFFFF" strokeWidth="1.5" />
      <path d="M32.5 15.5H35.5M32.5 17H35.5M34 14.5V17.5" stroke="#FFFFFF" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

// ── 9. Analytics Dashboard ──────────────────────────────────────────────────
export function AnalyticsIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="analyticsGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#3D9140" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Dashboard Screen frame */}
      <rect x="12" y="14" width="24" height="18" rx="1.5" fill="#263238" />
      <rect x="14" y="16" width="20" height="11" fill="#FFFFFF" />
      {/* Stand */}
      <path d="M21 32H27L28 35H20L21 32Z" fill="#263238" />
      {/* Line Chart inside screen */}
      <path d="M15 25L18 21L21 23L25 18L28 20L33 17" stroke="url(#analyticsGrad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Mini Bar charts */}
      <rect x="15" y="29" width="3" height="1" fill="#7AC77B" />
      <rect x="19" y="29" width="3" height="2" fill="#7AC77B" />
      <rect x="23" y="29" width="3" height="1.5" fill="#7AC77B" />
    </svg>
  );
}

// ── 10. Role-Based Access ───────────────────────────────────────────────────
export function RbacIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="rbacGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#7AC77B" />
          <stop offset="100%" stopColor="#4CAF4F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#E8F5E9" />
      {/* Security Shield */}
      <path d="M24 12C28 12 33 13.5 33 13.5V23C33 28.5 24 33 24 33C24 33 15 28.5 15 23V13.5C15 13.5 20 12 24 12Z" fill="url(#rbacGrad)" stroke="#263238" strokeWidth="1.5" strokeLinejoin="round" />
      {/* Lock symbol inside shield */}
      <rect x="20" y="21" width="8" height="6" rx="1" fill="#263238" />
      <path d="M22 21V19C22 17.8954 22.8954 17 24 17C25.1046 17 26 17.8954 26 19V21" stroke="#263238" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ── Map features to icons ──────────────────────────────────────────────────
export const FeatureIconMap = {
  "Sales & CRM": SalesCrmIcon,
  "Purchase Management": PurchaseIcon,
  "Inventory & Warehouse": InventoryIcon,
  "Production Planning": ProductionIcon,
  "Accounting & GST": AccountingGstIcon,
  "e-Invoicing": EInvoicingIcon,
  "e-Way Bill Integration": EWayBillIcon,
  "HR & Payroll": HrPayrollIcon,
  "Analytics Dashboard": AnalyticsIcon,
  "Role-Based Access": RbacIcon,
};
