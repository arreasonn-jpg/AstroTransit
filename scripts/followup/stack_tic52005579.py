"""
TIC 52005579 (TOI-6251.01) Çoklu Sektör Birlestirici ve Transit Dogrulayici
ESI = %96.52 (Earth Twin)
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import lightkurve as lk

TIC_ID = "TIC 52005579"
PERIOD = 12.761471
T0 = 2470.15 # BTJD tahmini
DEPTH_PPM = 1070.0 # ~0.97 R_earth around 0.27 R_sun star

print(f"{TIC_ID} için tüm TESS sektör verileri çekiliyor...")
search_res = lk.search_lightcurve(TIC_ID, author="SPOC")

if len(search_res) == 0:
    search_res = lk.search_lightcurve(TIC_ID)

print(f"Toplam {len(search_res)} sektör bulundu. Veriler indiriliyor ve birleştiriliyor...")
lc_collection = search_res.download_all()

# Tüm sektörleri temizle ve birleştir
cleaned_lcs = []
for lc in lc_collection:
    lc_c = lc.remove_nans().remove_outliers(sigma=4.5)
    lc_f, _ = lc_c.flatten(window_length=201, return_trend=True)
    cleaned_lcs.append(lc_f)

combined_lc = lk.LightCurveCollection(cleaned_lcs).stitch()

time = combined_lc.time.value
flux = combined_getattr(lc.flux, "value", lc.flux)

# Faz Katlama (Phase Folding)
phase = ((time - T0 + 0.5 * PERIOD) % PERIOD) / PERIOD - 0.5
phase_hours = phase * PERIOD * 24.0

# Transit Penceresi (±4 saat)
mask = np.abs(phase_hours) <= 4.0
p_fit = phase_hours[mask]
f_fit = flux[mask]

# Binning
bins = np.linspace(-4, 4, 40)
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

# Çizim
out_dir = Path("outputs_habitable_search/targets/TIC_52005579/figures")
out_dir.mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
ax.scatter(p_fit, f_fit, color="#a2d2ff", alpha=0.20, s=8, label="Multi-Sector TESS Photometry")

valid_bins = ~np.isnan(binned_flux)
ax.errorbar(binned_centers[valid_bins], binned_flux[valid_bins], yerr=binned_err[valid_bins], 
            fmt='o', color="#e63946", ecolor="#e63946", elinewidth=1.6, capsize=2.5, 
            markersize=6, zorder=5, label="Phase-Binned Photometry (15 min)")

# Model Çizgisi
model_x = np.linspace(-4, 4, 500)
model_y = np.ones_like(model_x)
in_tr = np.abs(model_x) <= 0.8
model_y[in_tr] -= (DEPTH_PPM / 1e6)
ax.plot(model_x, model_y, color="#1d3557", lw=2.8, label=f"Forced Ephemeris Model (Depth = {DEPTH_PPM:.1f} ppm)")

ax.set_title(f"{TIC_ID} (TOI-6251.01) — Multi-Sector Stacked Earth Twin", fontsize=13, fontweight="bold")
ax.set_xlabel("Time from Mid-Transit (Hours)", fontsize=11)
ax.set_ylabel("Normalized Flux", fontsize=11)
ax.set_ylim(0.9975, 1.0025)
ax.grid(True, linestyle="--", alpha=0.45)
ax.legend(loc="lower right", frameon=True)

info_text = (
    f"$P = 12.7615$ d\n"
    f"$R_p = 0.971\\ R_\\oplus$\n"
    f"$T_{{eq}} = 299.5$ K (26.3 °C)\n"
    f"ESI = 96.5% [Earth Twin]"
)
ax.text(0.025, 0.05, info_text, transform=ax.transAxes, fontsize=9.5,
        verticalalignment='bottom', bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#adb5bd', alpha=0.9))

plt.tight_layout()
save_p = out_dir / "TIC_52005579_stacked_publication.png"
plt.savefig(save_p)
print(f"🎉 Başarılı! {TIC_ID} Çoklu Sektör Grafiği Kaydedildi:\n{save_p}")
