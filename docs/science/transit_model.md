# Transit model

The model describes a periodic occultation through period, epoch, radius ratio,
impact parameter, duration and limb-darkening parameters. MAP is an initializer;
MCMC is accepted only when the diagnostic gate passes.

Inputs include detrended flux and stellar parameters. Outputs include fitted
parameters, derived radius and uncertainty metadata. Model assumptions (limb
darkening, circularity and stellar priors) are configuration and versioned.
Non-convergence is never converted to a valid fit.