# Incidents

Every outage, wrong output or fix, dated.

## 17/10/2026, before launch

- First live search near Dudley: 6 notices, 66 seconds, because each notice needs 3 to 4 model calls on the local 27B model and extraction runs inside the request. Fix before public use: pre-extract in the background and show "reading..." for notices not yet done.
- Two notices lost every summary sentence to the gate (the judge returned quotes that were not verbatim). Honest, but worth a stricter quoting instruction and an evaluation set.
- One "Where" field included a council contact address rather than an affected place. Prompt to say "places affected, not addresses for correspondence".

## 17/10/2026, map view, first test by the author

- **The page reloaded every 8 seconds** while notices were still being read (a `meta refresh`), so clicking a pin's "Show in the list" link jumped to the card and then the whole page, map included, reloaded under the reader. Fixed: no reload; a script asks `/status` for the notices still pending and swaps in each finished card from `/card/{id}`, so the map, the chosen filter, open notices and the scroll position stay put.
- **Pins outside the circle.** Two causes, both verified against the Gazette. (1) The Gazette's distance filter only honours 1, 5, 10, 15, 20, 25 and 30 miles; 2 and 3 miles returned exactly the 1-mile set near Dudley, so "within 3 miles" was really 1 mile. (2) A notice is filed under several postcodes (near Dudley: the street, the council at DY1 1RY, a consultant in Worcester) and the feed carries only the first as `geo:Point`; the Gazette matches on any of them, so a notice inside the radius could be pinned 3 miles out, or 23 miles out. Fixed: ask the Gazette for the smallest honoured radius that covers the asked distance, read `/notice/{id}/data.jsonld` for every filed postcode when the feed point is outside the circle (at most 16 lookups a search, stored with the notice), pin at the nearest, and drop notices whose nearest filed postcode is outside. Geocoding the street names from the plain-English "Where" field was tried and rejected: postcodes.io's places lookup returns nothing for road names, and OpenStreetMap's Nominatim returned three different "Priory Road, Dudley".
- **Miles and kilometres.** Added a unit choice (miles: 1, 3, 5, 10, 15; km: 2, 5, 10, 15, 25). The Gazette is always asked in miles; distances are measured and shown in the unit chosen.
- **Speed.** The Gazette answers each category feed in 2 to 4 seconds; six categories one after another took about 22 seconds. Now three feeds are fetched side by side with the two-requests-a-second gap kept across threads, candidates are cached for an hour under the Gazette radius actually asked for (so changing 3 miles to 5 km reuses the feed), and linked-data lookups run three at a time.
