#!/usr/bin/env python3
"""
Standalone anomaly + FPP değerlendirme script'i.

Tek bir TESS transit adayı için:
- Light curve indirir
- Transit maskeleme ve residual hesaplar
- SPOC header'dan crowding / centroid çeker
- Gaia DR3 cone search ile komşu analizi yapar
- Anomaly detection + Simple FPP çalıştırır
- Sonucu ekrana + JSON dosyasına yazar

Kullanım:
    python scripts/followup/run_anomaly_fpp_evaluation.py \
        --tic 347299560 --sector 24 \
        --period 1.234 --t0 1800.123 --duration 0.08 --depth 0.0007

    # Opsiyonel:
        --rp-rs 0.026 --output-dir outputs_anomaly_fpp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from loguru import logger


# ──────────────────────────────────────────────────────────────
# Yardımcı: Light curve indirme
# ──────────────────────────────────────────────────────────────

def download_lc(tic_id: int, sector: int):
    """TESS SPOC light curve indir, lk.LightCurve döndür."""
    import lightkurve as lk

    search = lk.search_lightcurve(
        f"TIC {tic_id}",
        mission="TESS",
        author="SPOC",
        sector=sector,
        exptime=120,
    )

    if len(search) == 0:
        logger.error(f"TIC {tic_id} S{sector} için SPOC LC bulunamadı.")
        sys.exit(1)

    lc = search[0].download()
    logger.info(f"LC indirildi: TIC {tic_id} S{sector}, {len(lc.flux)} nokta")
    return lc


# ──────────────────────────────────────────────────────────────
# Yardımcı: SPOC header'dan crowding ve centroid
# ──────────────────────────────────────────────────────────────

def extract_spoc_metadata(lc) -> dict:
    """SPOC FITS header'dan CROWDSAP ve centroid bilgisi çeker."""

    meta = {}

    # CROWDSAP
    crowdsap = None
    for key in ["CROWDSAP", "crowdsap"]:
        val = lc.meta.get(key)
        if val is not None:
            try:
                crowdsap = float(val)
            except (ValueError, TypeError):
                pass

    meta["crowding_ratio"] = crowdsap
    logger.info(f"CROWDSAP = {crowdsap}")

    # Centroid shift — SPOC bazen MOM_CENTR1/2 veya POS_CORR1/2 verir
    # Basit proxy: varsa kullan, yoksa None
    centr1 = lc.meta.get("MOM_CENTR1")
    centr2 = lc.meta.get("MOM_CENTR2")

    if centr1 is not None and centr2 is not None:
        try:
            # pixel cinsinden offset → arcsec (TESS pixel ~21 arcsec)
            shift_pix = np.sqrt(float(centr1) ** 2 + float(centr2) ** 2)
            meta["centroid_shift_arcsec"] = shift_pix * 21.0
        except (ValueError, TypeError):
            meta["centroid_shift_arcsec"] = None
    else:
        meta["centroid_shift_arcsec"] = None

    logger.info(f"Centroid shift = {meta['centroid_shift_arcsec']}")

    # RA/DEC
    meta["ra"] = lc.meta.get("RA_OBJ")
    meta["dec"] = lc.meta.get("DEC_OBJ")

    # TESS magnitude hint
    tmag = None
    for key in ["TESSMAG", "TESSMAGN", "TMAG", "Tmag"]:
        val = lc.meta.get(key)
        if val is not None:
            try:
                tmag = float(val)
                break
            except (ValueError, TypeError):
                pass
    meta["tmag"] = tmag

    return meta


# ──────────────────────────────────────────────────────────────
# Yardımcı: Gaia DR3 cone search
# ──────────────────────────────────────────────────────────────

def gaia_neighbor_search(
    ra: float,
    dec: float,
    radius_arcsec: float = 60.0,
    target_mag_hint: float | None = None,
) -> dict:
    """
    Gaia DR3 cone search ile komşu bilgisi toplar.

    Self-source seçimi:
    - target_mag_hint verilmişse, parlaklık + yakınlık birlikte kullanılır
    - yoksa en yakın Gaia kaynağı self kabul edilir

    Returns
    -------
    dict
        gaia_neighbors_within_60arcsec
        brightest_neighbor_delta_mag
        nearest_neighbor_arcsec
        target_gaia_mag
        target_sep_arcsec
        self_source_id
        self_selection_method
        top_neighbors
    """

    result = {
        "gaia_neighbors_within_60arcsec": None,
        "brightest_neighbor_delta_mag": None,
        "nearest_neighbor_arcsec": None,
        "target_gaia_mag": None,
        "target_sep_arcsec": None,
        "self_source_id": None,
        "self_selection_method": None,
        "top_neighbors": [],
    }

    if ra is None or dec is None:
        logger.warning("RA/DEC eksik, Gaia sorgusu atlanıyor.")
        return result

    try:
        from astroquery.gaia import Gaia
        import astropy.units as u
        from astropy.coordinates import SkyCoord

        coord = SkyCoord(ra=float(ra), dec=float(dec), unit=(u.deg, u.deg), frame="icrs")

        Gaia.ROW_LIMIT = 200
        job = Gaia.cone_search_async(
            coordinate=coord,
            radius=u.Quantity(radius_arcsec, u.arcsec),
        )
        table = job.get_results()

        if table is None or len(table) == 0:
            result["gaia_neighbors_within_60arcsec"] = 0
            logger.info("Gaia cone search: 0 kaynak bulundu.")
            return result

        source_ids = np.array(table["source_id"])
        ras = np.array(table["ra"], dtype=float)
        decs = np.array(table["dec"], dtype=float)
        mags = np.array(table["phot_g_mean_mag"], dtype=float)

        gaia_coords = SkyCoord(
            ra=ras,
            dec=decs,
            unit=(u.deg, u.deg),
            frame="icrs",
        )
        seps_to_query = coord.separation(gaia_coords).arcsec

        # Self seçimi
        if target_mag_hint is not None and np.isfinite(float(target_mag_hint)):
            mag_hint = float(target_mag_hint)

            mag_penalty = np.where(
                np.isfinite(mags),
                np.abs(mags - mag_hint),
                99.0,
            )

            # yakınlık + magnitude uyumu birlikte
            score = (seps_to_query / 10.0) + mag_penalty
            self_idx = int(np.argmin(score))
            self_method = f"mag_hint({mag_hint:.3f})+separation"
        else:
            self_idx = int(np.argmin(seps_to_query))
            self_method = "nearest_to_query_center"

        self_coord = gaia_coords[self_idx]
        self_mag = float(mags[self_idx]) if np.isfinite(mags[self_idx]) else None
        self_sep = float(seps_to_query[self_idx])
        self_source_id = str(source_ids[self_idx])

        result["target_gaia_mag"] = self_mag
        result["target_sep_arcsec"] = self_sep
        result["self_source_id"] = self_source_id
        result["self_selection_method"] = self_method

        # Komşu uzaklıklarını artık self source'a göre hesapla
        seps_to_self = self_coord.separation(gaia_coords).arcsec

        neighbor_mask = np.ones(len(seps_to_self), dtype=bool)
        neighbor_mask[self_idx] = False

        n_neighbors = int(np.sum(neighbor_mask))
        result["gaia_neighbors_within_60arcsec"] = n_neighbors

        if n_neighbors == 0:
            logger.info(
                f"Gaia cone search: izole hedef. "
                f"self_sep={self_sep:.3f} arcsec, self_mag={self_mag}, method={self_method}"
            )
            return result

        neighbor_seps = seps_to_self[neighbor_mask]
        neighbor_mags = mags[neighbor_mask]
        neighbor_ids = source_ids[neighbor_mask]

        nearest_idx = int(np.argmin(neighbor_seps))
        result["nearest_neighbor_arcsec"] = float(neighbor_seps[nearest_idx])

        finite_neighbor_mags = neighbor_mags[np.isfinite(neighbor_mags)]
        if len(finite_neighbor_mags) > 0 and self_mag is not None:
            brightest_mag = float(np.nanmin(finite_neighbor_mags))
            result["brightest_neighbor_delta_mag"] = float(brightest_mag - self_mag)

        order = np.argsort(neighbor_seps)
        top_neighbors = []
        for idx in order[:10]:
            mag = neighbor_mags[idx]
            top_neighbors.append({
                "source_id": str(neighbor_ids[idx]),
                "sep_arcsec": float(neighbor_seps[idx]),
                "gmag": None if not np.isfinite(mag) else float(mag),
                "delta_mag": None if (self_mag is None or not np.isfinite(mag))
                             else float(mag - self_mag),
            })
        result["top_neighbors"] = top_neighbors

        logger.info(
            f"Gaia cone search: method={self_method}, "
            f"self_sep={self_sep:.3f} arcsec, self_mag={self_mag}, "
            f"neighbors={n_neighbors}, nearest={result['nearest_neighbor_arcsec']:.2f} arcsec, "
            f"delta_mag={result['brightest_neighbor_delta_mag']}"
        )

    except Exception as exc:
        logger.warning(f"Gaia cone search başarısız: {exc}")

    return result

    try:
        from astroquery.gaia import Gaia
        import astropy.units as u
        from astropy.coordinates import SkyCoord

        coord = SkyCoord(ra=float(ra), dec=float(dec), unit=(u.deg, u.deg), frame="icrs")

        Gaia.ROW_LIMIT = 200
        job = Gaia.cone_search_async(
            coordinate=coord,
            radius=u.Quantity(radius_arcsec, u.arcsec),
        )
        table = job.get_results()

        if table is None or len(table) == 0:
            result["gaia_neighbors_within_60arcsec"] = 0
            logger.info("Gaia cone search: 0 kaynak bulundu.")
            return result

        source_ids = np.array(table["source_id"])
        ras = np.array(table["ra"], dtype=float)
        decs = np.array(table["dec"], dtype=float)
        mags = np.array(table["phot_g_mean_mag"], dtype=float)

        gaia_coords = SkyCoord(
            ra=ras,
            dec=decs,
            unit=(u.deg, u.deg),
            frame="icrs",
        )
        separations = coord.separation(gaia_coords).arcsec

        # Hedef = cone center'a en yakın Gaia kaynağı
        self_idx = int(np.argmin(separations))
        target_sep = float(separations[self_idx])
        target_mag = float(mags[self_idx]) if np.isfinite(mags[self_idx]) else None

        result["target_sep_arcsec"] = target_sep
        result["target_gaia_mag"] = target_mag

        # Sadece bu satırı self kabul et
        neighbor_mask = np.ones(len(separations), dtype=bool)
        neighbor_mask[self_idx] = False

        n_neighbors = int(np.sum(neighbor_mask))
        result["gaia_neighbors_within_60arcsec"] = n_neighbors

        if n_neighbors == 0:
            logger.info(
                f"Gaia cone search: hedef izole, komşu yok. "
                f"self_sep={target_sep:.3f} arcsec, self_mag={target_mag}"
            )
            return result

        neighbor_seps = separations[neighbor_mask]
        neighbor_mags = mags[neighbor_mask]
        neighbor_ids = source_ids[neighbor_mask]

        # En yakın komşu
        nearest_idx = int(np.argmin(neighbor_seps))
        result["nearest_neighbor_arcsec"] = float(neighbor_seps[nearest_idx])

        # En parlak komşu Δmag
        finite_mag_mask = np.isfinite(neighbor_mags)
        if np.any(finite_mag_mask) and target_mag is not None:
            brightest_mag = float(np.nanmin(neighbor_mags[finite_mag_mask]))
            result["brightest_neighbor_delta_mag"] = float(brightest_mag - target_mag)

        # İlk 10 komşuyu yakınlığa göre sakla
        order = np.argsort(neighbor_seps)
        top_neighbors = []
        for idx in order[:10]:
            mag = neighbor_mags[idx]
            top_neighbors.append({
                "source_id": str(neighbor_ids[idx]),
                "sep_arcsec": float(neighbor_seps[idx]),
                "gmag": None if not np.isfinite(mag) else float(mag),
                "delta_mag": None if (target_mag is None or not np.isfinite(mag))
                             else float(mag - target_mag),
            })
        result["top_neighbors"] = top_neighbors

        logger.info(
            f"Gaia cone search: self_sep={target_sep:.3f} arcsec, "
            f"self_mag={target_mag}, neighbors={n_neighbors}, "
            f"nearest={result['nearest_neighbor_arcsec']:.2f} arcsec, "
            f"delta_mag={result['brightest_neighbor_delta_mag']}"
        )

    except Exception as exc:
        logger.warning(f"Gaia cone search başarısız: {exc}")

    return result


# ──────────────────────────────────────────────────────────────
# Yardımcı: Transit maskeleme ve residual
# ──────────────────────────────────────────────────────────────

def compute_transit_arrays(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    t0: float,
    duration: float,
    depth: float,
) -> dict:
    """
    Transit mask, phase, residual dizilerini hesaplar.

    Basit box-model residual kullanır.
    Mid-transit zamanları flux-weighted centroid ile hesaplanır.
    """

    # Phase
    phase = ((time - t0 + 0.5 * period) % period) - 0.5 * period
    phase_fraction = phase / period

    # Transit mask — 1.3x genişletilmiş süre (kenar noktalarını dahil et)
    half_dur = duration / 2.0
    half_dur_wide = half_dur * 1.3
    in_transit = np.abs(phase) < half_dur_wide

    # Basit box model (dar pencere kullan)
    model_flux = np.ones_like(flux)
    narrow_mask = np.abs(phase) < half_dur
    model_flux[narrow_mask] = 1.0 - depth

    residuals = flux - model_flux

    # Transit event ID'leri
    transit_times = t0 + np.arange(
        np.floor((time.min() - t0) / period),
        np.ceil((time.max() - t0) / period) + 1,
    ) * period

    event_ids = np.full(len(time), -1, dtype=int)
    for i, tc in enumerate(transit_times):
        mask_event = np.abs(time - tc) < half_dur_wide
        event_ids[mask_event] = i

    # OOT baseline
    baseline = float(np.nanmedian(flux[~in_transit])) if np.sum(~in_transit) > 5 else 1.0

    # Per-transit depths
    per_depths = []
    for eid in np.unique(event_ids):
        if eid < 0:
            continue
        emask = event_ids == eid
        if np.sum(emask) < 3:
            continue
        d = baseline - float(np.nanmedian(flux[emask]))
        if np.isfinite(d) and d > 0:
            per_depths.append(d)

    # Observed mid-transit times — flux-weighted centroid
    observed_midtimes = []
    for eid in np.unique(event_ids):
        if eid < 0:
            continue
        emask = event_ids == eid
        if np.sum(emask) < 3:
            continue

        eflux = flux[emask]
        etime = time[emask]

        # Ağırlık = baseline - flux (transit sırasında pozitif)
        weights = baseline - eflux
        weights = np.clip(weights, 0.0, None)

        if np.sum(weights) > 0:
            t_mid = float(np.sum(etime * weights) / np.sum(weights))
        else:
            t_mid = float(np.median(etime))

        observed_midtimes.append(t_mid)

    return {
        "time": time,
        "flux": flux,
        "phase": phase_fraction,
        "residuals": residuals,
        "in_transit_mask": in_transit,
        "transit_event_ids": event_ids,
        "per_transit_depths": np.array(per_depths, dtype=float),
        "observed_midtimes": np.array(observed_midtimes, dtype=float),
        "baseline": baseline,
    }


# ──────────────────────────────────────────────────────────────
# Ana fonksiyon
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Standalone anomaly + FPP değerlendirme"
    )
    parser.add_argument("--tic", type=int, required=True, help="TIC ID")
    parser.add_argument("--sector", type=int, required=True, help="Sektör")
    parser.add_argument("--period", type=float, required=True, help="Periyot (gün)")
    parser.add_argument("--t0", type=float, required=True, help="Epoch t0 (BTJD)")
    parser.add_argument("--duration", type=float, required=True, help="Transit süresi (gün)")
    parser.add_argument("--depth", type=float, required=True, help="Transit derinliği (relative)")
    parser.add_argument("--rp-rs", type=float, default=None, help="Rp/Rs (opsiyonel)")
    parser.add_argument("--target-mag", type=float, default=None, help="Hedef Tmag/Gmag ipucu (Gaia self-match için)")
    parser.add_argument("--output-dir", type=str, default="outputs_anomaly_fpp", help="Çıktı klasörü")
    parser.add_argument("--gaia-radius", type=float, default=60.0, help="Gaia cone search yarıçapı (arcsec)")

    args = parser.parse_args()

    target_id = f"TIC {args.tic}"
    logger.info(f"Anomaly+FPP evaluation başlıyor — {target_id} S{args.sector}")

    # ── 1) LC indir ──
    lc = download_lc(args.tic, args.sector)

    time_raw = np.array(lc.time.value, dtype=float)
    flux_raw = np.array(getattr(lc.flux, "value", lc.flux), dtype=float)
    flux_err_raw = np.array(getattr(lc.flux_err, "value", lc.flux_err), dtype=float)

    # NaN temizle
    valid = np.isfinite(time_raw) & np.isfinite(flux_raw)
    time = time_raw[valid]
    flux = flux_raw[valid]

    # Normalize
    med = np.nanmedian(flux)
    if med > 0:
        flux = flux / med

    logger.info(f"LC temizlendi: {len(time)} nokta")

    # ── 2) SPOC metadata ──
    spoc_meta = extract_spoc_metadata(lc)

    # ── 3) Gaia komşu arama ──
    target_mag_hint = args.target_mag
    if target_mag_hint is None:
        target_mag_hint = spoc_meta.get("tmag")

    gaia_result = gaia_neighbor_search(
        ra=spoc_meta.get("ra"),
        dec=spoc_meta.get("dec"),
        radius_arcsec=args.gaia_radius,
        target_mag_hint=target_mag_hint,
    )

    # ── 4) Transit dizileri hesapla ──
    arrays = compute_transit_arrays(
        time=time,
        flux=flux,
        period=args.period,
        t0=args.t0,
        duration=args.duration,
        depth=args.depth,
    )

    logger.info(
        f"Transit dizileri: "
        f"n_intransit={np.sum(arrays['in_transit_mask'])}, "
        f"n_events={len(arrays['per_transit_depths'])}, "
        f"n_midtimes={len(arrays['observed_midtimes'])}"
    )

    # ── 5) Anomaly analizi ──
    from astrotransit.quality.residual_analysis import ResidualAnalyzer
    from astrotransit.quality.transit_consistency import TransitConsistencyAnalyzer
    from astrotransit.quality.timing_analysis import TimingAnalyzer
    from astrotransit.quality.anomaly_scorer import AnomalyScorer

    residual_report = ResidualAnalyzer().analyze(
        target_id=target_id,
        sector=args.sector,
        time=arrays["time"],
        residuals=arrays["residuals"],
        in_transit_mask=arrays["in_transit_mask"],
    )
    logger.info(f"Residual: {residual_report.summary()}")

    transit_report = TransitConsistencyAnalyzer().analyze(
        target_id=target_id,
        sector=args.sector,
        phase=arrays["phase"],
        flux=arrays["flux"],
        in_transit_mask=arrays["in_transit_mask"],
        transit_event_ids=arrays["transit_event_ids"],
        per_transit_depths=arrays["per_transit_depths"],
    )
    logger.info(f"Transit consistency: {transit_report.summary()}")

    timing_report = TimingAnalyzer().analyze(
        target_id=target_id,
        sector=args.sector,
        period=args.period,
        observed_midtimes=arrays["observed_midtimes"],
        t0=args.t0,
    )
    logger.info(f"Timing: {timing_report.summary()}")

    anomaly_report = AnomalyScorer().score(
        residual_report=residual_report,
        transit_report=transit_report,
        timing_report=timing_report,
    )
    logger.info(f"Anomaly: {anomaly_report.summary()}")

    # ── 6) FPP hesabı ──
    from astrotransit.quality.fpp import SimpleFPPCalculator, FPPReportWriter

    # Even/odd depth ve v-shape — transit_report details'tan çek
    td = transit_report.details or {}
    odd_depth = td.get("odd_depth_median")
    even_depth = td.get("even_depth_median")
    v_shape = None
    for t in transit_report.tests:
        if t.name == "v_shape_metric" and t.value is not None:
            v_shape = float(t.value)
            break

    # Secondary eclipse — basit proxy: 0.5 fazda median depth
    phase_arr = arrays["phase"]
    flux_arr = arrays["flux"]
    secondary_mask = (np.abs(phase_arr - 0.5) < 0.03) | (np.abs(phase_arr + 0.5) < 0.03)
    if np.sum(secondary_mask) >= 3:
        sec_depth = float(arrays["baseline"] - np.nanmedian(flux_arr[secondary_mask]))
        sec_depth = max(sec_depth, 0.0)
    else:
        sec_depth = 0.0

    fpp_report = SimpleFPPCalculator().calculate(
        target_id=target_id,
        sector=args.sector,
        primary_depth=args.depth,
        odd_depth=odd_depth,
        even_depth=even_depth,
        v_shape_score=v_shape,
        secondary_depth=sec_depth,
        n_transits=len(arrays["per_transit_depths"]),
        centroid_shift_arcsec=spoc_meta.get("centroid_shift_arcsec"),
        crowding_ratio=spoc_meta.get("crowding_ratio"),
        gaia_neighbors_within_60arcsec=gaia_result.get("gaia_neighbors_within_60arcsec"),
        brightest_neighbor_delta_mag=gaia_result.get("brightest_neighbor_delta_mag"),
        nearest_neighbor_arcsec=gaia_result.get("nearest_neighbor_arcsec"),
    )
    logger.info(f"FPP: {fpp_report.summary()}")

    # ── 7) Sonuçları birleştir ve yaz ──
    output = {
        "target_id": target_id,
        "tic_id": args.tic,
        "sector": args.sector,
        "parameters": {
            "period": args.period,
            "t0": args.t0,
            "duration": args.duration,
            "depth": args.depth,
            "rp_rs": args.rp_rs,
        },
        "spoc_metadata": {
            "crowding_ratio": spoc_meta.get("crowding_ratio"),
            "centroid_shift_arcsec": spoc_meta.get("centroid_shift_arcsec"),
            "ra": spoc_meta.get("ra"),
            "dec": spoc_meta.get("dec"),
            "tmag": spoc_meta.get("tmag"),
            "target_mag_hint_used": target_mag_hint,
        },
        "gaia_neighbors": gaia_result,
        "anomaly": {
            "residual": residual_report.to_dict(),
            "transit_consistency": transit_report.to_dict(),
            "timing": timing_report.to_dict(),
            "combined": anomaly_report.to_dict(),
        },
        "fpp": fpp_report.to_dict(),
    }

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    json_path = outdir / f"TIC_{args.tic}_S{args.sector}_anomaly_fpp.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"JSON yazıldı: {json_path}")

    # FPP text raporu
    txt_path = outdir / f"TIC_{args.tic}_S{args.sector}_fpp_report.txt"
    FPPReportWriter().write_text(fpp_report, txt_path)

    # ── 8) Özet ──
    print("\n" + "=" * 72)
    print(f"ANOMALY + FPP EVALUATION — {target_id} S{args.sector}")
    print("=" * 72)
    print(f"Residual          : {residual_report.flag} (score={residual_report.score:.3f})")
    print(f"Transit Consistency: {transit_report.flag} (score={transit_report.score:.3f})")
    print(f"Timing            : {timing_report.flag} (score={timing_report.score:.3f})")
    print(f"Anomaly Combined  : {anomaly_report.anomaly_flag} (score={anomaly_report.anomaly_score:.3f})")
    print(f"  Action          : {anomaly_report.recommended_action}")
    print("-" * 72)
    print(f"P(EB)             : {fpp_report.p_eb:.4f}")
    print(f"P(BEB)            : {fpp_report.p_beb:.4f}")
    print(f"P(NEB)            : {fpp_report.p_neb:.4f}")
    print(f"Simple FPP        : {fpp_report.fpp:.4f}")
    print(f"P(planet) proxy   : {fpp_report.p_planet:.4f}")
    print(f"Dominant scenario : {fpp_report.dominant_scenario}")
    print(f"Confidence        : {fpp_report.confidence}")
    print(f"  Action          : {fpp_report.recommended_action}")
    print("-" * 72)
    print(f"CROWDSAP          : {spoc_meta.get('crowding_ratio')}")
    print(f"Centroid shift    : {spoc_meta.get('centroid_shift_arcsec')}")
    print(f"Gaia self sep     : {gaia_result.get('target_sep_arcsec')}")
    print(f"Gaia self Gmag    : {gaia_result.get('target_gaia_mag')}")
    print(f"Gaia neighbors    : {gaia_result.get('gaia_neighbors_within_60arcsec')}")
    print(f"Nearest neighbor  : {gaia_result.get('nearest_neighbor_arcsec')}")
    print(f"Delta mag         : {gaia_result.get('brightest_neighbor_delta_mag')}")
    print("=" * 72)
    print(f"Output: {json_path}")
    print(f"Output: {txt_path}")


if __name__ == "__main__":
    main()
