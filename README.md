# Labor Card Checker

Checks HotSchedules daily Labor Card PDFs for staffing-rule problems before a shift: missing locations, out-of-order server sections, too few closers, host role gaps, unsplit doubles and more. It then hands back marked-up PDFs a manager can review.

It is built for casual-dining restaurants that schedule in HotSchedules. The rules are switchable and their thresholds are adjustable in the app.

Everything runs locally. PDFs are never uploaded to a third-party service.

| Folder | What it is |
|---|---|
| `local/` | Python app with a small localhost web UI. Reads PDFs, runs the checks, and exports annotated cards. |
| `web/` | The same analyzer compiled to run fully in the browser (Pyodide + pdf.js), deployable as a static Cloudflare site. Roster bytes never leave the browser. |
| `extension/` | Chrome extension that downloads a Thursday-to-Wednesday week of Labor Card PDFs from your signed-in HotSchedules session. |

## What it checks

- Every scheduled person except managers has a location, including Dish and Kitchen
- Server sections run 1–9 in order, separately for AM and PM; lounge staff count as servers; overlapping duplicate locations are flagged
- Section 1 is among the first server arrivals, and Section 1 plus a lounge server cover close
- At least one host on lunch and dinner; three or more overlapping hosts need separate Leader/Seater/Greeter labels
- Three closing cooks (midnight Sun–Thu, 1 AM Fri–Sat); a single PM Z3 cook must be the Z3 rover
- Bar and To Go do not start before a configurable time (default 10:30 AM)
- More than five doubles needs a staffing-plan review; shifts spanning the AM/PM boundary without `[D]` need review
- House shifts and after-midnight starts are flagged

Every finding is guidance for a manager to confirm. The tool never invents staffing levels or forecasts. Scanned or hand-marked cards are flagged as unreadable, never passed.

## Install and run

### Local app (Windows, macOS, Linux)

Requires Python 3.12+.

```bash
cd local
pip install -r requirements.txt
python server.py --open
```

This opens http://127.0.0.1:8766. On Windows, `Start Review.cmd` launches it in the background. Set `LABOR_CARD_PYTHON` to use a specific Python.

1. Choose one or more original daily Labor Card PDFs and click **Review cards**.
   You can also pick a Thursday and click **Review downloaded week**, which reads PDFs saved by the extension under `Downloads/Labor Cards/YYYY-MM-DD`.
2. Click a finding to highlight its roster rows. Use **Verify roster** to fix a misread row, then recheck.
3. **Download marked-up cards** keeps the originals and adds highlights, PDF comments and a written review page after each card.

**Review rules** lets you toggle checks and set the closing time, doubles limit, earliest Bar/To Go start and AM/PM boundary. Settings are stored in the browser.

### Browser build (static site)

Requires Node.js 20+ and Python (only to download the pinned wheels).

```bash
cd web
npm ci
pip download --no-deps --only-binary=:all: --platform any --python-version 3.12 -d public/wheels -r wheels.txt
node build.mjs          # copies the analyzer and UI from ../local and bundles Pyodide + pdf.js
npx wrangler deploy     # optional: publish public/ as a Cloudflare static site
```

To try it without deploying, serve `web/public` with any static server.

### Chrome extension

1. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and select `extension/`.
2. Sign in to HotSchedules, click **Weekly Labor Cards**, choose the Thursday, untick any days you don't need, and download.

PDFs save to `Downloads/Labor Cards/<Thursday date>/`. The extension only attaches to the temporary HotSchedules tab it opens (Chrome shows a debugging banner while it prints). It does not read or store passwords. Printing has had limited end-to-end testing, so PDF layout may need adjusting for your account.

## Tests

```bash
cd local && python -m unittest test_analyzer      # rule tests
cd web && node test-new-rules.mjs                 # same rules inside Pyodide (after build)
cd extension && node test-days.cjs                # week/day selection logic
```

Two analyzer tests and the browser parity checks (`web/test-browser-runtime.mjs`, `web/verify-parity.py`) need real Labor Card PDFs. Point `LABOR_CARD_FIXTURES` at a folder of them, otherwise the tests skip. **Never commit real labor cards.** They contain employee names, and `.gitignore` blocks PDFs for this reason.

## Contributing

Issues and pull requests are welcome. Most useful:

- Rules your restaurant uses, as a switchable check with a unit test in `local/test_analyzer.py` built from synthetic rows (see the `row()` helper)
- Parsing fixes for Labor Card layouts that come out unreadable. Describe the layout, or share a fully anonymized sample.
- A combined weekly PDF export

Keep `local/` as the single source of truth. `web/build.mjs` copies the analyzer and UI from it, so edit `local/` and rebuild.

## License

MIT. See [LICENSE](LICENSE). Not affiliated with or endorsed by HotSchedules or Fourth.
