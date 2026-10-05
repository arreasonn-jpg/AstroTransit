# Katkı Rehberi

AstroTransit'e katkıda bulunmak istediğiniz için teşekkürler! Bu rehber,
süreci olabildiğince pürüzsüz hale getirmek için hazırlanmıştır.

## Hızlı Başlangıç

    git clone https://github.com/arreasonn-jpg/AstroTransit.git
    cd AstroTransit
    python -m venv .venv
    source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
    python -m pip install -U pip
    python -m pip install -e ".[dev]"
    pre-commit install

## Geliştirme Akışı

1. **Branch açın**: `git checkout -b feat/kisa-aciklama` veya `fix/kisa-aciklama`
2. **Değişiklikleri yapın**
3. **Testleri çalıştırın**: `python -m pytest -q`
4. **Pre-commit hook'ları**: commit sırasında otomatik çalışır (ruff, mypy)
5. **Commit mesajı**: Conventional Commits formatı
   - `feat:` yeni özellik
   - `fix:` hata düzeltmesi
   - `test:` test ekleme
   - `docs:` dokümantasyon
   - `chore:` bakım
   - `refactor:` yeniden düzenleme
6. **Push + PR açın**

## Kod Standartları

### Python

- **Python 3.11+** sözdizimi (`from __future__ import annotations`)
- **Type hint'ler**: mypy strict'e yakın uyum
- **Docstring'ler**: NumPy/Google stili, public API'de zorunlu
- **Satır uzunluğu**: 100 karakter (ruff `line-length=100`)
- **Import sırası**: stdlib → third-party → first-party

### Testler

- **Yeni özellik** → test ile birlikte gelir
- **Bug fix** → reproducer test ile birlikte gelir
- **Coverage**: değiştirdiğiniz dosyanın coverage'ı düşmemeli
- **Mock'lama**: ağ erişimi (`astroquery`, `lightkurve`, `pymc`) mutlaka mock'lanmalı
- **Deterministik**: `numpy.random.default_rng(seed)` kullanın, `np.random.seed` değil

### Bilimsel Kod

Bu proje bilimsel bir araçtır; **iddialar kanıta dayanmalıdır**:

- Yeni bir metrik eklerken **epistemik sınırları** docstring'de belirtin
- "FPP" veya "Earth similarity" gibi terimler **kalibre olasılık değildir**;
  `docs/science/` altındaki mevcut tanımlara uyun
- Sayısal eşikler **sabit** olmamalı; `configs/default.toml` üzerinden
  yapılandırılabilir olmalı
- `confirmed=True` gibi iddialar kanıt zinciri (`FollowupEvidence`)
  gerektirir

## Pull Request Süreci

1. PR başlığı **Conventional Commits** formatında
2. PR açıklaması şablonu doldurun (değişiklik, test, kırıcı etki)
3. **Tüm CI check'leri yeşil olmalı**:
   - `lint` (ruff)
   - `mypy`
   - `quality` (test + coverage, matrix: 3.11, 3.12, 3.13)
   - `build`, `docker`, `modeling-smoke`
4. **En az bir reviewer onayı** (şu an maintainer: @arreasonn-jpg)
5. **Squash merge** tercih edilir

## Yerel Kalite Kontrolleri

    # Tüm testler
    python -m pytest -q

    # Coverage raporu
    python -m pytest --cov=astrotransit --cov-report=term-missing -q

    # Ruff (lint + format)
    ruff check .
    ruff format --check .

    # mypy
    mypy astrotransit cli dashboard

    # Pre-commit (tüm dosyalar)
    pre-commit run --all-files

## Sık Yapılan Hatalar

- **Ağ çağrıları test ediliyor**: `lightkurve.search_lightcurve`, `astroquery.mast`
  gibi çağrılar `unittest.mock.patch` ile sarılmalı
- **Pragma yanlış kullanımı**: `# pragma: no cover` sadece gerçekten test
  edilemez satırlar için (platforma özel kod, `except ImportError` fallback)
- **Sihirli sayılar**: sabit değerleri `configs/default.toml`'a taşıyın
- **Konfigürasyon okuma**: `Settings` modeli üzerinden, `os.environ` doğrudan
  okumayın

## Yardım

- **Sorular**: GitHub Issues (etiket: `question`)
- **Bug raporları**: GitHub Issues (etiket: `bug`), reproducer ile
- **Tartışma**: GitHub Discussions
- **Bilimsel metodoloji**: `docs/science/` klasörü

## Lisans

Katkılarınız [MIT](LICENSE) lisansı altında yayınlanır.
