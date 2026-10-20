"""AstroTransit masaüstü ana penceresi (PySide6).

UI katmanı: iş mantığı `desktop.analysis`/`desktop.helpers` içindedir;
bu modül yalnızca pencere, tablo ve sinyal bağlantılarını kurar.
Görsel katman olduğu için coverage dışı bırakılır (pyproject omit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.analysis import AnalysisConfig, project_root
from desktop.helpers import (
    RESULT_TABLE_COLUMNS,
    figure_caption,
    find_figures,
    list_json_results,
    output_roots,
    parse_sectors,
    rows_from_json_files,
    sector_rows,
)
from desktop.worker import AnalysisWorker


class MainWindow(QMainWindow):
    """AstroTransit ana pencere."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AstroTransit — TESS Transit Keşif Konsolu")
        self.resize(1180, 720)
        self._worker: Optional[AnalysisWorker] = None
        self._roots = output_roots(project_root())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_run_tab(), "Analiz")
        self.tabs.addTab(self._build_results_tab(), "Sonuçlar")
        self.tabs.addTab(self._build_json_tab(), "Kayıtlı Çıktılar")
        self.tabs.addTab(self._build_log_tab(), "Log")
        self.setCentralWidget(self.tabs)

    # ── Analiz sekmesi ────────────────────────────────────────

    def _build_run_tab(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        form_panel = QWidget()
        form = QFormLayout(form_panel)
        form.setSpacing(10)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Tek Hedef", "Toplu Hedefler"])
        form.addRow("Mod", self.mode_combo)

        self.target_edit = QLineEdit("TIC 261136679")
        form.addRow("TIC ID (tek)", self.target_edit)

        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText("CSV dosyası ya da virgülle ayrılmış TIC listesi")
        form.addRow("Toplu", self.batch_edit)
        browse_button = QPushButton("CSV Seç…")
        browse_button.clicked.connect(self._pick_batches_csv)
        form.addRow("", browse_button)

        self.sectors_edit = QLineEdit()
        self.sectors_edit.setPlaceholderText("Örn. 14,15 (boş = tümü)")
        form.addRow("Sektörler", self.sectors_edit)

        self.force_map_check = QCheckBox("Sadece MAP")
        self.force_map_check.setChecked(True)
        self.skip_viz_check = QCheckBox("Görsel atla")
        self.skip_catalog_check = QCheckBox("Katalog sorgusu atla")
        form.addRow("", self.force_map_check)
        form.addRow("", self.skip_viz_check)
        form.addRow("", self.skip_catalog_check)

        self.run_button = QPushButton("Analizi Başlat")
        run_font = QFont()
        run_font.setBold(True)
        self.run_button.setFont(run_font)
        self.run_button.clicked.connect(self._start_analysis)
        form.addRow("", self.run_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        form.addRow("İlerleme", self.progress_bar)
        self.progress_label = QLabel("")
        form.addRow("", self.progress_label)

        summary_label = QLabel(
            "Çıktılar ProjectPaths üzerinden outputs/ dizinine yazılır.\n"
            "Loglar 'Log' sekmesinde gerçek zamanlı aktarılır."
        )
        summary_label.setWordWrap(True)
        form.addRow(summary_label)
        splitter.addWidget(form_panel)

        self.run_results_table = self._build_table()
        splitter.addWidget(self.run_results_table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        return panel

    def _pick_batches_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Hedef CSV seç", str(project_root() / "benchmarks"), "CSV (*.csv)"
        )
        if path:
            self.batch_edit.setText(path)

    def _collect_batch_targets(self) -> list[str]:
        raw = self.batch_edit.text().strip()
        if not raw:
            return []
        maybe_csv = Path(raw)
        if maybe_csv.suffix.lower() == ".csv":
            if not maybe_csv.exists():
                raise ValueError(f"CSV bulunamadı: {raw}")
            entries = [
                line.strip().split(",")[0]
                for line in maybe_csv.read_text(encoding="utf-8").splitlines()[1:]
                if line.strip()
            ]
            return entries
        return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]

    def _start_analysis(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "Analiz", "Devam eden bir analiz var.")
            return
        try:
            from desktop.analysis import AnalysisError

            mode = self.mode_combo.currentText()
            if mode == "Tek Hedef":
                targets = [self.target_edit.text().strip()]
                if not targets[0]:
                    raise AnalysisError("TIC ID boş olamaz.")
            else:
                targets = self._collect_batch_targets()
                if not targets:
                    raise AnalysisError("Toplu hedef listesi boş.")
            sectors = parse_sectors(self.sectors_edit.text())
        except ValueError as error:
            QMessageBox.critical(self, "Girdi hatası", str(error))
            return

        config = AnalysisConfig(
            targets=targets,
            sectors=sectors,
            force_map=self.force_map_check.isChecked(),
            force_mcmc=not self.force_map_check.isChecked(),
            skip_visualization=self.skip_viz_check.isChecked(),
            skip_catalog=self.skip_catalog_check.isChecked(),
            log_level="INFO",
        )

        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Kuruluyor…")
        self._worker = AnalysisWorker(config)
        self._worker.log_line.connect(self.append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_analysis_finished)
        self._worker.failed.connect(self._on_analysis_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int, target: str) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(f"[{done}/{total}] {target}")

    def _on_analysis_finished(self, results: Any) -> None:
        self.run_button.setEnabled(True)
        self.progress_bar.setValue(self.progress_bar.maximum() or 100)
        rows: list[dict[str, Any]] = []
        for result in results or []:
            rows.extend(sector_rows(result))
        self._fill_table(self.run_results_table, rows)
        summary = AnalysisWorker.summarize(results or [])
        self.progress_label.setText(f"Tamamlandı — {summary}")
        self.append_log(f"Analiz tamamlandı — {summary}")
        self.tabs.setCurrentIndex(1)

    def _on_analysis_failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.progress_label.setText("Başarısız")
        self.append_log(f"HATA: {message}")
        QMessageBox.critical(self, "Analiz hatası", message)

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _build_log_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        return panel

    # ── Sonuçlar / tablo ──────────────────────────────────────

    def _build_results_tab(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        self.results_table = self._build_table()
        layout.addWidget(self.results_table)

        refresh = QPushButton("Kayıtlı JSON çıktılarını yükle")
        refresh.clicked.connect(self._load_saved_json)
        layout.addWidget(refresh)
        return panel

    def _build_json_tab(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        self.json_table = self._build_table()
        layout.addWidget(self.json_table)
        refresh = QPushButton("Yenile")
        refresh.clicked.connect(self._load_saved_json)
        layout.addWidget(refresh)
        return panel

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(RESULT_TABLE_COLUMNS))
        table.setHorizontalHeaderLabels(RESULT_TABLE_COLUMNS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.cellClicked.connect(self._show_row_detail)
        return table

    def _fill_table(self, table: QTableWidget, rows: list[dict[str, Any]]) -> None:
        table.setRowCount(0)
        for row_index, row in enumerate(rows):
            table.insertRow(row_index)
            for col_index, key in enumerate(RESULT_TABLE_COLUMNS):
                value = row.get(key, "")
                if isinstance(value, float):
                    item = QTableWidgetItem(f"{value:.3f}")
                elif isinstance(value, bool):
                    item = QTableWidgetItem("✓" if value else "✗")
                else:
                    item = QTableWidgetItem(
                        "" if value is None else str(value)
                    )
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_index, col_index, item)

    def _load_saved_json(self) -> None:
        rows = rows_from_json_files(list_json_results(self._roots))
        self._fill_table(self.json_table, rows)

    # ── Detay pencere ─────────────────────────────────────────

    def _show_row_detail(self, row_index: int, _column: int) -> None:
        sender_table = self.sender()
        if not isinstance(sender_table, QTableWidget):
            return
        target_item = sender_table.item(row_index, 0)
        sector_item = sender_table.item(row_index, 1)
        if target_item is None:
            return
        target_id = target_item.text()
        try:
            sector = int(sector_item.text())
        except (TypeError, ValueError):
            sector = 0
        dialog = DetailDialog(self, target_id, sector, find_figures(self._roots, target_id, sector))
        dialog.exec()


class DetailDialog(QDialog):
    """Tek adayın metrikleri ve görselleri."""

    def __init__(
        self,
        parent: QWidget,
        target_id: str,
        sector: int,
        figures: list[Path],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Detay — {target_id} S{sector:02d}")
        self.resize(720, 560)
        layout = QVBoxLayout(self)

        header = QLabel(f"Hedef: {target_id}  •  Sektör: {sector}")
        f = QFont()
        f.setBold(True)
        header.setFont(f)
        layout.addWidget(header)

        info = QLabel(f"{len(figures)} görsel bulundu (kanıt zinciri sırasında).")
        layout.addWidget(info)

        for path in figures[:4]:
            caption = QLabel(figure_caption(path))
            layout.addWidget(caption)
            image_label = QLabel()
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    760, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                image_label.setPixmap(scaled)
            else:
                image_label.setText(f"Görsel okunamadı: {path}")
            layout.addWidget(image_label)


__all__ = ["DetailDialog", "MainWindow"]
