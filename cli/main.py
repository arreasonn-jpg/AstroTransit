"""
AstroTransit CLI (Komut Satırı Arayüzü).

Kullanım:
    astrotransit single TIC 261136679
    astrotransit single TIC 261136679 --sectors 14 15
    astrotransit batch targets.csv
    astrotransit benchmark --max-per-category 5
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(
    name="astrotransit",
    help="TESS ve JWST verilerinden transit tespiti, filtreleme ve kategorizasyon.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def single(
    target: str = typer.Argument(
        ...,
        help="Hedef TIC ID (örn. 'TIC 261136679' veya '261136679')",
    ),
    sectors: Optional[list[int]] = typer.Option(
        None,
        "--sectors", "-s",
        help="İşlenecek sektörler (boş = tümü)",
    ),
    config: Optional[str] = typer.Option(
        None,
        "--config", "-c",
        help="Konfigürasyon dosyası yolu",
    ),
    force_mcmc: bool = typer.Option(
        False,
        "--force-mcmc",
        help="Tüm adaylara MCMC uygula",
    ),
    force_map: bool = typer.Option(
        False,
        "--force-map",
        help="Sadece MAP kullan",
    ),
    no_viz: bool = typer.Option(
        False,
        "--no-viz",
        help="Görselleştirmeyi atla",
    ),
    no_catalog: bool = typer.Option(
        False,
        "--no-catalog",
        help="Katalog sorgusunu atla",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log seviyesi (DEBUG, INFO, WARNING, ERROR)",
    ),
):
    """Tek bir hedef için transit analizi çalıştırır."""

    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    console.print(
        Panel(
            f"[bold cyan]AstroTransit — Tek Hedef Analizi[/bold cyan]\n"
            f"Hedef: [bold]{target}[/bold]",
            border_style="cyan",
        )
    )

    with AstroTransitOrchestrator(
        config_path=config,
        force_mcmc=force_mcmc,
        force_map=force_map,
        skip_visualization=no_viz,
        skip_catalog=no_catalog,
        log_level=log_level,
    ) as orchestrator:

        result = orchestrator.run_single(target, sectors=sectors)

    # ── Sonuç tablosu ──
    table = Table(title=f"Sonuçlar — {result.target_id}")
    table.add_column("Özellik", style="cyan")
    table.add_column("Değer", style="green")

    table.add_row("Durum", "✓ Başarılı" if result.success else "✗ Başarısız")
    table.add_row("İşlenen Sektör", str(result.sectors_processed))
    table.add_row("Bulunan Aday", str(result.candidates_found))
    table.add_row("Onaylı Aday", str(result.candidates_confirmed))

    if result.error:
        table.add_row("Hata", f"[red]{result.error}[/red]")

    for sr in result.sector_results:
        if sr.quality is not None:
            table.add_row(
                f"Sektör {sr.sector}",
                f"Sınıf {sr.quality.score.candidate_class.value} "
                f"(skor: {sr.quality.score.total_score:.0f})"
            )

    console.print(table)


@app.command()
def batch(
    targets_file: str = typer.Argument(
        ...,
        help="Hedef listesi dosyası (CSV veya TXT, her satırda bir TIC ID)",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    force_map: bool = typer.Option(False, "--force-map"),
    no_viz: bool = typer.Option(True, "--no-viz"),
    no_catalog: bool = typer.Option(False, "--no-catalog"),
    log_level: str = typer.Option("INFO", "--log-level"),
):
    """Birden fazla hedef için toplu transit analizi çalıştırır."""

    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    # Hedef dosyasını oku
    path = Path(targets_file)

    if not path.exists():
        console.print(f"[red]Dosya bulunamadı: {path}[/red]")
        raise typer.Exit(1)

    if path.suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(path)
        if "tic_id" in df.columns:
            targets = [f"TIC {tid}" for tid in df["tic_id"].tolist()]
        else:
            targets = df.iloc[:, 0].astype(str).tolist()
    else:
        targets = [
            line.strip()
            for line in path.read_text().strip().split("\n")
            if line.strip() and not line.startswith("#")
        ]

    console.print(
        Panel(
            f"[bold cyan]AstroTransit — Toplu Analiz[/bold cyan]\n"
            f"Hedef sayısı: [bold]{len(targets)}[/bold]",
            border_style="cyan",
        )
    )

    with AstroTransitOrchestrator(
        config_path=config,
        force_map=force_map,
        skip_visualization=no_viz,
        skip_catalog=no_catalog,
        log_level=log_level,
    ) as orchestrator:

        results = orchestrator.run_batch(targets)

    # Özet
    n_success = sum(1 for r in results if r.success)
    n_candidates = sum(r.candidates_confirmed for r in results)

    console.print(
        f"\n[bold green]Tamamlandı:[/bold green] "
        f"{n_success}/{len(results)} başarılı, "
        f"{n_candidates} onaylı aday"
    )


@app.command()
def benchmark(
    max_per_category: Optional[int] = typer.Option(
        None,
        "--max",
        help="Kategori başına maksimum hedef sayısı",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    log_level: str = typer.Option("INFO", "--log-level"),
):
    """Benchmark doğrulama pipeline'ını çalıştırır."""

    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    console.print(
        Panel(
            f"[bold cyan]AstroTransit — Benchmark Doğrulama[/bold cyan]",
            border_style="cyan",
        )
    )

    orchestrator = AstroTransitOrchestrator(
        config_path=config,
        force_map=True,
        skip_visualization=True,
        log_level=log_level,
    )

    result = orchestrator.run_benchmark(
        max_per_category=max_per_category,
    )

    orchestrator.close()

    # Sonuçlar
    console.print(result.metrics.report())


@app.command()
def version():
    """AstroTransit versiyon bilgisi."""

    from astrotransit.version import __version__

    console.print(
        Panel(
            f"[bold cyan]AstroTransit[/bold cyan] v{__version__}\n"
            f"TESS ve JWST verilerinden transit tespiti, "
            f"filtreleme ve kategorizasyon platformu",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    app()