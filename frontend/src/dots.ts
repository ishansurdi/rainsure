/** 26 hex chars from the tile (store/points.py) -> 100 wet flags: 0-49 physics members, 50-99 AI members. */
export function decodeDots(hex: string): boolean[] {
  if (!/^[0-9a-f]{26}$/.test(hex)) throw new Error(`bad dots ${hex}`);
  const out: boolean[] = [];
  for (let n = 0; n < 100; n++) {
    const byte = parseInt(hex.slice(2 * (n >> 3), 2 * (n >> 3) + 2), 16);
    out.push(((byte >> (7 - (n & 7))) & 1) === 1);
  }
  return out;
}
