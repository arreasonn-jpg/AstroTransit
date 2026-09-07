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