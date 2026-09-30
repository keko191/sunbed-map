# Sunbed Competitor Map

Interactive map of UV tanning / sunbed locations across London and the South East.

- Searches Google Places for sunbed, sunbeds, tanning salon and tanning
- Deduplicates by Google Place ID
- Filters obvious non-tanning false positives
- Shows all relevant businesses as one competitor type
- Adjustable competition-radius circles
- Monthly refresh via GitHub Actions

Live site: https://keko191.github.io/sunbed-map/

## Google Places key

The refresh workflow expects a repository Actions secret named `GOOGLE_API_KEY`.
