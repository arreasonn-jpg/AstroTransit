# False-positive risk method

The current FPP field is a heuristic risk proxy, not a Bayesian posterior.
`fpp_method` identifies its origin. It must be calibrated on labelled planet,
false-positive and quiet-star corpora using a holdout set.

Release metrics are Brier score, reliability curve, ECE, ROC-AUC and PR-AUC.
Missing corpus evidence produces null/not-evaluated metrics.