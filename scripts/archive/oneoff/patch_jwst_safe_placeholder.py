from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
jwst_file = project_root / "astrotransit" / "pipelines" / "jwst_pipeline.py"


def main():
    if not jwst_file.exists():
        print("HATA: jwst_pipeline.py bulunamadi")
        return 1

    backup = jwst_file.with_suffix(".py.placeholder_backup")
    shutil.copy(jwst_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = jwst_file.read_text(encoding="utf-8")
    changed = False

    # Observation result dataclass alanlari
    old = """    detrended: Optional[JWSTDetrendedData] = None
    fit_result: Optional[MAPFitResult] = None
    noise_ppm: float = 0.0
    success: bool = False
    error: str = """""
    new = """    detrended: Optional[JWSTDetrendedData] = None
    fit_result: Optional[MAPFitResult] = None
    noise_ppm: Optional[float] = None
    fit_status: str = "placeholder"
    scientific_ready: bool = False
    success: bool = False
    error: str = """""
    if old in content:
        content = content.replace(old, new)
        print("OK jwst dataclass: safe placeholder alanlari eklendi")
        changed = True

    # Placeholder process sonucu
    old = """        obs_result.success = True
        obs_result.error = "placeholder — veri işleme henüz implemente edilmedi"

        return obs_result"""
    new = """        obs_result.success = True
        obs_result.fit_status = "placeholder"
        obs_result.scientific_ready = False
        obs_result.noise_ppm = None
        obs_result.error = "placeholder - veri isleme henuz implemente edilmedi"

        return obs_result"""
    if old in content:
        content = content.replace(old, new)
        print("OK jwst placeholder sonuc guvenli hale getirildi")
        changed = True

    # observations_processed sayimi scientific_ready ile olsun
    old = """                if obs_result.success:
                    result.observations_processed += 1"""
    new = """                if obs_result.success and getattr(obs_result, "scientific_ready", False):
                    result.observations_processed += 1"""
    if old in content:
        content = content.replace(old, new)
        print("OK jwst progress sayimi scientific_ready bazli oldu")
        changed = True

    if changed:
        jwst_file.write_text(content, encoding="utf-8")
        print("OK JWST pipeline kaydedildi")
    else:
        print("BILGI JWST icin degisiklik gerekmedi")

    ast.parse(jwst_file.read_text(encoding="utf-8"))
    print("OK Python sozdizimi gecerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())