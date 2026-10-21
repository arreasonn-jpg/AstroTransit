"""Qt-bağımsız hedef keşif katmanı.

Kullanıcı TIC listesi girmeden "hedef sayısı 5" dediğinde burası devreye
girer: MAST'ın TESS-SPOC 2 dakikalık gözlem listesinden rastgele bir sektör
seçilir ve o sektörün İNDİRİLEBİLİR veri envanterinden benzersiz N hedef
seçilir. Seçim bilimsel kataloğa (TOI/TCE vb.) DAYANMAZ — veri-varlığı
tabanlıdır; böylece "kataloglarda önceden seçilmemiş hedefler" taranır.

Saf mantık (satır filtreleme/örnekleme) birim test edilebilir; MAST sorgusu
ağırbaşı (network) ve UI katmanı (QThread) ile uyumlu workspace fonksiyonu
ayrırılmıştır.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from typing import Any, Optional

from loguru import logger

# MAST şeması: TESS ürünleri mission 'TESS' altında; 2-dakikalık SPOC
# envanteri provenance_name='SPOC' ile filtrelenir (obs_collection
# 'TESS-SPOC' geçersizdir) ve sektör 'sequence_number' alanındadır.
SPOC_PROVENANCE = "SPOC"
SPOC_EXPTIME = 120.0
SPOC_EXPTIME_WINDOW = (110.0, 130.0)  # sürekli filtre → [min, max] aralık
# Kapı üst sınırı: MAST sorgusu boş gelirse daha yaşlı sektörler denenir.
SECTOR_RANGE = range(1, 97)


class DiscoveryError(RuntimeError):
    """Keşif başarısız (havuz boş / hedef sayısı yetersiz / sorgu hatası)."""


def unique_targets_from_rows(rows: Iterable[Any]) -> list[str]:
    """MAST gözlem tablosundan benzersiz 'TIC <n>' hedef listesi üretir.

    MAST target_name alanı SPOC ürünlerinde '231081369 (TIC)' biçimindedir;
    bu alandan tamamen rakamlardan oluşan token alınır. Sayısal token
    üretmeyen adlar (kalibrasyon/FFI vb.) düşer.
    """

    seen: set[int] = set()
    targets: list[str] = []
    for row in rows:
        try:
            name = row["target_name"]
        except (KeyError, IndexError, TypeError):
            continue
        # MAST SPOC adı '231081369 (TIC)' biçimdedir; yalnız tamamen
        # rakamlardan oluşan token kabul edilir (TICFid1 vb. elenir).
        digits = next((tok for tok in str(name or "").split() if tok.isdigit()), "")
        if not digits:
            continue
        number = int(digits)
        if number in seen:
            continue
        seen.add(number)
        targets.append(f"TIC {number}")
    return targets


def pick_targets(
    rows: Iterable[Any],
    count: int,
    *,
    seed: Optional[int] = None,
    log_sink: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Gözlem satırlarından deterministik örneklemenin ``count`` hedef alır.

    seed verilirse aynı satır kümesinde aynı hedef listesi döner (testler ve
    yeniden-koşum için). Sorun satır kümesi yetersizse DiscoveryError.
    """

    if count < 1:
        raise DiscoveryError("hedef sayısı en az 1 olmalı.")
    candidates = unique_targets_from_rows(rows)
    if log_sink is not None:
        log_sink(f"keşif havuzu: {len(candidates)} benzersiz TIC adayı")
    if len(candidates) < count:
        raise DiscoveryError(
            f"keşif havuzu ({len(candidates)} benzersiz TIC) {count} hedef için yetersiz."
        )
    rng = random.Random(seed)
    picked = rng.sample(candidates, count)
    if log_sink is not None:
        for target in picked:
            log_sink(f"keşif hedefi: {target}")
    logger.info(f"keşif tamamlandı — {count} hedef (seed={seed})")
    return picked


def discover_targets(
    count: int,
    *,
    seed: Optional[int] = None,
    sector: Optional[int] = None,
    log_sink: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """MAST'tan N benzersiz, indirilebilir veriye sahip hedef seçer.

    Sektör filtresi verilmediyse rastgele sektörler denenir; SPOC envanteri
    beklenen sayıyı karşılamazsa en fazla 3 sektör denenir, hepsi boş/beşer
    kalırsa sektör filtresiz (ağır) sorgu düşer, o da başarısızsa
    DiscoveryError yükselir. ``sector`` verilirse o sektör sabitlenir
    (test/tekrarlanabilirlik).
    """

    if count < 1:
        raise DiscoveryError("hedef sayısı en az 1 olmalı.")
    try:
        from astroquery.mast import Observations
    except ImportError as exc:
        raise DiscoveryError("astroquery gereklidir: pip install astroquery") from exc

    if log_sink is not None:
        log_sink(f"MAST keşif sorgusu başlıyor (hedef sayısı={count})")

    sectors = [sector] if sector is not None else list(SECTOR_RANGE)
    if sector is None:
        sectors = random.sample(list(SECTOR_RANGE), len(SECTOR_RANGE))

    rows = None
    for probe in sectors[:3]:
        try:
            rows = Observations.query_criteria(
                provenance_name=SPOC_PROVENANCE,
                t_exptime=list(SPOC_EXPTIME_WINDOW),
                sequence_number=probe,
            )
        except Exception as exc:  # MAST hata çeşitli türde olur
            if log_sink is not None:
                log_sink(f"MAST sorgusu başarısız (s_sector={probe}): {exc}")
            rows = None
            continue
        if rows is not None and len(rows) >= count:
            if log_sink is not None:
                log_sink(f"MAST envanteri: sektör {probe} → {len(rows)} gözlem")
            break
        rows = None

    if rows is None:
        # Son çare: sektör filtresiz (ağır sorgu) envanter.
        try:
            rows = Observations.query_criteria(
                provenance_name=SPOC_PROVENANCE,
                t_exptime=list(SPOC_EXPTIME_WINDOW),
            )
        except Exception as exc:
            raise DiscoveryError(f"MAST sorgusu başarısız: {exc}") from exc

    return pick_targets(rows, count, seed=seed, log_sink=log_sink)
