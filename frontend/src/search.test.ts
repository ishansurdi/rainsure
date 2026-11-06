import { describe, expect, it } from "vitest";
import { normalise, searchPlaces, type Place } from "./search";

const P: Place[] = [
  ["Mumbai", "Maharashtra", 19.073, 72.883, 12691836],
  ["Aurangabad", "Maharashtra", 19.877, 75.343, 1016441],
  ["Aurangabad", "Bihar", 24.752, 84.374, 95929],
  ["Navi Mumbai", "Maharashtra", 19.034, 73.03, 2600000],
  ["Port Blair", "Andaman and Nicobar", 11.667, 92.736, 112050],
  ["Aurangābād Bāngar", "Uttar Pradesh", 27.1, 79.9, 2000],
];

describe("searchPlaces", () => {
  it("keeps duplicate names apart by state, most populous first", () => {
    expect(searchPlaces(P, "aurang").map((p) => `${p[0]}, ${p[1]}`)).toEqual([
      "Aurangabad, Maharashtra", "Aurangabad, Bihar", "Aurangābād Bāngar, Uttar Pradesh"]);
  });
  it("matches without accents and ranks name-start before word-start", () => {
    expect(normalise("Aurangābād  Bāngar")).toBe("aurangabad bangar");
    expect(searchPlaces(P, "mumbai").map((p) => p[0])).toEqual(["Mumbai", "Navi Mumbai"]);
    expect(searchPlaces(P, "blair").map((p) => p[0])).toEqual(["Port Blair"]);
  });
  it("needs two characters and returns nothing for no match", () => {
    expect(searchPlaces(P, "a")).toEqual([]);
    expect(searchPlaces(P, "zzz")).toEqual([]);
  });
});
