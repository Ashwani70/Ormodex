import React from "react";

// ── 1. Manual Spreadsheets (Broken/cracked sheet grid) ──────────────────────
export function SpreadsheetProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probSpreadsheetGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFA07A" />
          <stop offset="100%" stopColor="#FF4500" />
        </linearGradient>
      </defs>
      {/* Background circle */}
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Spreadsheet board */}
      <rect x="13" y="11" width="22" height="26" rx="2" fill="#FFFFFF" stroke="#263238" strokeWidth="1.5" />
      {/* Grid lines */}
      <line x1="13" y1="18" x2="35" y2="18" stroke="#263238" strokeWidth="1.2" />
      <line x1="13" y1="25" x2="35" y2="25" stroke="#263238" strokeWidth="1.2" />
      <line x1="13" y1="32" x2="35" y2="32" stroke="#263238" strokeWidth="1.2" />
      <line x1="20" y1="11" x2="20" y2="37" stroke="#263238" strokeWidth="1.2" />
      <line x1="28" y1="11" x2="28" y2="37" stroke="#263238" strokeWidth="1.2" />
      {/* Red crack/broken error line */}
      <path d="M12 28L18 22L24 29L31 20L36 24" stroke="url(#probSpreadsheetGrad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Error dot */}
      <circle cx="31" cy="20" r="2.5" fill="#FF4500" />
    </svg>
  );
}

// ── 2. Duplicate Data Entry (Redundant copy loops) ──────────────────────────
export function DuplicateDataProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probDuplicateGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FF8C00" />
          <stop offset="100%" stopColor="#E84A5F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Card 1 (Base) */}
      <rect x="14" y="16" width="16" height="20" rx="1.5" fill="#FFFFFF" stroke="#263238" strokeWidth="1.5" />
      <line x1="18" y1="21" x2="26" y2="21" stroke="#263238" strokeWidth="1.2" />
      <line x1="18" y1="26" x2="24" y2="26" stroke="#263238" strokeWidth="1.2" />
      
      {/* Card 2 (Duplicate Stacked) */}
      <rect x="20" y="12" width="16" height="20" rx="1.5" fill="#FFFFFF" stroke="url(#probDuplicateGrad)" strokeWidth="1.5" />
      <line x1="24" y1="17" x2="32" y2="17" stroke="url(#probDuplicateGrad)" strokeWidth="1.2" />
      <line x1="24" y1="22" x2="30" y2="22" stroke="url(#probDuplicateGrad)" strokeWidth="1.2" />

      {/* Redundancy double-arrow loop */}
      <path d="M14 13C12 16 11 20 13 23" stroke="#E84A5F" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M32 35C35 32 36 28 34 25" stroke="#E84A5F" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="13" cy="23" r="1.5" fill="#E84A5F" />
      <circle cx="34" cy="25" r="1.5" fill="#E84A5F" />
    </svg>
  );
}

// ── 3. Inventory Mismatches (Alert crate / broken scale) ────────────────────
export function InventoryMismatchProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probInventoryGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFA07A" />
          <stop offset="100%" stopColor="#E84A5F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Box Outlines */}
      <path d="M24 13L15 17.5V28.5L24 33L33 28.5V17.5L24 13Z" stroke="#263238" strokeWidth="1.5" strokeLinejoin="round" />
      {/* Isometric divisions */}
      <path d="M24 13V33" stroke="#263238" strokeWidth="1" strokeDasharray="2 2" />
      <path d="M15 17.5L24 22L33 17.5" stroke="#263238" strokeWidth="1.5" />
      {/* Red Mismatch Exclamation / Warning sign inside box */}
      <circle cx="24" cy="24" r="5" fill="url(#probInventoryGrad)" stroke="#FFFFFF" strokeWidth="1.5" />
      <line x1="24" y1="21.5" x2="24" y2="24" stroke="#FFFFFF" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="24" cy="26" r="0.6" fill="#FFFFFF" />
    </svg>
  );
}

// ── 4. Delayed Invoicing (Sand clock / running out time) ────────────────────
export function DelayedInvoicingProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probDelayGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFD700" />
          <stop offset="100%" stopColor="#FF4500" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Document outline */}
      <rect x="14" y="11" width="20" height="26" rx="1.5" fill="#FFFFFF" stroke="#263238" strokeWidth="1.5" />
      <line x1="18" y1="16" x2="26" y2="16" stroke="#263238" strokeWidth="1.2" />
      <line x1="18" y1="21" x2="24" y2="21" stroke="#263238" strokeWidth="1.2" />
      {/* Hourglass */}
      <g transform="translate(24, 27)">
        {/* Frame */}
        <path d="M-6 -7H6M-6 7H6" stroke="url(#probDelayGrad)" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M-5 -7L-1 0L-5 7" stroke="url(#probDelayGrad)" strokeWidth="1.5" />
        <path d="M5 -7L1 0L5 7" stroke="url(#probDelayGrad)" strokeWidth="1.5" />
        {/* Sand */}
        <path d="M-3.5 -5H3.5L1 -1H-1L-3.5 -5Z" fill="url(#probDelayGrad)" opacity="0.6" />
        <path d="M-1.5 2H1.5L3 5.5H-3L-1.5 2Z" fill="url(#probDelayGrad)" />
        {/* Falling drop */}
        <line x1="0" y1="-1" x2="0" y2="2" stroke="url(#probDelayGrad)" strokeWidth="1" strokeDasharray="1.5 1.5" />
      </g>
    </svg>
  );
}

// ── 5. GST Compliance Stress (Calendar deadline warning) ────────────────────
export function GstStressProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probGstGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFA07A" />
          <stop offset="100%" stopColor="#FF4500" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Calendar Grid */}
      <rect x="13" y="13" width="22" height="22" rx="2" fill="#FFFFFF" stroke="#263238" strokeWidth="1.5" />
      {/* Header bar of calendar */}
      <path d="M13 13H35V19H13V13Z" fill="#263238" />
      {/* Binder rings */}
      <rect x="17" y="10" width="2" height="5" rx="1" fill="#717171" />
      <rect x="29" y="10" width="2" height="5" rx="1" fill="#717171" />
      {/* Grid lines */}
      <line x1="13" y1="24" x2="35" y2="24" stroke="#717171" strokeWidth="1" />
      <line x1="13" y1="29" x2="35" y2="29" stroke="#717171" strokeWidth="1" />
      <line x1="19" y1="19" x2="19" y2="35" stroke="#717171" strokeWidth="1" />
      <line x1="25" y1="19" x2="25" y2="35" stroke="#717171" strokeWidth="1" />
      <line x1="30" y1="19" x2="30" y2="35" stroke="#717171" strokeWidth="1" />
      {/* Stressed deadline marker */}
      <circle cx="24" cy="24" r="7" fill="url(#probGstGrad)" stroke="#FFFFFF" strokeWidth="1.5" />
      <path d="M22 22L26 26M26 22L22 26" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ── 6. No Real-Time Reporting (Blurred monitor / sleep report) ──────────────
export function NoRealTimeProblemIcon({ className = "w-12 h-12" }) {
  return (
    <svg className={className} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="probRealTimeGrad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFA07A" />
          <stop offset="100%" stopColor="#E84A5F" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#FFF5F5" />
      {/* Monitor frame */}
      <rect x="12" y="14" width="24" height="18" rx="1.5" fill="#263238" />
      <rect x="14" y="16" width="20" height="11" fill="#FFFFFF" />
      {/* Stand */}
      <path d="M21 32H27L28 34H20L21 32Z" fill="#263238" />
      {/* Blurred / Late static data lines */}
      <line x1="16" y1="19" x2="24" y2="19" stroke="#717171" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
      <line x1="16" y1="23" x2="28" y2="23" stroke="#717171" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
      {/* Warning/Clock badge in corner */}
      <circle cx="28" cy="25" r="6.5" fill="url(#probRealTimeGrad)" stroke="#FFFFFF" strokeWidth="1.5" />
      {/* Clock hands showing late time */}
      <path d="M28 22V25H30" stroke="#FFFFFF" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

// ── Map problems to icons ──────────────────────────────────────────────────
export const ProblemIconMap = {
  "Manual spreadsheets": SpreadsheetProblemIcon,
  "Duplicate data entry": DuplicateDataProblemIcon,
  "Inventory mismatches": InventoryMismatchProblemIcon,
  "Delayed invoicing": DelayedInvoicingProblemIcon,
  "GST compliance stress": GstStressProblemIcon,
  "No real-time reporting": NoRealTimeProblemIcon,
};
