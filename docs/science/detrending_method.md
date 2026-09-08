# Detrending method

Detrending removes low-frequency instrumental and stellar variability while
preserving transit-scale structure. The method, window and masking policy are
configuration inputs and are recorded in provenance.

Assumption: the baseline model is smooth over a transit duration. Over-aggressive
windows can attenuate shallow signals; this is measured by injection recovery.
Inputs are raw/quality-filtered flux and cadence metadata; output is normalized
flux plus masks and data completeness. Failure outcomes include high systematics
and insufficient baseline. Test coverage includes preprocessing regression and
injection recovery.