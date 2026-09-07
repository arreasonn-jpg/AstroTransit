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


@app.command("earth-search")
def earth_search(
    targets_file: str = typer.Argument(
        ...,
        help="TESS hedef listesi (CSV veya TXT, her satırda bir TIC ID)",
    ),
    min_similarity: float = typer.Option(
        90.0,
        "--min-similarity",
        help="Minimum Earth similarity skoru (0-100)",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Gösterilecek ve JSON'a yazılacak maksimum aday sayısı",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Sıralanmış aday özetinin JSON yolu",
    ),
    sectors: Optional[list[int]] = typer.Option(
        None,
        "--sectors", "-s",
        help="İşlenecek sektörler (boş = tüm mevcut sektörler)",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    force_map: bool = typer.Option(True, "--force-map/--no-force-map"),
    no_catalog: bool = typer.Option(False, "--no-catalog"),
    log_level: str = typer.Option("INFO", "--log-level"),
):
    """TESS hedef listesini tarar ve yüzde 90+ Earth-like adayları sıralar.

    Earth similarity, detection confidence ve FPP ayrı sütunlarda gösterilir;
    öncelik skoru yalnızca operasyonel follow-up sıralamasıdır.
    """

    from astrotransit.discovery.earth_search import EarthCandidateRanker
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    if limit < 1:
        console.print("[red]--limit en az 1 olmalıdır.[/red]")
        raise typer.Exit(1)
    if not 0.0 <= min_similarity <= 100.0:
        console.print("[red]--min-similarity 0 ile 100 arasında olmalıdır.[/red]")
        raise typer.Exit(1)

    path = Path(targets_file)
    if not path.exists():
        console.print(f"[red]Dosya bulunamadı: {path}[/red]")
        raise typer.Exit(1)

    if path.suffix.lower() == ".csv":
        import pandas as pd

        df = pd.read_csv(path)
        if "tic_id" in df.columns:
            targets = [f"TIC {tid}" for tid in df["tic_id"].tolist()]
        else:
            targets = df.iloc[:, 0].astype(str).tolist()
    else:
        targets = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    if not targets:
        console.print("[yellow]Hedef listesi boş.[/yellow]")
        raise typer.Exit(0)

    console.print(
        Panel(
            f"[bold cyan]AstroTransit — Earth-like TESS Araması[/bold cyan]\n"
            f"Hedef sayısı: [bold]{len(targets)}[/bold] | "
            f"minimum similarity: [bold]{min_similarity:.1f}[/bold]",
            border_style="cyan",
        )
    )

    with AstroTransitOrchestrator(
        config_path=config,
        force_map=force_map,
        skip_visualization=True,
        skip_catalog=no_catalog,
        log_level=log_level,
    ) as orchestrator:
        results = orchestrator.run_batch(targets, sectors=sectors)

    ranker = EarthCandidateRanker(min_similarity=min_similarity)
    records = ranker.records_from_target_results(results)
    summary = ranker.summarize(records, n_targets=len(results))
    ranked = summary.ranked_candidates[:limit]

    table = Table(title="Earth-like aday önceliklendirmesi")
    table.add_column("#", justify="right")
    table.add_column("Hedef", style="cyan")
    table.add_column("Kategori", style="green")
    table.add_column("Similarity", justify="right")
    table.add_column("Confidence", justify="center")
    table.add_column("FPP", justify="right")
    table.add_column("Priority", justify="right")
    for index, candidate in enumerate(ranked, start=1):
        fpp = "?" if candidate.false_positive_probability is None else f"{candidate.false_positive_probability:.3f}"
        table.add_row(
            str(index),
            candidate.target_id,
            candidate.category_label,
            f"{candidate.similarity_score:.1f}",
            candidate.detection_confidence,
            fpp,
            f"{candidate.priority_score:.1f}",
        )
    console.print(table)
    console.print(
        f"\n[bold]Özet:[/bold] {summary.n_ranked_candidates} uygun aday / "
        f"{summary.n_targets} hedef; similarity, confidence ve FPP ayrı raporlandı."
    )

    if output:
        limited_summary = type(summary)(
            n_targets=summary.n_targets,
            n_records=summary.n_records,
            n_ranked_candidates=len(ranked),
            ranked_candidates=tuple(ranked),
        )
        output_path = limited_summary.write_json(output)
        console.print(f"JSON çıktı: [green]{output_path}[/green]")


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