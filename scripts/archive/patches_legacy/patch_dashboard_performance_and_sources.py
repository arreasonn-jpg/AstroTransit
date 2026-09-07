from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
dashboard_file = project_root / "dashboard" / "app.py"


def main():
    if not dashboard_file.exists():
        print("HATA: dashboard/app.py bulunamadi")
        return 1

    backup = dashboard_file.with_suffix(".py.perf_backup")
    shutil.copy(dashboard_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = dashboard_file.read_text(encoding="utf-8")
    changed = False

    # ────────────────────────────────────────────────────────
    # 1. Cache helper fonksiyonlari ekle
    # ────────────────────────────────────────────────────────
    if "@st.cache_data" not in content:
        insert_after = "import streamlit as st\n"
        cache_block = '''

@st.cache_data(show_spinner=False)
def load_parquet_cached(path_str: str):
    import pandas as pd
    return pd.read_parquet(Path(path_str))

@st.cache_data(show_spinner=False)
def load_json_cached(path_str: str):
    import json
    with open(Path(path_str), "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(show_spinner=False)
def list_json_candidates():
    roots = [Path("outputs/json"), Path("outputs_top10/json"), Path("outputs_wsl_mcmc/json")]
    files = []
    for root in roots:
        if root.exists():
            files.extend([f for f in root.glob("*.json") if f.name != "all_candidates.jsonl"])
    uniq = {}
    for f in files:
        uniq[f.name] = f
    return sorted(uniq.values(), key=lambda x: x.name)

@st.cache_data(show_spinner=False)
def find_candidate_images(source_id: str, sector: int):
    safe_id = source_id.replace(" ", "_").replace("/", "_")
    sector_str = f"S{sector:02d}"
    roots = [
        Path("outputs/figures"),
        Path("outputs_top10/figures"),
        Path("outputs_wsl_mcmc/figures"),
    ]
    images = []
    for root in roots:
        if root.exists():
            images.extend(sorted(root.glob(f"{safe_id}_{sector_str}_*.png")))
    uniq = {}
    for img in images:
        uniq[img.name] = img
    return list(sorted(uniq.values(), key=lambda p: p.name))

'''
        content = content.replace(insert_after, insert_after + cache_block)
        print("OK dashboard cache helper fonksiyonlari eklendi")
        changed = True

    # ────────────────────────────────────────────────────────
    # 2. Parquet okuma cache ile
    # ────────────────────────────────────────────────────────
    old = "        df = pd.read_parquet(path)"
    new = "        df = load_parquet_cached(str(path))"
    if old in content:
        content = content.replace(old, new)
        print("OK parquet okuma cache hale getirildi")
        changed = True

    # ────────────────────────────────────────────────────────
    # 3. Candidate detail: JSON listesi coklu kaynaktan
    # ────────────────────────────────────────────────────────
    old_json_block = '''    json_dir = Path("outputs/json")

    if not json_dir.exists():
        st.warning("JSON dizini bulunamadi. Once bir analiz calistirin.")
        return

    json_files = sorted([f for f in json_dir.glob("*.json") if f.name != "all_candidates.jsonl"])
    if not json_files:
        st.warning("Henuz JSON raporu yok.")
        return'''
    new_json_block = '''    json_files = list_json_candidates()
    if not json_files:
        st.warning("Henuz JSON raporu yok. Once bir analiz calistirin.")
        return'''
    if old_json_block in content:
        content = content.replace(old_json_block, new_json_block)
        print("OK candidate detail json kaynaklari genisletildi")
        changed = True

    # ────────────────────────────────────────────────────────
    # 4. JSON okuma cache ile
    # ────────────────────────────────────────────────────────
    old_json_read = '''        import json
        try:
            with open(selected, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            st.error(f"JSON okuma hatasi: {e}")
            return'''
    new_json_read = '''        try:
            data = load_json_cached(str(selected))
        except Exception as e:
            st.error(f"JSON okuma hatasi: {e}")
            return'''
    if old_json_read in content:
        content = content.replace(old_json_read, new_json_read)
        print("OK json okuma cache hale getirildi")
        changed = True

    # ────────────────────────────────────────────────────────
    # 5. Gorsel yukleme: coklu kaynak + lazy selectbox
    # ────────────────────────────────────────────────────────
    old_image_block = '''        possible_dirs = [
            Path("outputs/figures"),
            Path(data.get("files", {}).get("figure_dir", "")),
        ]

        found_images = []
        for fig_dir in possible_dirs:
            if fig_dir.exists() and fig_dir.is_dir():
                matching = sorted(fig_dir.glob(f"{safe_id}_{sector_str}_*.png"))
                if matching:
                    found_images = matching
                    break

        if found_images:
            st.success(f"{len(found_images)} gorsel bulundu")
            image_order = {"summary": 1, "lightcurve": 2, "folded": 3,
                           "bls_tls": 4, "residuals": 5, "timing": 6, "scorecard": 7}
            found_images.sort(key=lambda p: next((v for k, v in image_order.items() if k in p.stem), 999))
            for img in found_images:
                st.markdown(f"**{img.stem}**")
                st.image(str(img), use_container_width=True)
                st.divider()
        else:
            st.warning(f"`{safe_id}_{sector_str}_*.png` icin gorsel bulunamadi.")
            fallback = Path("outputs/figures")
            if fallback.exists():
                all_pngs = list(fallback.glob("*.png"))
                if all_pngs:
                    st.info(f"outputs/figures/ icinde {len(all_pngs)} gorsel var:")
                    for p in all_pngs[:10]:
                        st.text(f"  - {p.name}")'''
    new_image_block = '''        found_images = find_candidate_images(source_id, sector)

        if found_images:
            st.success(f"{len(found_images)} gorsel bulundu")

            image_order = {
                "summary": 1, "lightcurve": 2, "folded": 3,
                "bls_tls_comparison": 4, "bls_tls": 4,
                "residuals": 5, "timing": 6, "scorecard": 7,
            }
            found_images.sort(
                key=lambda p: next(
                    (v for k, v in image_order.items() if k in p.stem),
                    999,
                )
            )

            image_names = [img.stem for img in found_images]
            selected_idx = st.selectbox(
                "Gorsel sec",
                range(len(image_names)),
                format_func=lambda i: image_names[i],
            )
            if selected_idx is not None:
                st.image(str(found_images[selected_idx]), use_container_width=True)
                st.caption(f"Dosya: {found_images[selected_idx].name}")
        else:
            st.warning(f"{safe_id} S{sector:02d} icin gorsel bulunamadi.")
            st.info(
                "Aranan konumlar:\\n"
                "- outputs/figures/\\n"
                "- outputs_top10/figures/\\n"
                "- outputs_wsl_mcmc/figures/"
            )'''
    if old_image_block in content:
        content = content.replace(old_image_block, new_image_block)
        print("OK gorsel yukleme lazy ve coklu kaynakli yapildi")
        changed = True

    if changed:
        dashboard_file.write_text(content, encoding="utf-8")
        print("OK dashboard kaydedildi")
    else:
        print("BILGI dashboard icin degisiklik gerekmedi")

    try:
        ast.parse(dashboard_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: cp {backup} {dashboard_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())