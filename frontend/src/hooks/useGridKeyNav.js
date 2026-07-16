import { useCallback, useRef } from "react";

/**
 * Tally Prime-style keyboard navigation for a grid of input/select cells laid
 * out in rows × columns.
 *
 * Usage:
 *   const nav = useGridKeyNav({ rowCount, colCount, onRowComplete, onInsertRow, onDeleteRow });
 *   <input ref={nav.registerCell(row, col)} onKeyDown={nav.handleKeyDown(row, col)} />
 *
 * `colCount` may be either a plain number (every row has the same column
 * count) OR a function `(row) => number` for grids whose column count varies
 * per row — e.g. a GST-rate cell that renders 1 input for a flat rate, 2 for
 * CGST+SGST, or 1 for IGST, so row N might have 5 columns and row N+1 has 6.
 * The registered cell indices don't need to be contiguous either: register
 * whatever columns exist for that row's current shape (0, 1, 2, ...) and
 * navigation reads the row's live column count on every keypress, so it
 * adapts immediately when a row's shape changes (e.g. switching GST type)
 * without needing to re-create the hook or its callbacks.
 *
 * Behaviour:
 *   Enter      → move to the next column; at the last column of the last row,
 *                fires onRowComplete() (caller appends a new row) then focuses
 *                the first cell of that new row on the next tick.
 *   ArrowRight → next column (same row)
 *   ArrowLeft  → previous column (same row)
 *   ArrowDown  → same column, next row (clamped to that row's own column count)
 *   ArrowUp    → same column, previous row (clamped to that row's own column count)
 *   Insert     → onInsertRow(row) — caller inserts a blank row after `row`;
 *                focuses column 0 of the new row
 *   Ctrl+Delete → onDeleteRow(row) — caller removes `row`; focuses column 0
 *                of the row that takes its place (or the previous row if it
 *                was the last one)
 *   Escape     → blur the current cell
 *
 * Arrow keys are only intercepted when the input's cursor is already at the
 * boundary in that direction (start/end of text) so normal text editing
 * (moving the caret within a value) still works — this matches how Tally
 * itself behaves (arrows move within a field first, then between fields).
 */
export default function useGridKeyNav({ rowCount, colCount, onRowComplete, onInsertRow, onDeleteRow }) {
  // cells[row][col] = HTMLElement
  const cellsRef = useRef({});

  // Normalize colCount to a per-row lookup regardless of which form the
  // caller passed. Read fresh on every call (not memoized) so a row whose
  // shape just changed (e.g. GST type toggle) is reflected immediately.
  const colsForRow = useCallback((row) => {
    if (typeof colCount === "function") return colCount(row) ?? 0;
    return colCount ?? 0;
  }, [colCount]);

  const registerCell = useCallback((row, col) => (el) => {
    if (!cellsRef.current[row]) cellsRef.current[row] = {};
    if (el) cellsRef.current[row][col] = el;
    else if (cellsRef.current[row]) delete cellsRef.current[row][col];
  }, []);

  // Find the highest actually-registered column index for a row, capped by
  // that row's declared column count — a row may register fewer live cells
  // than its nominal count (e.g. a read-only computed column isn't wired
  // into the grid), so "last column" means the last NAVIGABLE one.
  const lastRegisteredCol = useCallback((row) => {
    const cells = cellsRef.current[row];
    if (!cells) return -1;
    const keys = Object.keys(cells).map(Number);
    return keys.length ? Math.max(...keys) : -1;
  }, []);

  const focusCell = useCallback((row, col) => {
    // Defer to the next tick so a just-appended row's DOM node exists.
    requestAnimationFrame(() => {
      const el = cellsRef.current[row]?.[col];
      if (el) {
        el.focus();
        if (typeof el.select === "function") el.select();
      }
    });
  }, []);

  // ArrowDown/Up need a target column that still exists on the destination
  // row when column counts differ row-to-row — clamp to that row's own max
  // registered column rather than blindly reusing the source row's column.
  const focusCellClamped = useCallback((row, col) => {
    requestAnimationFrame(() => {
      const rowCells = cellsRef.current[row];
      if (!rowCells) return;
      const keys = Object.keys(rowCells).map(Number);
      if (!keys.length) return;
      const below = keys.filter((k) => k <= col);
      const targetCol = keys.includes(col) ? col : (below.length ? Math.max(...below) : Math.min(...keys));
      const el = rowCells[targetCol] ?? rowCells[keys[0]];
      if (el) {
        el.focus();
        if (typeof el.select === "function") el.select();
      }
    });
  }, []);

  const isAtStart = (el) => {
    if (el?.selectionStart == null) return true;
    return el.selectionStart === 0 && el.selectionEnd === 0;
  };
  const isAtEnd = (el) => {
    if (el?.selectionStart == null) return true;
    const len = el.value?.length ?? 0;
    return el.selectionStart === len && el.selectionEnd === len;
  };

  const handleKeyDown = useCallback((row, col) => (e) => {
    const target = e.target;
    const colCountHere = colsForRow(row);

    if (e.key === "Enter") {
      e.preventDefault();
      const isLastCol = col >= colCountHere - 1 || col >= lastRegisteredCol(row);
      const isLastRow = row >= rowCount - 1;
      if (isLastCol && isLastRow) {
        onRowComplete?.();
        focusCell(row + 1, 0);
      } else if (isLastCol) {
        focusCell(row + 1, 0);
      } else {
        focusCell(row, col + 1);
      }
      return;
    }

    if (e.key === "ArrowRight" && isAtEnd(target)) {
      if (col < colCountHere - 1 && col < lastRegisteredCol(row)) {
        e.preventDefault();
        focusCell(row, col + 1);
      }
      return;
    }
    if (e.key === "ArrowLeft" && isAtStart(target)) {
      if (col > 0) {
        e.preventDefault();
        focusCell(row, col - 1);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusCellClamped(Math.min(row + 1, rowCount - 1), col);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      focusCellClamped(Math.max(row - 1, 0), col);
      return;
    }
    if (e.key === "Insert" && onInsertRow) {
      e.preventDefault();
      onInsertRow(row);
      focusCell(row + 1, 0);
      return;
    }
    if (e.key === "Delete" && e.ctrlKey && onDeleteRow) {
      e.preventDefault();
      onDeleteRow(row);
      // The row at `row` is gone; the row that slides into its place (or the
      // previous row, if `row` was last) is the sensible next focus target.
      focusCell(Math.min(row, rowCount - 2), 0);
      return;
    }
    if (e.key === "Escape") {
      target.blur?.();
    }
  }, [colsForRow, rowCount, onRowComplete, onInsertRow, onDeleteRow, focusCell, focusCellClamped, lastRegisteredCol]);

  return { registerCell, handleKeyDown, focusCell };
}
