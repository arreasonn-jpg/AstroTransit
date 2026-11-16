# L1 Dinamikleri (`astrotransit/dynamics/`)

İki keşif kolunun (Kol 1: L1'de yaşanabilir Dünya-benzeri gezegen; Kol 2:
L1'de kontrollü uydu/mega yapı) ortak teknik altyapısıdır. CR3BP (dairesel
kısıtlı üç-cisim problemi) temellidir.

## Modüller

| Modül | İçerik |
|-------|--------|
| `lagrange.py` | `mass_ratio`, `collinear_equilibrium_x` (L1/L2/L3 quintic kökü, Newton), `lagrange_point_positions`, L1 mesafe fonksiyonları (AU), `hill_radius_au`, `orbital_period_days` |
| `cr3bp.py` | `cr3bp_rhs`, `integrate_orbit` (scipy DOP853), `l1_linearized_matrix`, `l1_eigenvalues`, `stability_e_folding_days`, `linear_lissajous_state`, `station_keeping_delta_v_per_correction`, `station_keeping_budget`, `summarize_orbit` |
| `system.py` | `L1System` (yıldız/gezegen parametreleri), `L1Assessment`, `assess_l1` orkestratörü |

## Kullanım

```python
from astrotransit.dynamics import L1System, assess_l1
from astrotransit.dynamics.lagrange import M_SUN_KG, M_EARTH_KG

system = L1System(
    star_name="Sun-like",
    m_star_kg=M_SUN_KG,
    m_planet_kg=M_EARTH_KG,
    separation_au=1.0,
    planet_in_habitable_zone=True,
)
assessment = assess_l1(system)
print(assessment.to_dict())
```

## Fiziksel çerçeve ve epistemik notlar

- **Kolineer noktalar kararsızdır.** L1 doğrusal sisteminde pozitif reel bir
  özdeğer vardır; sapmalar üstel büyür. Güneş-Dünya L1 için e-katlama süresi
  ~23 gündür (`stability_e_folding_days`).
- **L1 yaşanabilir bölge değildir.** Kol 1 için ön koşul, *ana gezegenin*
  HZ'de olmasıdır; L1'in kendisi yıldız ışınımına açık bir noktadır, yaşanabilirlik
  ancak bu ön koşulla anlam kazanır. `planet_in_habitable_zone=None` ise bu alan
  `null` kalır (ölçülmeyen şey null kalır).
- **Kol 2 kontrol gerektirir.** L1'de görülen bir cisim, kontrol edilmediği
  sürece uzun süre kalamaz. `station_keeping_budget` bu gereksinimi model bir
  tahmin olarak üretir; "L1'de görüldü" ifadesi kontrol kanıtı değildir.
- İki kol aynı L1 geometrisini paylaşır ama **aynı kararlılık varsayımını
  paylaşmaz**: Kol 1'de L1 bölgesi pasif olarak yaşanabilir olabilir (HZ ön
  koşulu), Kol 2'de aktif istasyon tutma şarttır.

## Testler

`tests/test_dynamics_lagrange.py`, `tests/test_dynamics_cr3bp.py`,
`tests/test_dynamics_system.py` — 46 test; bilinen değerler (Dünya-Güneş
L1 ≈ 0.01 AU, periyot ≈ 365.25 gün), denge noktasında sıfır ivme, kararsız
özdeğer varlığı, null-semantics (eksik girdi → None, asla 0.0).

## Keşif Kolları (`astrotransit/discovery/`)

Aynı L1 geometrisini paylaşan, ama farklı başarı kriterlerine sahip iki ayrı
motor:

| Kol | Modül | Başarı kriteri | Çıktı etiketi |
|-----|-------|----------------|---------------|
| **Kol 1** — L1'de yaşanabilir Dünya-benzeri | `l1_earth_twin.py` (`L1EarthTwinScorer`) | ana gezegen HZ'de **ve** L1 ışınımı 0.25–2.0 S_earth **ve** Earth similarity ≥ eşik | `eligible=True` + `L1_HABITABLE_REGION_CANDIDATE` |
| **Kol 2** — L1'de kontrollü yapı | `l1_structure.py` (`L1StructureScorer`) | L1 geometrisi hesaplanabilir **ve** istasyon-tutma review skoru ≥ 70 **ve** delta-v bütçesi ≤ üst sınır | `controllable_candidate=True` + `L1_CONTROLLED_STRUCTURE_CANDIDATE` |

- `l1_target_pool.py` (`L1TargetPoolBuilder`): katalog satırlarından (CSV/JSON)
  her hedef için tek kayıtta iki kolu ayrı ayrı değerlendirir; `l1-search` CLI
  komutu (`cli/main.py`) bunu JSON olarak yazar.
- `validation/l1_claims.py`: L1 etiketleri için evidence-gated claim firewall.
  Ana `ClaimStatus` hiyerarşisini değiştirmez; `L1_CONTROLLED_STRUCTURE_CANDIDATE`
  ancak review skoru + makul bütçe birlikte varsa üretilebilir. **"L1'de görüldü"
  hiçbir zaman kontrol kanıtı olarak etiketlenmez.**

### CLI

```bash
astrotransit l1-search targets.csv -o outputs/l1_pool.json --min-similarity 90 --min-review 70
# MAST'tan eksik yıldız parametrelerini tamamla (TXT olarak saf TIC listesi de olur):
astrotransit l1-search tic_list.txt --query-mast -o outputs/l1_pool.json
# Çıktı şema versiyonlu JSON'dur (metadata.schema_version = 1.0, kind = l1_target_pool);
# her kayıtta l1_claim_label claim-firewall etiketini taşır.
# Release gate'e L1 claim tutarlılığını ekle:
astrotransit release-gate --l1-pool outputs/l1_pool.json
```

`l1-search` çıktısındaki `l1_claim_firewall` gate'i: havuz yoksa `PENDING_RUN`,
etiketler `infer_l1_claim` ile uyuşmazsa `FAIL`, aksi halde `PASS`.
`followup-update --l1-pool outputs/l1_pool.json` hedef için L1 etiketini panelde gösterir.

### Kol testleri

`tests/test_l1_earth_twin.py`, `tests/test_l1_structure.py`,
`tests/test_l1_claims.py`, `tests/test_l1_target_pool.py` — 31 test;
eligible path, HZ=False/None → eligible=False, eksik kütle → None (0.0 değil),
review eşiğinin altı → controllable=False, bütçe üstü → False, claim firewall
reddi.
