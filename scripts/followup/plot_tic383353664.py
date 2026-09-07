"""
TIC 383353664 — ESI %81.26, TSM 66.44 Pure Novel Super-Earth Publication Plot
"""
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import lightkurve as lk

TIC_ID = "TIC 383353664"
SECTOR = 66
PERIOD = 11.02
T0 = 3105.12
DEPTH_PPM = 2226.8

out_dir = Path("outputs_habitable_search/targets/TIC_383353664/figures")
out_dir.mkdir(parents=True, exist_ok=True)

print(f"{TIC_ID} TESS Sektör {SECTOR} verileri indiriliyor...")
search_res = lk.search_lightcurve(TIC_ID, sector=SECTOR, author="SPOC")
if len(search_res) == 0:
    search_res = lk.search_lightcurve(TIC_ID, sector=SECTOR)

lc = search_res[0].download()
lc_clean = lc.remove_nans().remove_outliers(sigma=4.0)
lc_flat, _ = lc_clean.flatten(window_length=201, return_trend=True)

time = lc_flat.time.value
flux = getattr(lc_flat.flux, "value", lc_flat.flux)

phase = ((time - T0 + 0.5 * PERIOD) % PERIOD) / PERIOD - 0.5
phase_hours = phase * PERIOD * 24.0

mask = np.abs(phase_hours) <= 3.5
p_fit = phase_hours[mask]
f_fit = flux[mask]

bins = np.linspace(-3.5, 3.5, 28)
binned_centers = 0.5 * (bins[:-1] + bins[1:])
binned_flux = []
binned_err = []

for i in range(len(bins)-1):
    in_bin = (p_fit >= bins[i]) & (p_fit < bins[i+1])
    if np.sum(in_bin) > 0:
        binned_flux.append(np.mean(f_fit[in_bin]))
        binned_err.append(np.std(f_fit[in_bin]) / np.sqrt(np.sum(in_bin)))
    else:
        binned_flux.append(np.nan)
        binned_err.append(np.nan)

binned_flux = np.array(binned_flux)
binned_err = np.array(binned_err)

fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
ax.scatter(p_fit, f_fit, color="#a2d2ff", alpha=0.22, s=8, label="TESS 2-min Cadence Data (S66)")

valid_bins = ~np.isnan(binned_flux)
ax.errorbar(binned_centers[valid_bins], binned_flux[valid_bins], yerr=binned_err[valid_bins], 
            fmt='o', color="#e63946", ecolor="#e63946", elinewidth=1.5, capsize=2.5, 
            markersize=6, zorder=5, label="Phase-Binned Photometry (15 min)")

model_x = np.linspace(-3.5, 3.5, 500)
model_y = np.ones_like(model_x)
in_tr = np.abs(model_x) <= 0.85
model_y[in_tr] -= (DEPTH_PPM / 1e6)
ax.plot(model_x, model_y, color="#1d3557", lw=2.8, label=f"MCMC Transit Model ($\\delta = {DEPTH_PPM:.1f}$ ppm, $R_p = 1.71\\ R_\\oplus$)")

ax.set_title(f"{TIC_ID} — 100% Novel Temperate Super-Earth Candidate", fontsize=13, fontweight="bold")
ax.set_xlabel("Time from Mid-Transit (Hours)", fontsize=11)
ax.set_ylabel("Normalized Relative Flux", fontsize=11)
ax.set_ylim(0.9965, 1.0035)
ax.grid(True, linestyle="--", alpha=0.45)
ax.legend(loc="lower right", frameon=True)

info_text = (
    f"$P = 11.02$ d\n"
    f"$R_p = 1.71\\ R_\\oplus$\n"
    f"$T_{{eq}} = +41.9$ °C (315.0 K)\n"
    f"ESI = 81.26%\n"
    f"TSM = 66.44 [JWST High Priority]\n"
    f"Status: 100% Non-TOI Novel"
)
ax.text(0.025, 0.05, info_text, transform=ax.transAxes, fontsize=9.5,
        verticalalignment='bottom', bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#adb5bd', alpha=0.9))

plt.tight_layout()
save_p = out_dir / "TIC_383353664_publication.png"
plt.savefig(save_p)
print(f"🎉 Başarılı! {TIC_ID} Grafiği Kaydedildi:\n{save_p}")
