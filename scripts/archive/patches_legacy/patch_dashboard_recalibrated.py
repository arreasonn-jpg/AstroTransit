from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
dashboard_file = project_root / "dashboard" / "app.py"


def main():
    if not dashboard_file.exists():
        print("HATA: dashboard/app.py bulunamadi")
        return 1

    backup = dashboard_file.with_suffix(".py.recal_backup")
    shutil.copy(dashboard_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = dashboard_file.read_text(encoding="utf-8")
    changed = False

    # Varsayılan parquet yolu
    old = 'value="outputs/parquet/astrotransit_candidates.parquet",'
    new = 'value="outputs/parquet/astrotransit_candidates_recal.parquet",'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: varsayilan parquet yolu recal oldu")
        changed = True

    # candidate_class yerine candidate_class_recal tercih etsin
    helper_block = """
def _preferred_class_column(df):
    if "candidate_class_recal" in df.columns:
        return "candidate_class_recal"
    if "candidate_class" in df.columns:
        return "candidate_class"
    return None

def _preferred_score_column(df):
    if "total_score" in df.columns:
        return "total_score"
    return None
"""

    if "_preferred_class_column" not in content:
        insert_after = "def apply_custom_css():"
        idx = content.find(insert_after)
        if idx != -1:
            # fonksiyonun önüne ekle
            content = content.replace(insert_after, helper_block + "\n\ndef apply_custom_css():")
            print("OK dashboard helper fonksiyonlari eklendi")
            changed = True

    # Katalog gezgininde candidate_class kolonunu tercihli yap
    old = 'available_classes = sorted(df["candidate_class"].dropna().unique().tolist()) if "candidate_class" in df.columns else []'
    new = 'class_col = _preferred_class_column(df)\n        available_classes = sorted(df[class_col].dropna().unique().tolist()) if class_col else []'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: class kolon secimi dinamik yapildi")
        changed = True

    old = 'if "candidate_class" in df.columns and selected_classes:\n        mask &= df["candidate_class"].isin(selected_classes)'
    new = 'class_col = _preferred_class_column(df)\n    if class_col and selected_classes:\n        mask &= df[class_col].isin(selected_classes)'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: sinif filtresi recalibrated destekli")
        changed = True

    old = 'if "candidate_class" in df_filtered.columns and len(df_filtered) > 0:'
    new = 'class_col = _preferred_class_column(df_filtered)\n    if class_col and len(df_filtered) > 0:'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: sinif dagilimi recalibrated destekli")
        changed = True

    old = 'class_counts = df_filtered["candidate_class"].value_counts().to_dict()'
    new = 'class_counts = df_filtered[class_col].value_counts().to_dict()'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: sinif sayimi dynamic")
        changed = True

    # Display kolonları recalibrated bilgiyi içersin
    old = '"total_score", "candidate_class", "fpp",'
    new = '"total_score", "candidate_class", "candidate_class_recal", "scientific_status", "fpp",'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: tabloya recalibrated kolonlar eklendi")
        changed = True

    # Plotly color
    old = 'color="candidate_class" if "candidate_class" in df_plot.columns else None,'
    new = 'plot_class_col = _preferred_class_column(df_plot)\n                color=plot_class_col if plot_class_col else None,'
    if old in content:
        content = content.replace(old, new)
        print("OK dashboard: plot color recalibrated destekli")
        changed = True

    # Candidate detail'de recal parquet lookup göstergesi
    insert_marker = '        with tabs[5]:\n            st.json(data)\n\n        st.subheader("Gorseller")'
    add_block = '''        with tabs[5]:
            st.json(data)

        # Recalibrated katalogdan ek bilgi bul
        recal_path = Path("outputs/parquet/astrotransit_candidates_recal.parquet")
        if recal_path.exists():
            try:
                import pandas as pd
                recal_df = pd.read_parquet(recal_path)
                source_id = data.get("target", {}).get("source_id", "")
                sector_val = data.get("target", {}).get("sector", None)
                match = recal_df[recal_df["source_id"] == source_id]
                if sector_val is not None and "sector" in recal_df.columns:
                    match = match[match["sector"] == sector_val]

                if len(match) > 0:
                    row = match.iloc[0]
                    st.subheader("Recalibrated Status")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Class (recal)", str(row.get("candidate_class_recal", "NA")))
                    with c2:
                        st.metric("Scientific Status", str(row.get("scientific_status", "NA")))
                    with c3:
                        st.metric("Ref Match", str(row.get("reference_match", "NA")))
            except Exception as e:
                st.info(f"Recal lookup yapilamadi: {e}")

        st.subheader("Gorseller")'''
    if insert_marker in content:
        content = content.replace(insert_marker, add_block)
        print("OK dashboard: candidate detail'e recal status eklendi")
        changed = True

    if changed:
        dashboard_file.write_text(content, encoding="utf-8")
        print("OK Dashboard kaydedildi")
    else:
        print("BILGI Dashboard icin degisiklik gerekmedi")

    ast.parse(dashboard_file.read_text(encoding="utf-8"))
    print("OK Python sozdizimi gecerli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())