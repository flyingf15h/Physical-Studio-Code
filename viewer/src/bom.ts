// Shared between BomImport (which adds parts) and PartsLibrary (which lists them).
import type { BomRow } from './api'

/** Fired on window when a BOM upload has added parts to your library. */
export const PARTS_CHANGED = 'physical-studio:parts-changed'

/** The chip a finished row becomes: "2 × GY-530 VL53L0X", or the row's own name when nothing was found. */
export function chipFor(row: BomRow): string {
  const name = row.part_name || row.name
  return row.quantity > 1 ? `${row.quantity} × ${name}` : name
}
