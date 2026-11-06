// Place search over the static GeoNames file (DECISIONS.md D26): [name, state, lat, lon, population], most populous first.

export type Place = [string, string, number, number, number];

/** Lower case, accents removed, spaces collapsed. */
export function normalise(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
}

/** Great-circle distance in km. */
export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 +
    Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

/** Nearest place within maxKm, preferring the more populous one when two are about equally near (within 2 km). */
export function nearestPlace(places: Place[], lat: number, lon: number, maxKm = 25): { place: Place; km: number } | null {
  let best: { place: Place; km: number } | null = null;
  for (const p of places) {
    if (Math.abs(p[2] - lat) > 0.5 || Math.abs(p[3] - lon) > 0.5) continue; // cheap prefilter (~55 km)
    const km = distanceKm(lat, lon, p[2], p[3]);
    if (km > maxKm) continue;
    if (!best || km < best.km - 2 || (Math.abs(km - best.km) <= 2 && p[4] > best.place[4])) best = { place: p, km };
  }
  return best;
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
