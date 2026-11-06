# rainsure

## Findings from the data

**Where physics and AI disagree, the physics model is usually the lighter one.** Across all grid points and 6-hour
blocks where the two ensembles differ by 20 points or more, the most common pattern is that both expect rain but one
model's median is under 2.5 mm ("lighter rain": 39.1 % of disagreements in run 2026110512, 37.6 % in 2026110412). In
those "lighter rain" cases the AI model (AIFS) was the drier one in only 24 % and 33 % of cases respectively, so the
physics model (IFS) was the lighter one in about 70 %. Measured on these two runs only (about 41,000 disagreeing
block-cells each); it is not a general claim about the models. ECMWF's own case study of Storm Hans found the opposite
for that one extreme event (DECISIONS.md D59, D60).

## Measured performance

**Neutral measurement — Google PageSpeed Insights** (Lighthouse 13.6.0 on Google's servers, 6 Nov 2026 15:25 IST,
`?lat=13.088&lon=80.278` Chennai):

| | Mobile (Moto G Power, Slow 4G) | Desktop |
|---|---|---|
| Performance | 73 | 66 |
| Accessibility | 100 | 94 (three issues found and fixed afterwards, not re-measured yet) |
| Best Practices / SEO | 100 / 100 | 100 / 100 |
| First Contentful Paint | 0.9 s | 0.2 s |
| Largest Contentful Paint | 0.9 s | 0.5 s |
| Total Blocking Time | 1,020 ms | 1,420 ms |
| Cumulative Layout Shift | 0 | 0 |
| Speed Index | 5.7 s | 2.0 s |

The answer paints within a second; the score is held back by Total Blocking Time, which is MapLibre's own start-up
work (about 2.2 s of script on a local desktop Lighthouse run). The answer never waits for it.

**Our own measurement** (headless Chrome over the DevTools protocol, Chennai, phone 390 x 844, cold cache; times of
our `answer-visible` and `map-visible` marks). Caveat: this machine's own connection is slow and erratic and the
throttling stacks on top of it, so these numbers are pessimistic.

| Profile | Answer visible | Map visible |
|---|---|---|
| Slow 4G (150 ms, 1.6 Mbit/s, 4x CPU), before the speed work | 9.1–16.8 s | 22.3–26.7 s |
| Slow 4G, after (4 runs; a 5th got no reading and counts as failed) | 2.2–7.4 s | 9.5–15.4 s |
| Typical 4G (60 ms, 9 Mbit/s, normal CPU), after, 5 runs | 1.4–7.4 s (median 2.7) | 6.0–14.9 s (median 10.0) |
| No throttling, warm runs | 0.2–1.7 s | 2.3–4.8 s |

What changed and why is in DECISIONS.md D62.

## Future work
- **District answers** (area-weighted rain over a district): needs a district boundary dataset that matches India's
  official (India point of view) boundaries, with a licence that allows publishing. Not built; point lookup and place
  search cover the app for now (DECISIONS.md D53).
