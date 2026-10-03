# Environment lock files

Bu dizin iki farkli bagimlilik kilidi icerir. Ikisi de ayni Python 3.11
surumune karsi uretilmistir.

## `requirements.lock` — Full development environment

Tum gelistirme araclarini icerir: jupyterlab, ipykernel, pytest, mypy,
ruff, pre-commit ve runtime bagimliliklari.

**Kullanim:** Yerel gelistirme ortami olusturmak icin:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r envs/requirements.lock

**Kaynak:** `pip freeze` cikti, en son dogrulanan gelistirme ortamindan.

## `requirements-docker.lock` — Docker runtime environment

Sadece runtime bagimliliklari + modeling extra (pymc, exoplanet, arviz,
numba, llvmlite). Gelistirme araclari **cikarilmistir** (~185MB tasarruf).

**Kullanim:** `Dockerfile` icindeki iki-stage build tarafindan tuketilir.
Manuel kurulum icin:

    pip install -r envs/requirements-docker.lock

**Kaynak:** Temiz bir venv'de `pip install -e ".[modeling]"` sonrasi
`pip freeze` cikti.

## Lock Guncelleme Proseduru

Herhangi bir lock'u guncellemek icin:

    python -m venv /tmp/fresh-env
    /tmp/fresh-env/bin/pip install --upgrade pip

    # Full dev lock icin:
    /tmp/fresh-env/bin/pip install -e ".[dev,modeling]"
    /tmp/fresh-env/bin/pip freeze | grep -v '^-e' | grep -v '^astrotransit' \
        > envs/requirements.lock

    # Docker runtime lock icin:
    /tmp/fresh-env/bin/pip install -e ".[modeling]"  # (yeni venv)
    /tmp/fresh-env/bin/pip freeze | grep -v '^-e' | grep -v '^astrotransit' \
        > envs/requirements-docker.lock

    rm -rf /tmp/fresh-env

**Onemli:** Dosyalari her zaman `>` ile bastan yazin. `>>` ile
eklemeyin — tekrarli pin cakismasi yaratir.
