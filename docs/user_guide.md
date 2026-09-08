## WSL / Linux Üzerinde MCMC Çalıştırma

AstroTransit’in PyMC + exoplanet tabanlı MCMC hattı, Windows ortamında kurulum ve derleyici kısıtları nedeniyle kararsız olabilir. Bu nedenle güvenilir MCMC çalışmaları için **WSL (Ubuntu)** veya genel olarak **Linux** önerilir.

### Neden WSL?
- `pymc`, `exoplanet`, `exoplanet-core` ve `celerite2` Linux üzerinde daha kararlı çalışır
- derleyici zinciri (`build-essential`, `g++`) kolayca kurulabilir
- PyTensor backend daha sorunsuz davranır
- divergence / convergence teşhisi daha güvenilir olur

### WSL Kurulum Özeti

Ubuntu içinde:

```bash
sudo apt update
sudo apt install -y build-essential python3-venv python3-dev
```

Sonra standart kurulum + MCMC ek paketleri:

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
python -m pip install -U pip
python -m pip install -e ".[modeling]"
```

MCMC'yi çalıştırmadan önce modeli doğrulayın:

```bash
python - <<'PY'
import arviz, exoplanet, pymc
from astrotransit.modeling.pymc_fit import MCMCFitResult
print("modeling environment ok")
PY
```

Dikkat: MCMC yalnızca seçilmiş güçlü adaylar içindir; toplu taramada
hesapsal olarak uygulanabilir değildir (bkz. README → "MAP ve MCMC").
`MCMCFitResult` ancak R-hat < 1.01, bulk ESS ≥ 400 ve sıfır divergence ile
`convergence_ok=True` sayılır; aksi halde posterior güvenilir posterior
olarak işaretlenmez.