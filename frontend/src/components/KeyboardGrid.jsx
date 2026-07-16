import useGridKeyNav from "@/hooks/useGridKeyNav";

/**
 * Drop-in wrapper for a line-item grid's <table> (or any container) that
 * wires up full Tally-style cell navigation and marks the region
 * `data-grid-managed` so it doesn't fight with a surrounding <KeyboardForm>'s
 * own Enter-as-Tab handling (see useEnterNavigation's docstring for why that
 * matters — a real bug this project hit once already).
 *
 * Usage (render-prop child function receives the nav API):
 *   <KeyboardGrid
 *     as="table" className="w-full ..."
 *     rowCount={form.items.length}
 *     colCount={(row) => gstColsForRow(form.items[row])}  // number OR per-row fn
 *     onRowComplete={addLine}
 *     onInsertRow={insertLineAfter}
 *     onDeleteRow={removeLineKeepingOne}
 *   >
 *     {(nav) => (
 *       <tbody>
 *         {form.items.map((l, idx) => (
 *           <tr key={idx}>
 *             <td><ItemSearch inputRef={nav.registerCell(idx, 0)} onKeyDown={nav.handleKeyDown(idx, 0)} .../></td>
 *             ...
 *           </tr>
 *         ))}
 *       </tbody>
 *     )}
 *   </KeyboardGrid>
 *
 * `colCount` supports variable columns per row out of the box (see
 * useGridKeyNav) — this is what makes a GST-rate cell that renders 1, 2, or 1
 * inputs depending on tax type work seamlessly: pass a function and register
 * whichever columns that row's current shape actually has.
 */
export default function KeyboardGrid({
  as: Tag = "table",
  rowCount,
  colCount,
  onRowComplete,
  onInsertRow,
  onDeleteRow,
  children,
  ...rest
}) {
  const nav = useGridKeyNav({ rowCount, colCount, onRowComplete, onInsertRow, onDeleteRow });
  return (
    <Tag data-grid-managed {...rest}>
      {typeof children === "function" ? children(nav) : children}
    </Tag>
  );
}
