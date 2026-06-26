# Phase 3 - Error analysis & hidden variance

## 1. How much of an NBA game is even predictable?

- SD of actual home margin: **16.4 pts** (total variance 267).
- Vegas line explains **28.1%** of margin variance; residual SD = **13.9 pts**.
- Our XGBoost explains **19.3%**; residual SD = **14.7 pts**.
- => Even the market leaves a ~**14-point** per-game noise floor. That is the *hidden variance*: injuries, rotations, foul trouble, and shooting luck that no pre-game model sees.



## 2. Is any segment beatable? (52.4% = breakeven)

No slice clears the vig with any margin; ATS hovers at ~50% everywhere.

```
   seg_group                 seg  games  ats_hit_pct  model_mae  vegas_mae  roi_pct
 spread size        pickem (0-3)    450         49.6      11.93      11.52     -5.3
 spread size         small (3-7)    743         49.0      11.44      10.89     -6.5
 spread size          mid (7-11)    514         50.4      11.08      10.29     -3.8
 spread size           big (11+)    427         48.0      11.71      10.43     -8.4
    favorite        away favored    870         47.5      11.69      10.73     -9.3
    favorite        home favored   1264         50.5      11.39      10.82     -3.6
back-to-back         away on B2B    276         47.5      11.32      10.85     -9.3
back-to-back         home on B2B    255         50.2      12.11      11.45     -4.2
back-to-back        neither/both   1603         49.4      11.45      10.67     -5.7
season stage    early (gm 10-20)    320         51.9      10.56      10.26     -0.9
season stage         mid (20-45)    739         50.2      11.68      10.99     -4.2
season stage          late (45+)   1075         47.8      11.68      10.81     -8.7
  game total high total (>= 220)   1799         49.2      11.38      10.68     -6.1
  game total   low total (< 220)    335         49.3      12.20      11.34     -5.9
```

## 3. Where is error largest?

Prediction error grows with spread size (blowout games are noisier): {'pickem (0-3)': 11.5, 'small (3-7)': 10.9, 'mid (7-11)': 10.3, 'big (11+)': 10.4}. Big favorites invite garbage time and resting starters, adding variance the line cannot fully anticipate.


_Limitation:_ this dataset has only closing lines (no opening lines), so closing-line-value and line-movement tests are out of scope.
