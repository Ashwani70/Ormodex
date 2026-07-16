import { useCallback, useEffect, useRef, useState } from "react";
import {
  Image as ImageIcon, Building2, Hash, MapPin, Phone, Mail, Globe,
  Type, Trash2, AlignLeft, AlignCenter, AlignRight, GripVertical,
} from "lucide-react";

// ── Field blocks the user can drag onto the letterhead ─────────────────────────
// `value` is the PDF token the backend (_substitute_tokens in letterhead_pdf.py)
// replaces with live company data at render time. `type: "logo"` renders the
// template's uploaded logo. Keep tokens in sync with the backend mapping.
export const FIELD_BLOCKS = [
  { id: "logo",     label: "Company Logo", icon: ImageIcon, type: "logo",  value: "{logo}",            w_mm: 32, h_mm: 16, size: 10 },
  { id: "name",     label: "Company Name", icon: Building2, type: "text",  value: "{company_name}",    size: 16 },
  { id: "gstin",    label: "GST No.",      icon: Hash,      type: "text",  value: "GSTIN: {company_gstin}", size: 9 },
  { id: "address",  label: "Address",      icon: MapPin,    type: "text",  value: "{company_address}", size: 8 },
  { id: "phone",    label: "Phone No.",    icon: Phone,     type: "text",  value: "Ph: {company_phone}", size: 8 },
  { id: "email",    label: "Email ID",     icon: Mail,      type: "text",  value: "{company_email}",   size: 8 },
  { id: "website",  label: "Website",      icon: Globe,     type: "text",  value: "{company_website}", size: 8 },
  { id: "custom",   label: "Custom Text",  icon: Type,      type: "text",  value: "Custom text",       size: 10 },
];

// Human-readable preview of a token value (so the canvas shows real-ish text,
// not raw {tokens}). Falls back to the token label when company data is absent.
function previewText(el, company) {
  const c = company || {};
  const map = {
    "{company_name}": c.name || "Your Company Name",
    "{company_tagline}": c.tagline || "Company Tagline",
    "{company_gstin}": c.gstin || "00AAAAA0000A1Z0",
    "{company_pan}": c.pan || "AAAAA0000A",
    "{company_address}": c.address || "123 Business Street, City",
    "{company_phone}": c.phone || "+00 000 000 0000",
    "{company_email}": c.email || "hello@company.com",
    "{company_website}": c.website || "www.company.com",
  };
  let t = el.value || "";
  for (const [tok, val] of Object.entries(map)) t = t.split(tok).join(val);
  return t;
}

// A4 dimensions in mm (portrait). The canvas scales mm→px by a fixed factor.
const PAGE_MM = { A4: [210, 297], A4_landscape: [297, 210], letter: [216, 279] };
const PX_PER_MM = 2.6; // canvas render scale

/**
 * Visual drag-and-drop letterhead region editor.
 *
 * Renders an A4-proportioned canvas. Users click a field chip to add it, then
 * drag placed blocks to reposition. Positions are stored in millimetres
 * (x_mm/y_mm from the top-left of the page) so they map 1:1 to the ReportLab
 * PDF coordinate space the backend renders. `elements` are the raw element
 * dicts persisted to the template's header_elements / footer_elements.
 */
export default function DragDropCanvas({ pageSize = "A4", elements = [], onChange, company }) {
  const [w_mm, h_mm] = PAGE_MM[pageSize] || PAGE_MM.A4;
  const canvasRef = useRef(null);
  const [selected, setSelected] = useState(null); // index of selected element
  const dragRef = useRef(null); // { idx, offsetX_mm, offsetY_mm }

  const pxToMmX = useCallback((px) => px / PX_PER_MM, []);
  const pxToMmY = useCallback((px) => px / PX_PER_MM, []);

  const update = (idx, patch) => {
    const next = elements.map((el, i) => (i === idx ? { ...el, ...patch } : el));
    onChange(next);
  };

  const addBlock = (block) => {
    // Drop new blocks near the top-left inside the margin, staggered so they
    // don't stack exactly on top of one another.
    const offset = elements.length * 4;
    const el = {
      type: block.type,
      value: block.value,
      x_mm: Math.round(20 + offset),
      y_mm: Math.round(14 + offset),
      size: block.size || 10,
      color: block.type === "logo" ? undefined : "#111827",
      align: "left",
      ...(block.type === "logo" ? { w_mm: block.w_mm, h_mm: block.h_mm } : {}),
    };
    const next = [...elements, el];
    onChange(next);
    setSelected(next.length - 1);
  };

  const removeBlock = (idx) => {
    onChange(elements.filter((_, i) => i !== idx));
    setSelected(null);
  };

  // ── Dragging ────────────────────────────────────────────────────────────────
  const onPointerDown = (e, idx) => {
    e.stopPropagation();
    setSelected(idx);
    const rect = canvasRef.current.getBoundingClientRect();
    const el = elements[idx];
    dragRef.current = {
      idx,
      offsetX_mm: pxToMmX(e.clientX - rect.left) - (el.x_mm || 0),
      offsetY_mm: pxToMmY(e.clientY - rect.top) - (el.y_mm || 0),
    };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e) => {
    const d = dragRef.current;
    if (!d) return;
    const rect = canvasRef.current.getBoundingClientRect();
    let x = pxToMmX(e.clientX - rect.left) - d.offsetX_mm;
    let y = pxToMmY(e.clientY - rect.top) - d.offsetY_mm;
    // Clamp inside the page.
    x = Math.max(0, Math.min(w_mm - 2, x));
    y = Math.max(0, Math.min(h_mm - 2, y));
    update(d.idx, { x_mm: Math.round(x), y_mm: Math.round(y) });
  };

  const onPointerUp = () => { dragRef.current = null; };

  useEffect(() => {
    window.addEventListener("pointerup", onPointerUp);
    return () => window.removeEventListener("pointerup", onPointerUp);
  }, []);

  const selEl = selected != null ? elements[selected] : null;

  return (
    <div className="space-y-3">
      {/* Palette */}
      <div className="flex flex-wrap gap-2">
        {FIELD_BLOCKS.map((b) => {
          const Icon = b.icon;
          return (
            <button
              key={b.id}
              type="button"
              onClick={() => addBlock(b)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border bg-card hover:border-primary hover:bg-primary/5 text-xs font-medium transition-colors"
              title={`Add ${b.label}`}
            >
              <Icon className="w-3.5 h-3.5 text-primary" />
              {b.label}
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Click a field to add it, then drag it into position on the page. Select a block to edit its size, colour and alignment.
      </p>

      {/* Canvas + inspector */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* A4 canvas */}
        <div
          ref={canvasRef}
          onPointerMove={onPointerMove}
          onClick={() => setSelected(null)}
          className="relative bg-white border border-border shadow-sm shrink-0 mx-auto touch-none select-none"
          style={{ width: w_mm * PX_PER_MM, height: h_mm * PX_PER_MM }}
        >
          {/* Margin guide */}
          <div
            className="absolute border border-dashed border-primary/20 pointer-events-none"
            style={{
              left: 20 * PX_PER_MM, top: 12 * PX_PER_MM,
              right: 18 * PX_PER_MM, bottom: 12 * PX_PER_MM,
            }}
          />
          {/* Placed elements */}
          {elements.map((el, idx) => {
            const isSel = idx === selected;
            const left = (el.x_mm || 0) * PX_PER_MM;
            const top = (el.y_mm || 0) * PX_PER_MM;
            const isLogo = (el.type || "text").toLowerCase() === "logo";
            const alignJustify = el.align === "center" ? "center" : el.align === "right" ? "flex-end" : "flex-start";
            return (
              <div
                key={idx}
                onPointerDown={(e) => onPointerDown(e, idx)}
                onClick={(e) => { e.stopPropagation(); setSelected(idx); }}
                className={`absolute cursor-move flex items-center gap-1 ${isSel ? "ring-2 ring-primary z-10" : "hover:ring-1 hover:ring-primary/40"}`}
                style={{ left, top, maxWidth: (w_mm - (el.x_mm || 0) - 4) * PX_PER_MM }}
              >
                {isLogo ? (
                  <div
                    className="flex items-center justify-center bg-primary/10 border border-primary/30 rounded text-[8px] text-primary font-semibold"
                    style={{ width: (el.w_mm || 32) * PX_PER_MM, height: (el.h_mm || 16) * PX_PER_MM }}
                  >
                    LOGO
                  </div>
                ) : (
                  <span
                    style={{
                      fontSize: (el.size || 10) * PX_PER_MM * 0.35,
                      color: el.color || "#111827",
                      fontWeight: (el.size || 10) >= 14 ? 700 : 400,
                      whiteSpace: "nowrap",
                      display: "flex",
                      width: "100%",
                      justifyContent: alignJustify,
                    }}
                  >
                    {previewText(el, company)}
                  </span>
                )}
              </div>
            );
          })}
          {elements.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-xs pointer-events-none">
              Click a field above to place it here
            </div>
          )}
        </div>

        {/* Inspector for the selected block */}
        <div className="flex-1 min-w-0">
          {selEl ? (
            <div className="rounded-lg border border-border p-3 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium flex items-center gap-1.5">
                  <GripVertical className="w-4 h-4 text-muted-foreground" />
                  {(selEl.type || "text") === "logo" ? "Company Logo" : "Text Block"}
                </span>
                <button
                  type="button"
                  onClick={() => removeBlock(selected)}
                  className="text-destructive hover:bg-destructive/10 rounded p-1"
                  title="Delete block"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {(selEl.type || "text") !== "logo" && (
                <>
                  <label className="block">
                    <span className="text-xs text-muted-foreground">Text / token</span>
                    <input
                      value={selEl.value || ""}
                      onChange={(e) => update(selected, { value: e.target.value })}
                      className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                    />
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block">
                      <span className="text-xs text-muted-foreground">Font size (pt)</span>
                      <input
                        type="number" min={5} max={48} value={selEl.size || 10}
                        onChange={(e) => update(selected, { size: +e.target.value })}
                        className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-muted-foreground">Colour</span>
                      <input
                        type="color" value={selEl.color || "#111827"}
                        onChange={(e) => update(selected, { color: e.target.value })}
                        className="w-full mt-1 h-[34px] rounded border border-border cursor-pointer"
                      />
                    </label>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">Alignment</span>
                    <div className="flex gap-1 mt-1">
                      {[["left", AlignLeft], ["center", AlignCenter], ["right", AlignRight]].map(([a, Icon]) => (
                        <button
                          key={a}
                          type="button"
                          onClick={() => update(selected, { align: a })}
                          className={`p-1.5 rounded border ${selEl.align === a ? "border-primary bg-primary/10 text-primary" : "border-border"}`}
                        >
                          <Icon className="w-4 h-4" />
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {(selEl.type || "text") === "logo" && (
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-xs text-muted-foreground">Width (mm)</span>
                    <input
                      type="number" min={5} max={120} value={selEl.w_mm || 32}
                      onChange={(e) => update(selected, { w_mm: +e.target.value })}
                      className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-muted-foreground">Height (mm)</span>
                    <input
                      type="number" min={5} max={80} value={selEl.h_mm || 16}
                      onChange={(e) => update(selected, { h_mm: +e.target.value })}
                      className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                    />
                  </label>
                  <p className="col-span-2 text-[11px] text-muted-foreground">
                    Renders the template’s uploaded logo. Upload one in the Images section.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 pt-1 border-t border-border">
                <label className="block">
                  <span className="text-xs text-muted-foreground">X (mm)</span>
                  <input
                    type="number" min={0} max={w_mm} value={selEl.x_mm || 0}
                    onChange={(e) => update(selected, { x_mm: +e.target.value })}
                    className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                  />
                </label>
                <label className="block">
                  <span className="text-xs text-muted-foreground">Y (mm)</span>
                  <input
                    type="number" min={0} max={h_mm} value={selEl.y_mm || 0}
                    onChange={(e) => update(selected, { y_mm: +e.target.value })}
                    className="w-full mt-1 px-2 py-1.5 rounded border border-border bg-background text-sm"
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
              Select a placed block to edit it, or add a field from the palette above.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
