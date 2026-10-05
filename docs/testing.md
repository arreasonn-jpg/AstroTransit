# Test Stratejisi

Bu doküman AstroTransit'in test yaklaşımını, mock'lama kurallarını ve coverage
politikasını açıklar.

## Mevcut Durum

| Metrik | Değer |
|--------|-------|
| Test sayısı | **2409 geçen** (0 skip, 0 xfail) |
| Satır coverage | **%94.66** |
| Branch coverage | %90+ |
| Test süresi | ~8 dk (tam suite, tek çekirdek) |
| Python matrix | 3.11, 3.12, 3.13 (CI) |

## Test Katmanları

### 1. Unit testler (çoğunluk)

Her modül için bir test dosyası:

    tests/test_<modul>.py

Örnek: `astrotransit/quality/vetting.py` → `tests/test_quality_vetting.py`

Bu testler:
- Ağ erişimi **yok** (mock'lu)
- Deterministik (`numpy.random.default_rng(seed)`)
- Hızlı (<1 sn / dosya genelde)

### 2. Integration testler

Birden çok modülü birlikte test eder:

    tests/test_pipelines_tess_pipeline.py
    tests/test_pipelines_jwst_pipeline.py

Alt bağımlılıklar mock'lanır (TESSClient, MAPFitter), ama pipeline
orkestrasyonu gerçek çalışır.

### 3. Contract testler

Dış sözleşmeleri doğrular:

    tests/test_cli_contract.py
    tests/test_outputs.py

Örnek: CLI'ın `--help` çıktısı, JSON şema sözleşmeleri, Parquet sütun
isimleri.

## Mock'lama Kuralları

### Ağ erişimi — Her zaman mock

Şu çağrılar **asla gerçek ağa çıkmamalı**:

| Çağrı | Mock hedefi |
|-------|-------------|
| `lightkurve.search_lightcurve` | `astrotransit.data.tess_client.lk` |
| `astroquery.mast.Observations` | `astrotransit.data.mast_client` |
| `pymc.sample` | `astrotransit.modeling.pymc_fit.pm` |
| `celerite2.GaussianProcess` | `astrotransit.preprocessing.jwst_detrend.celerite2` |
| `scipy.optimize.minimize` | `astrotransit.modeling.map_fit.minimize` |
| `transitleastsquares` | `astrotransit.detection.tls_search.transitleastsquares` |

**Örnek pattern:**

    from unittest.mock import patch

    def test_search_returns_result(tmp_path):
        c = TESSClient(cache_dir=tmp_path, use_cache=False)
        fake_result = MagicMock()
        fake_result.__len__ = MagicMock(return_value=3)

        with patch("astrotransit.data.tess_client.lk") as mock_lk:
            mock_lk.search_lightcurve.return_value = fake_result
            result = c.search("TIC 123")
        assert result is fake_result

### Gerçek astronomik nesneler — Kullan

`lightkurve`, `astropy.units` gibi kütüphaneler **kurulu olduğunda**
gerçek nesneleri kullanmak daha iyi:

    lk = pytest.importorskip("lightkurve")
    import astropy.units as u

    lc = lk.LightCurve(time=np.arange(100) * u.day, flux=np.ones(100))
    result = client._clean_lightcurve(lc)

Bu, sahte `MagicMock` nesnelerinin yakalayamadığı sözleşme hatalarını
(test edilen kodun `lc.flux.value` beklemesi gibi) yakalar.

### pymc gibi opsiyonel bağımlılıklar

**Kurulu değilse** testler atlanmalı, hata vermemeli:

    lk = pytest.importorskip("lightkurve")  # yoksa skip

Ayrıca `monkeypatch.setattr(mod, "pm", fake_pm, raising=False)` gibi
`raising=False` kullanın — modül attribute'u yoksa hata vermez.

## Coverage Politikası

### Hedefler

- **Proje toplamı:** ≥%90 (mevcut: %94.66)
- **Değiştirdiğiniz dosya:** düşmemeli
- **Yeni dosya:** ≥%80

### `# pragma: no cover` Kullanımı

Pragma **sadece** şu durumlarda:

1. **Platforma özel kod**

       if sys.platform == "win32":  # pragma: no cover
           ...

2. **Fallback import**

       except ImportError as exc:  # pragma: no cover
           import tomli as tomllib

3. **Defansif `except` blokları** (asla tetiklenmeyen)

       except (ValueError, ZeroDivisionError):  # pragma: no cover - defansif
           derived.semi_major_axis_au = 0.0

4. **Singleton cache mantığı**

       if _default_settings is None or config_path is not None:
           _default_settings = load_settings(config_path)

**Yanlış kullanım:** Test edilebilir bir dalı pragma ile gizlemek —
bu teknik borçtur, reviewer reddeder.

### Branch Coverage

Branch coverage, `if/else`'in her iki dalının da test edildiğini doğrular.
Mevcut hedef %90+. Bazı durumlarda `# pragma: no branch` kullanın
(asla False dönmeyen koşullar için).

## CI/CD

Her PR'da:

| Check | Ne yapar |
|-------|----------|
| `lint` | `ruff check .` |
| `mypy` | `mypy astrotransit cli dashboard` |
| `quality (3.11)` | Test + coverage, `--cov-fail-under=72` |
| `quality (3.12)` | Aynı, 3.12'de |
| `quality (3.13)` | Aynı, 3.13'te |
| `build` | `pip install -e ".[dev]"` |
| `docker` | Dockerfile build |
| `modeling-smoke` | Minimal MCMC smoke test |

**Not:** Coverage eşiği `pyproject.toml`'da `fail_under = 72`; artırım PR
bazında yapılır (72 → 75 → 80 → ...).

## Yerel Geliştirme Akışı

### Hızlı iterasyon

    # Tek dosya
    pytest tests/test_quality_vetting.py -q

    # Regex
    pytest -k "residual" -q

    # İlk hata dur, traceback göster
    pytest -x -vv tests/test_quality_vetting.py

### Tam suite + coverage

    pytest --cov=astrotransit --cov-report=term-missing -q

### Belirli dosyanın coverage'ı

    coverage run --source=astrotransit -m pytest tests/test_data_tess_client.py -q
    coverage report -m --include="*/data/tess_client.py"

## Test Kategorileri

### 1. Dataclass testleri

`.to_dict()`, `.summary()`, `__post_init__` validasyonu:

    def test_to_dict():
        obj = SomeResult(name="x", value=1.5)
        d = obj.to_dict()
        assert d["name"] == "x"

### 2. Helper fonksiyon testleri

`_finite_or_none`, `_value`, `_parse_int` gibi private helper'lar.
Bunlar küçük olduğu için hızlıca %100'e çıkar.

### 3. Error path testleri

Her `raise ValueError` için bir `pytest.raises`:

    with pytest.raises(ValueError, match="pozitif"):
        MyConfig(value=-1)

### 4. Integration / happy path

Modül birlikte çalıştığında beklenen akış:

    def test_vet_clean_candidate():
        v = FalsePositiveVetter()
        r = v.vet(clean_candidate, clean_metrics)
        assert r.n_fail == 0
        assert r.is_false_positive is False

## Yeni Modül Eklerken Kontrol Listesi

- [ ] `tests/test_<modul_adi>.py` oluştur
- [ ] Her public fonksiyon/sınıf için en az 1 test
- [ ] Her `raise` için `pytest.raises` testi
- [ ] Dataclass `to_dict`/`summary` testi
- [ ] Integration testi (mock'larla uçtan uca)
- [ ] `pytest tests/test_<modul_adi>.py --cov=<modül> --cov-report=term-missing`
- [ ] Coverage ≥%80
- [ ] `ruff check` ve `mypy` temiz
- [ ] Yeni mock var mı? → Yukarıdaki "Mock'lama Kuralları"na uygun mu?

## Sıkça Sorulan

**S: Test neden yavaş (8 dk)?**
C: `pymc`, `lightkurve`, `transitleastsquares` import'ları yavaş. Suite
paralel çalıştırmak için `pytest-xdist` kullanılabilir (`pytest -n auto`).

**S: Ağ hatası veren testi nasıl geçici olarak atlarım?**
C: `pytest.importorskip("lightkurve")` modül seviyesinde kullanın, ya da
testin gövdesinde `pytest.skip("ağ yok")`.

**S: Coverage %100'e nasıl çıkarırım?**
C: Private helper'ları test edin, `# pragma: no cover` sadece gerçekten
test edilemez satırlara. Genelde %94-96 pratik üst sınırdır; %100 zorunlu
değildir ve bazen anti-pattern olur (test edilemez satırı pragma ile
gizlemek teknik borçtur).

**S: `# pragma: no cover` sayısını nasıl azaltırım?**
C: Pragramalar genelde `except ImportError`, `except OSError` gibi
defansif bloklardadır. Bunlar gerçekten test edilemez; pragma doğru
kullanımdır. Test edilebilir bir dalı pragma ile gizlemek **yanlıştır**.

## Referanslar

- [pytest documentation](https://docs.pytest.org/)
- [coverage.py documentation](https://coverage.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Hypothesis](https://hypothesis.readthedocs.io/) — ileride property-based testler için
