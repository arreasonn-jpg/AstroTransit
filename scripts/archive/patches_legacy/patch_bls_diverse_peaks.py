"""
BLS'in bulduğu tepeler genelde harmoniktir.
Bu patch: birbirinden farkli periyot gruplarindan
en iyi 3 adayi secer.

Boylece hem gercek periyot hem 2P harmonigi ayni
listede yer alir - biz secebilir.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
bls_file = project_root / "astrotransit" / "detection" / "bls_search.py"


def main():
    if not bls_file.exists():
        print("HATA: bls_search.py bulunamadi")
        return 1

    shutil.copy(bls_file, bls_file.with_suffix(".py.diverse_backup"))
    print("OK Yedek: bls_search.py.diverse_backup")

    content = bls_file.read_text(encoding="utf-8")

    if "_select_diverse_peaks" in content:
        print("BILGI Diverse peaks zaten uygulanmis")
        return 0

    # Search metodunda "top_indices" satirini bul ve degistir
    old_parts = [
        '        sorted_idx = np.argsort(power_arr)[::-1]',
        '        top_indices = sorted_idx[: self.n_peaks]',
    ]
    old_block = "\n".join(old_parts)

    new_parts = [
        '        sorted_idx = np.argsort(power_arr)[::-1]',
        '        # Cesitli periyot gruplarindan sec (harmonik degil)',
        '        top_indices = self._select_diverse_peaks(',
        '            sorted_idx, periods_arr, n_peaks=self.n_peaks',
        '        )',
    ]
    new_block = "\n".join(new_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK Search metodu diverse peaks kullaniyor")
    else:
        print("UYARI Search bloklari bulunamadi")
        return 1

    # Yeni metodu class icine ekle
    # _empty_result metodundan HEMEN once
    marker = '    def _empty_result(self, target_id: str, sector: int) -> BLSResult:'

    new_method_parts = [
        '    @staticmethod',
        '    def _select_diverse_peaks(',
        '        sorted_indices,',
        '        periods,',
        '        n_peaks: int = 5,',
        '        min_period_ratio: float = 0.15,',
        '    ):',
        '        # Harmonik olmayan farkli periyot grubu tepelerini secer.',
        '        # Iki periyot birbirinden en az %15 uzakta olmali,',
        '        # 2P veya P/2 harmoniginden de kacinilir.',
        '        selected = []',
        '        selected_periods = []',
        '',
        '        for idx in sorted_indices:',
        '            if len(selected) >= n_peaks:',
        '                break',
        '',
        '            p = float(periods[idx])',
        '            if p <= 0:',
        '                continue',
        '',
        '            # Bu periyot mevcut seciilenlerden yeterince farkli mi?',
        '            is_diverse = True',
        '            for prev_p in selected_periods:',
        '                if prev_p <= 0:',
        '                    continue',
        '',
        '                # Direkt yakınlık',
        '                rel_diff = abs(p - prev_p) / prev_p',
        '                if rel_diff < min_period_ratio:',
        '                    is_diverse = False',
        '                    break',
        '',
        '                # 2P harmonigi kontrolu',
        '                for factor in [0.5, 2.0, 3.0]:',
        '                    harmonic = prev_p * factor',
        '                    if harmonic > 0:',
        '                        h_diff = abs(p - harmonic) / harmonic',
        '                        if h_diff < 0.05:',
        '                            is_diverse = False',
        '                            break',
        '',
        '                if not is_diverse:',
        '                    break',
        '',
        '            if is_diverse:',
        '                selected.append(idx)',
        '                selected_periods.append(p)',
        '',
        '        # Eger yeterli bulamazsak, sirali listeden doldur',
        '        if len(selected) < n_peaks:',
        '            for idx in sorted_indices:',
        '                if idx not in selected:',
        '                    selected.append(idx)',
        '                    if len(selected) >= n_peaks:',
        '                        break',
        '',
        '        return selected[:n_peaks]',
        '',
        '',
    ]
    new_method = "\n".join(new_method_parts)

    if marker in content:
        content = content.replace(marker, new_method + marker)
        print("OK _select_diverse_peaks metodu eklendi")
    else:
        print("UYARI _empty_result marker bulunamadi")
        return 1

    bls_file.write_text(content, encoding="utf-8")

    try:
        import ast
        ast.parse(bls_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())