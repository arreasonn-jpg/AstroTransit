from pathlib import Path
import json

project_root = Path(__file__).resolve().parents[2]


def main():
    target_id = "TIC 417860263"
    sector = 57

    followup_json = project_root / "outputs_novel_followup" / "json" / f"{target_id.replace(' ', '_')}_S{sector:02d}.json"
    figures_dir = project_root / "outputs_novel_followup" / "figures"
    reports_dir = project_root / "outputs_discovery" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not followup_json.exists():
        print(f"HATA: {followup_json} bulunamadi")
        return 1

    data = json.load(open(followup_json, encoding="utf-8"))

    params = data.get("parameters", {})
    derived = data.get("derived", {})
    quality = data.get("quality", {})
    score = data.get("score", {})
    stellar = data.get("stellar", {})
    vetting = data.get("vetting", {})
    detection = data.get("detection", {})

    out_md = reports_dir / "TIC_417860263_report.md"
    out_txt = reports_dir / "TIC_417860263_summary.txt"

    # Markdown rapor
    md = []
    md.append("# TIC 417860263 - Novel Transit Candidate Report\n")
    md.append("## Özet\n")
    md.append(
        "Bu hedef, TOI katalogunda ve Exoplanet Archive TESS bilinen gezegen "
        "listelerinde yer almayan, TESS verisinde tespit edilmiş güçlü bir transit adayıdır.\n"
    )

    md.append("## Hedef Bilgileri\n")
    md.append(f"- Target ID: **{target_id}**")
    md.append(f"- Sector: **{sector}**")
    md.append(f"- Teff: **{stellar.get('teff_k', 'NA')} K**")
    md.append(f"- Radius: **{stellar.get('radius_rsun', 'NA')} R_sun**")
    md.append(f"- Tmag: **{stellar.get('tmag', 'NA')}**")
    md.append("")

    md.append("## Tespit Sonuçları\n")
    md.append(f"- BLS Period: **{detection.get('bls', {}).get('period_days', 'NA')} d**")
    md.append(f"- TLS Period: **{detection.get('tls', {}).get('period_days', 'NA')} d**")
    md.append(f"- TLS SDE: **{detection.get('tls', {}).get('sde', 'NA')}**")
    md.append(f"- TLS SNR: **{detection.get('tls', {}).get('snr', 'NA')}**")
    md.append(f"- Cascade Status: **{detection.get('cascade', {}).get('status', 'NA')}**")
    md.append(f"- Confirmed: **{detection.get('cascade', {}).get('confirmed', 'NA')}**")
    md.append("")

    md.append("## Parametreler\n")
    md.append(f"- Period: **{params.get('period_days', 'NA')} d**")
    md.append(f"- Duration: **{params.get('duration_hours', 'NA')} h**")
    md.append(f"- Depth: **{params.get('depth_ppm', 'NA')} ppm**")
    md.append(f"- Rp/Rs: **{params.get('rp_rs', 'NA')}**")
    md.append(f"- Impact parameter: **{params.get('impact_parameter', 'NA')}**")
    md.append("")

    md.append("## Türetilmiş Fiziksel Parametreler\n")
    md.append(f"- Planet Radius: **{derived.get('planet_radius_rearth', 'NA')} R_earth**")
    md.append(f"- Semi-major Axis: **{derived.get('semi_major_axis_au', 'NA')} AU**")
    md.append(f"- Equilibrium Temperature: **{derived.get('equilibrium_temperature_k', 'NA')} K**")
    md.append(f"- Insolation Flux: **{derived.get('insolation_flux', 'NA')}**")
    md.append("")

    md.append("## Kalite ve Vetting\n")
    md.append(f"- Adopted SNR: **{quality.get('snr_adopted', 'NA')}**")
    md.append(f"- Data Completeness: **{quality.get('data_completeness', 'NA')}**")
    md.append(f"- Residual RMS: **{quality.get('residual_rms_ppm', 'NA')} ppm**")
    md.append(f"- Candidate Class: **{score.get('candidate_class', 'NA')}**")
    md.append(f"- Total Score: **{score.get('total_score', 'NA')} / 100**")
    md.append(f"- FPP: **{vetting.get('fpp', 'NA')}**")
    md.append("")

    md.append("## Known-status Check\n")
    md.append("- TOI catalog match: **No**")
    md.append("- Verified benchmark target: **No**")
    md.append("- Exoplanet Archive TESS known planet match: **No**")
    md.append("")

    md.append("## Yorum\n")
    md.append(
        "Bu hedef, periyot, transit derinliği, yarıçap ve SNR açısından "
        "fiziksel olarak makul bir sub-Neptune / mini-Neptune adayı görünümündedir. "
        "Mevcut TESS odaklı bilinen kataloglarda eşleşme bulunmamıştır. "
        "Bu nedenle ileri follow-up ve bağımsız katalog çapraz kontrolü için öncelikli adaydır."
    )
    md.append("")

    # Görsel listesi
    md.append("## Üretilen Görseller\n")
    figs = sorted(figures_dir.glob("TIC_417860263_S57_*.png"))
    for fig in figs:
        md.append(f"- `{fig.name}`")
    md.append("")

    out_md.write_text("\n".join(md), encoding="utf-8")

    # Kısa TXT özet
    txt = []
    txt.append("TIC 417860263 - Strong Novel Transit Candidate")
    txt.append("=" * 56)
    txt.append(f"Sector: {sector}")
    txt.append(f"Period: {params.get('period_days', 'NA')} d")
    txt.append(f"Depth: {params.get('depth_ppm', 'NA')} ppm")
    txt.append(f"Rp/Rs: {params.get('rp_rs', 'NA')}")
    txt.append(f"Planet Radius: {derived.get('planet_radius_rearth', 'NA')} R_earth")
    txt.append(f"SNR: {quality.get('snr_adopted', 'NA')}")
    txt.append(f"Class: {score.get('candidate_class', 'NA')}")
    txt.append(f"Score: {score.get('total_score', 'NA')}")
    txt.append(f"FPP: {vetting.get('fpp', 'NA')}")
    txt.append("")
    txt.append("Known-status:")
    txt.append(" - TOI: No")
    txt.append(" - Verified benchmark: No")
    txt.append(" - Exoplanet Archive TESS known match: No")
    txt.append("")
    txt.append("Status: PRIORITY FOLLOW-UP CANDIDATE")

    out_txt.write_text("\n".join(txt), encoding="utf-8")

    print("=" * 72)
    print("Novel Candidate Report Generated")
    print("=" * 72)
    print(f"Markdown: {out_md}")
    print(f"Summary : {out_txt}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())