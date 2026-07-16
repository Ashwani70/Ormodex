import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Save, Download, Search } from "lucide-react";
import {
  PageHeader, SectionTitle, Card, StatTile,
  PrimaryButton, SecondaryButton, SuccessButton,
  Input, Textarea, Select, Field,
  Badge, StatusBadge, EmptyState,
  Spinner, Skeleton, SkeletonTable,
} from "@/components/ui-kit";

// ============================================================
// /design-system — living style guide for the Aurora system.
// Every shared primitive and its states (default, hover, disabled,
// loading, error, empty) is rendered here so regressions surface
// immediately and contributors have one visual reference.
// ============================================================

function Block({ title, children }) {
  return (
    <section className="mb-10">
      <SectionTitle>{title}</SectionTitle>
      <Card>{children}</Card>
    </section>
  );
}

function Swatch({ name, varName, hex }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="h-14 w-full border border-border"
        style={{ background: `var(${varName})`, borderRadius: "var(--radius-md)" }}
      />
      <div className="text-xs font-medium text-foreground">{name}</div>
      <div className="text-[11px] text-muted-foreground font-mono">{hex}</div>
    </div>
  );
}

export default function DesignSystem() {
  const [loadingBtn, setLoadingBtn] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);

  const fakeLoad = () => {
    setLoadingBtn(true);
    setTimeout(() => setLoadingBtn(false), 1600);
  };

  const toggleSkeleton = () => {
    setShowSkeleton(true);
    setTimeout(() => setShowSkeleton(false), 2000);
  };

  return (
    <div data-testid="design-system-page" className="max-w-[1100px]">
      <PageHeader
        eyebrow="Aurora Design System"
        title="Component Library"
        description="A living reference for every shared UI primitive and its states. Build new modules from these — never hard-code colors, radius, or shadows."
        actions={<PrimaryButton icon={Plus}>Primary Action</PrimaryButton>}
      />

      {/* Colors */}
      <Block title="Colors">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
          <Swatch name="Background" varName="--bg" hex="#F8FAFC" />
          <Swatch name="Surface" varName="--surface" hex="#FFFFFF" />
          <Swatch name="Primary" varName="--primary-color" hex="#4F46E5" />
          <Swatch name="Primary Soft" varName="--primary-soft" hex="#EEF2FF" />
          <Swatch name="Accent" varName="--accent-color" hex="#10B981" />
          <Swatch name="Text" varName="--text" hex="#0F172A" />
          <Swatch name="Success" varName="--success" hex="#10B981" />
          <Swatch name="Warning" varName="--warning" hex="#F59E0B" />
          <Swatch name="Danger" varName="--danger" hex="#EF4444" />
          <Swatch name="Info" varName="--info" hex="#3B82F6" />
          <Swatch name="Border" varName="--border-color" hex="#E2E8F0" />
          <Swatch name="Sidebar" varName="--sidebar-bg" hex="#0F172A" />
        </div>
      </Block>

      {/* Typography */}
      <Block title="Typography">
        <div className="space-y-3">
          <h1 className="text-foreground">Heading 1 — 28px / 700</h1>
          <h2 className="text-foreground">Heading 2 — 22px / 600</h2>
          <h3 className="text-foreground">Heading 3 — 18px / 600</h3>
          <p className="text-foreground text-sm">Body text — 14px / 1.5. The quick brown fox jumps over the lazy dog. Information-dense without feeling crowded.</p>
          <p className="caption">Caption — 12px muted, used for hints and metadata.</p>
          <div className="label-overline">Overline label</div>
        </div>
      </Block>

      {/* Buttons */}
      <Block title="Buttons">
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <PrimaryButton icon={Save}>Primary</PrimaryButton>
            <SecondaryButton icon={Download}>Secondary</SecondaryButton>
            <SuccessButton icon={Plus}>Success</SuccessButton>
            <SecondaryButton danger icon={Trash2}>Danger</SecondaryButton>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <PrimaryButton disabled>Disabled</PrimaryButton>
            <SecondaryButton disabled>Disabled</SecondaryButton>
            <PrimaryButton loading={loadingBtn} onClick={fakeLoad}>
              {loadingBtn ? "Saving…" : "Click to load"}
            </PrimaryButton>
          </div>
          <p className="caption">All buttons are 40px tall, rounded-md, with a subtle hover lift. States: default · hover · disabled · loading.</p>
        </div>
      </Block>

      {/* Form controls */}
      <Block title="Form Controls">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4 max-w-2xl">
          <Field label="Text input" required>
            <Input placeholder="Enter value…" />
          </Field>
          <Field label="Select">
            <Select defaultValue="">
              <option value="" disabled>Choose…</option>
              <option>Option A</option>
              <option>Option B</option>
            </Select>
          </Field>
          <Field label="With hint" hint="Helper text appears below the field.">
            <Input placeholder="example@company.com" />
          </Field>
          <Field label="Error state" error="GSTIN must be 15 characters.">
            <Input defaultValue="27ABCDE" error />
          </Field>
          <Field label="Disabled">
            <Input placeholder="Read only" disabled />
          </Field>
          <Field label="Textarea">
            <Textarea rows={3} placeholder="Notes…" />
          </Field>
        </div>
        <p className="caption mt-4">Focus any field to see the 3px primary ring. Errors switch border and ring to danger.</p>
      </Block>

      {/* Cards & stat tiles */}
      <Block title="Cards & Stat Tiles">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatTile label="Total Revenue" value="₹ 12,40,500" sub="+8.2% vs last month" accent />
          <StatTile label="Open Invoices" value="42" sub="₹ 3,12,000 due" />
          <StatTile label="Low Stock Items" value="7" sub="Reorder required" />
        </div>
      </Block>

      {/* Table */}
      <Block title="Data Table">
        <div className="flex justify-end mb-3">
          <SecondaryButton icon={Search} onClick={toggleSkeleton}>Simulate loading</SecondaryButton>
        </div>
        {showSkeleton ? (
          <SkeletonTable rows={5} cols={5} />
        ) : (
          <div className="overflow-x-auto border border-border" style={{ borderRadius: "var(--radius-lg)" }}>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th>Invoice #</th><th>Customer</th><th>Date</th><th>Amount</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["INV-1042", "Acme Industries", "2026-06-10", "₹ 45,200", "PAID"],
                  ["INV-1043", "Bharat Steel", "2026-06-11", "₹ 1,12,000", "PARTIAL"],
                  ["INV-1044", "Crest Pvt Ltd", "2026-06-12", "₹ 8,900", "UNPAID"],
                  ["INV-1045", "Delta Corp", "2026-06-13", "₹ 67,500", "SENT"],
                ].map((r) => (
                  <tr key={r[0]}>
                    <td className="font-medium">{r[0]}</td>
                    <td>{r[1]}</td>
                    <td>{r[2]}</td>
                    <td className="tabular">{r[3]}</td>
                    <td><StatusBadge status={r[4]} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="caption mt-3">Sticky headers, zebra rows, and primary-soft hover. Scroll a long table to see the header stick.</p>
      </Block>

      {/* Badges */}
      <Block title="Status Badges">
        <div className="flex flex-wrap gap-2">
          <Badge tone="success">Success</Badge>
          <Badge tone="warning">Warning</Badge>
          <Badge tone="danger">Danger</Badge>
          <Badge tone="info">Info</Badge>
          <Badge tone="neutral">Neutral</Badge>
          <StatusBadge status="PAID" />
          <StatusBadge status="PENDING" />
          <StatusBadge status="CANCELLED" />
          <StatusBadge status="IN_TRANSIT" />
        </div>
      </Block>

      {/* Loading states */}
      <Block title="Loading States">
        <div className="space-y-4">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Spinner className="w-5 h-5 text-primary" /> Inline spinner
          </div>
          <div className="flex flex-col gap-2 max-w-sm">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-24 w-full" />
          </div>
        </div>
      </Block>

      {/* Empty state */}
      <Block title="Empty State">
        <EmptyState
          message="No invoices yet"
          action={<PrimaryButton icon={Plus}>Create Invoice</PrimaryButton>}
        />
      </Block>

      {/* Notifications */}
      <Block title="Notifications (Toasts)">
        <div className="flex flex-wrap gap-3">
          <SuccessButton onClick={() => toast.success("Saved successfully.")}>Success toast</SuccessButton>
          <SecondaryButton onClick={() => toast.warning("Stock running low.")}>Warning toast</SecondaryButton>
          <SecondaryButton danger onClick={() => toast.error("Failed to save record.")}>Error toast</SecondaryButton>
          <SecondaryButton onClick={() => toast("Heads up — new update available.")}>Info toast</SecondaryButton>
        </div>
        <p className="caption mt-4">Toasts use a colored left border per type and auto-dismiss after 5 seconds.</p>
      </Block>
    </div>
  );
}
