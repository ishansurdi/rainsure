// Place search over the static GeoNames file (DECISIONS.md D26): [name, state, lat, lon, population], most populous first.

export type Place = [string, string, number, number, number];

/** Lower case, accents removed, spaces collapsed. */
export function normalise(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
}

/** Up to `limit` places: name starts with the query first, then a word starts with it, then contains it. */
export function searchPlaces(places: Place[], query: string, limit = 8): Place[] {
  const q = normalise(query);
  if (q.length < 2) return [];
  const starts: Place[] = [], word: Place[] = [], contains: Place[] = [];
  for (const p of places) {
    const n = normalise(p[0]);
    if (n.startsWith(q)) starts.push(p);
    else if (n.includes(` ${q}`)) word.push(p);
    else if (n.includes(q)) contains.push(p);
    if (starts.length >= limit) break;
  }
  return [...starts, ...word, ...contains].slice(0, limit);
}
