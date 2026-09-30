# Sunbed Competitor Map

Interactive map of UV tanning / sunbed locations across London and the South East.

- Searches Google Places for `sunbed`, `sunbeds`, `tanning salon` and `tanning`
- Deduplicates by Google Place ID
- Filters obvious non-tanning false positives
- Shows every relevant business as the same competitor pin
- Adjustable competition-radius circles
- Monthly refresh via GitHub Actions

Once GitHub Pages is enabled from **main / root**, the live site is:

https://keko191.github.io/sunbed-map/

## Google Places key

The refresh workflow expects a repository Actions secret named `GOOGLE_API_KEY`.

GitHub: **Settings → Secrets and variables → Actions → New repository secret**

## Refreshing

After the secret is added, go to **Actions → Refresh sunbed locations → Run workflow** for the first scan. It then runs automatically each month.
