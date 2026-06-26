# Power BI dashboard - build guide

A step-by-step to build the dashboard from the exported CSVs. No prior Power BI
needed. Target: a single-page dashboard that tells the project's story -
*models predict winners well, but cannot beat the Vegas line*.

Regenerate the data anytime with `python src/06_export_powerbi.py`.

---

## 0. Install Power BI Desktop (once)
Free. Microsoft Store -> search **"Power BI Desktop"** -> Install. (Windows only,
which you have.) Open it and close the splash/sign-in popups.

## 1. Load the five CSVs
Home tab -> **Get data** -> **Text/CSV**. Load each file from `powerbi/exports/`:

| File | What it is |
| --- | --- |
| `games.csv` | one row per test game (the main fact table) |
| `win_metrics.csv` | accuracy / AUC / Brier per model |
| `margin_mae.csv` | margin error per model |
| `ats_segments.csv` | ATS hit% + ROI by segment |
| `calibration.csv` | predicted vs observed win probability |

For each: click **Load** (not Transform). When loading `games.csv`, check that
`game_date` came in as a **Date** type (in the right-hand Data pane, click the
column and set Column tools -> Data type = Date if needed).

> You do **not** need to create relationships between tables - every visual below
> uses a single table.

## 2. Create five measures (Modeling -> New measure)
Click the `games` table first, then add each (formula bar):

```DAX
ATS Hit % = AVERAGE(games[model_ats_win])
Model Win Acc % = AVERAGE(games[model_win_correct])
Vegas Win Acc % = AVERAGE(games[vegas_win_correct])
Total Profit (units) = SUM(games[unit_profit])
ROI % = DIVIDE([Total Profit (units)], COUNTROWS(games))
```
Select each %-measure -> Measure tools -> **Format = Percentage**, 1 decimal.
(`ATS Hit %`, `Model/Vegas Win Acc %`, `ROI %`.)

Add one more for the cumulative-profit line:
```DAX
Cumulative Profit =
CALCULATE(
    SUM(games[unit_profit]),
    FILTER(ALLSELECTED(games[game_date]), games[game_date] <= MAX(games[game_date]))
)
```

## 3. Build the page

**Title** - Insert -> Text box: *"Can a model beat the Vegas line? (NBA 2024-26)"*

**KPI cards** (Visualizations -> **Card**, one each, across the top):
- Games = drag `games[game_id]` -> set to **Count**
- `Model Win Acc %`
- `Vegas Win Acc %`  ← will read higher than the model: the key contrast
- `ATS Hit %`
- `ROI %`  ← negative: the punchline

**Visual 1 - Win accuracy: model vs market** (Clustered column chart)
- Source table: `win_metrics`
- X axis: `model` · Y: `accuracy`
- Title: "Vegas predicts winners better than our models"

**Visual 2 - ATS hit % by segment** (Clustered bar chart)
- Source: `ats_segments`
- Y axis: `segment` · X: `ats_hit_pct`
- Add a slicer (see below) on `seg_group` so you can flip between Spread size /
  Favorite / Season stage / Back-to-back
- **Add the breakeven line:** select the visual -> **Analytics** pane (magnifying
  glass) -> **Constant line** -> Value **52.4** -> name it "Breakeven", red, dashed.
- Title: "No segment clears the 52.4% breakeven"

**Visual 3 - Calibration** (Line chart)
- Source: `calibration`
- X axis: `predicted` · Y: `observed` · Legend: `model`
- Add an Analytics constant line is not ideal here; instead the closer each line
  hugs the diagonal, the better calibrated. Title: "Calibration: Vegas hugs the diagonal"

**Visual 4 - Cumulative betting P&L** (Line chart)
- Source: `games`
- X axis: `game_date` · Y: `Cumulative Profit`
- Title: "Betting the model loses money over time" (trends downward)

**Visual 5 - Margin error** (Clustered column)
- Source: `margin_mae` · X: `model` · Y: `mae`
- Title: "Vegas spread has the lowest error"

**Slicers** (Visualizations -> **Slicer**), add 2-3 from `games`:
- `season`, `favorite_side`, `spread_bucket`
- Plus one slicer on `ats_segments[seg_group]` to drive Visual 2.

## 4. Polish
- View -> **Themes** -> pick a clean one (e.g. "Executive").
- Align visuals on a grid; give each a short title; turn off chart-junk
  (Format -> turn off gridlines you don't need).
- File -> Save As -> `powerbi/NBA_Vegas_Dashboard.pbix`.

## 5. Add a screenshot to the repo (nice touch)
With the dashboard open, Windows **Snipping Tool** (Win+Shift+S) -> capture the
page -> save as `powerbi/dashboard.png`. Then it can be embedded in the README so
the dashboard is visible without opening Power BI.
