"""Final acceptance kapısı bitirici — kanıt auditi geçen kapının durumunu kapatır.

Epistemik sıra IMPORTANT:
  1. program.json'a kabul kontrolleri *kanıt yokken* ilan edilir
  2. koşucu kanıtı üretir (`run_performance_campaign.py` gibi)
  3. audit `acceptance_status == pass` gösterir
  4. **bu betik** yalnız `status: pending_run → measured` çevirir —
     ve yalnız audit yeniden hesaplayıp geçtiyse. Audit geçmezse
     hiçbir şey yazmaz.

Bu betik eşik üretmez, ölçüm yapmaz; ölçüm başarılı olmuş bir kapının
kayıt durumunu kalıcı belgeye işler.

Kullanım:
    python scripts/validation/finalize_performance_gate.py --gate performance
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.final_acceptance_audit import audit

PROGRAM = Path("validation_runs/final_acceptance_v1/program.json")


def finalize_gate(gate_id: str, program_path: Path) -> int:
    if not program_path.is_file():
        print(f"[error] program dosyası yok: {program_path}", file=sys.stderr)
        return 2

    program = json.loads(program_path.read_text(encoding="utf-8"))
    gate = next((g for g in program["gates"] if g.get("id") == gate_id), None)
    if gate is None:
        print(f"[error] kapı bulunamadı: {gate_id}", file=sys.stderr)
        return 2
    if not gate.get("acceptance_checks"):
        print(
            "[error] kabul kontrolü ilan edilmemiş kapı kapatılmaz — "
            "önce eşikleri ilan edin, sonra kanıt üretin.",
            file=sys.stderr,
        )
        return 3

    result = audit(program_path)
    audit_gate = next(g for g in result["gates"] if g["id"] == gate_id)
    if not (audit_gate.get("evidence_exists") and audit_gate.get("acceptance_status") == "pass"):
        print(
            "[error] audit geçmedi "
            f"(evidence_exists={audit_gate.get('evidence_exists')}, "
            f"acceptance={audit_gate.get('acceptance_status')}) — status değiştirilmedi.",
            file=sys.stderr,
        )
        return 4
    if audit_gate.get("closed"):
        print(f"[ok] {gate_id} zaten kapalı — değişiklik yok")
        return 0

    gate["status"] = "measured"
    program_path.write_text(
        json.dumps(program, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[ok] {gate_id}: pending_run → measured (audit pass ile desteklendi)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.validation.finalize_performance_gate")
    parser.add_argument("--gate", default="performance")
    parser.add_argument(
        "--program",
        default=str(PROGRAM),
        help="program.json yolu (testler için geçersiz kılınabilir)",
    )
    args = parser.parse_args(argv)
    return finalize_gate(args.gate, Path(args.program))


if __name__ == "__main__":
    raise SystemExit(main())
