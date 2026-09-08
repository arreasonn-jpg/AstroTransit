# Parameter inference

Point estimates and posterior estimates are distinct. A posterior is marked
`mcmc_quality=PASS` only for R-hat < 1.01, bulk ESS >= 400 and zero divergences.
The optional modeling environment must install the `.[modeling]` extra, which
includes PyMC, ArviZ, batman and exoplanet; MAP-only operation does not claim a
posterior.
Otherwise the result carries `MCMC_FAILED_DIAGNOSTICS` and must not be described
as a calibrated uncertainty.

Validation uses injected truth to measure bias, scatter, RMSE and 50/68/90/95%
interval coverage. All unavailable intervals remain null.