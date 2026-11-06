// Draggable bottom sheet with snap points (phone). On desktop the sheet is a fixed side panel (CSS).
const SNAPS = [0.6, 0.15, 0.0]; // sheet top as a share of the viewport height: ~40 %, ~85 %, full
let current = 0;
const set = (topFrac: number) => document.documentElement.style.setProperty("--sheet-top", `${(topFrac * 100).toFixed(1)}vh`);

/** Move the first (~40 %) snap, e.g. so the whole timeline fits; applied now if the sheet sits there. */
export function setFirstSnap(topFrac: number): void {
  SNAPS[0] = topFrac;
  if (current === 0) set(topFrac);
}

export function initSheet(sheet: HTMLElement, handle: HTMLElement): (snap: number) => void {
  const snapTo = (n: number) => { current = n; set(SNAPS[n]); };
  snapTo(0);
  let startY = 0, startTop = 0, dragging = false;
  handle.addEventListener("pointerdown", (e) => {
    dragging = true; startY = e.clientY; startTop = SNAPS[current] * innerHeight;
    sheet.classList.add("dragging"); handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    set(Math.min(0.75, Math.max(0, (startTop + e.clientY - startY) / innerHeight)));
  });
  const end = (e: PointerEvent) => {
    if (!dragging) return;
    dragging = false; sheet.classList.remove("dragging");
    const frac = (startTop + e.clientY - startY) / innerHeight;
    let best = 0;
    SNAPS.forEach((s, n) => { if (Math.abs(s - frac) < Math.abs(SNAPS[best] - frac)) best = n; });
    snapTo(best);
  };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
  handle.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp" || e.key === "Enter") snapTo(Math.min(SNAPS.length - 1, current + 1));
    if (e.key === "ArrowDown") snapTo(Math.max(0, current - 1));
  });
  return snapTo;
}
