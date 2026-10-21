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
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
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
from desktop.worker import AnalysisWorker, DiscoveryWorker


def _field_label(text: str) -> QLabel:
    """Form alanı etiketi (tema sınıfı fieldLabel)."""

    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


class MainWindow(QMainWindow):
    """AstroTransit ana pencere."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AstroTransit — TESS Transit Keşif Konsolu")
        self.resize(1280, 760)
        self.setMinimumSize(980, 640)
        self._worker: Optional[AnalysisWorker | DiscoveryWorker] = None
        self._roots = output_roots(project_root())

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_run_tab(), "Analiz")
        self.tabs.addTab(self._build_results_tab(), "Sonuçlar")
        self.tabs.addTab(self._build_json_tab(), "Kayıtlı Çıktılar")
        self.tabs.addTab(self._build_log_tab(), "Log")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

    # ── Üst banner ────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 10, 22, 8)
        column = QVBoxLayout()
        column.setContentsMargins(6, 0, 0, 0)
        column.setSpacing(1)
        title = QLabel("✦  ASTROTRANSIT")
        title.setObjectName("appTitle")
        column.addWidget(title)
        subtitle = QLabel(
            "TESS ışık eğrisi transit keşfi — Bakus et al. 2024, 2025"
        )
        subtitle.setObjectName("appSubtitle")
        column.addWidget(subtitle)
        layout.addLayout(column)
        layout.addStretch(1)
        version_label = QLabel("AstroTransit v1.0")
        version_label.setObjectName("appSubtitle")
        layout.addWidget(version_label)
        return header

    # ── Analiz sekmesi ────────────────────────────────────────

    def _build_run_tab(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 12)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Sol form sütunu: içerik pencereye sığmazsa kaydırılır (satırlar
        # asla üst üste binmez); widgetResizable ile genişlik uyumu otomatik.
        form_panel = QWidget()
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QScrollArea.NoFrame)
        form_scroll.setWidget(form_panel)
        splitter.addWidget(form_scroll)
        form = QFormLayout(form_panel)
        form.setSpacing(10)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Tek Hedef", "Toplu Hedefler", "Otomatik Keşif"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        form.addRow(_field_label("Mod"), self.mode_combo)

        self.target_edit = QLineEdit("TIC 261136679")
        self.target_edit.setMaximumWidth(420)
        form.addRow(_field_label("TIC ID (tek)"), self.target_edit)

        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText("CSV dosyası ya da virgülle ayrılmış TIC listesi")
        self.batch_edit.setMaximumWidth(420)
        form.addRow(_field_label("Toplu"), self.batch_edit)
        browse_button = QPushButton("CSV Seç…")
        browse_button.setObjectName("secondary")
        browse_button.setMaximumWidth(420)
        browse_button.clicked.connect(self._pick_batches_csv)
        form.addRow("", browse_button)

        self.discovery_spin = QSpinBox()
        self.discovery_spin.setRange(1, 20)
        self.discovery_spin.setValue(5)
        self.discovery_spin.setMaximumWidth(200)
        self.discovery_spin.setToolTip(
            "TIC girmeden bu kadar hedef otomatik seçilir:\n"
            "MAST TESS-SPOC envanterinden rastgele sektör, indirilebilir hedefler."
        )
        form.addRow(_field_label("Hedef Sayısı (keşif)"), self.discovery_spin)
        discovery_hint = QLabel(
            "TIC girmeden N hedef: verisi mevcut rastgele SPOC hedefleri taranır."
        )
        discovery_hint.setObjectName("appSubtitle")
        discovery_hint.setWordWrap(True)
        form.addRow("", discovery_hint)

        self.sectors_edit = QLineEdit()
        self.sectors_edit.setPlaceholderText("Örn. 14,15 (boş = tümü)")
        self.sectors_edit.setMaximumWidth(420)
        form.addRow(_field_label("Sektörler"), self.sectors_edit)

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

        # ── Analiz Parametreleri paneli (butonun hızla ardında) ──
        self.params_group = QGroupBox("⚙  Analiz Parametreleri")
        self.params_group.setObjectName("paramsGroup")
        params_grid = QGridLayout(self.params_group)
        params_grid.setVerticalSpacing(7)
        params_grid.setHorizontalSpacing(8)
        self._param_fields: dict[str, QLineEdit] = {}
        seen_labels = {
            "period_days": "Periyot (gün)",
            "t0_btjd": "T0 (BTJD)",
            "rp_rs": "Rp/Rs",
            "impact_parameter": "b (etki)",
            "a_over_rs": "a/Rs",
            "inclination_deg": "i (°)",
            "planet_radius_rearth": "Re (R⊕)",
            "planet_radius_rjup": "Rj (Rjup)",
            "semi_major_axis_au": "Au (AU)",
            "teff_k": "Sıcaklık (K)",
            "log_l_lsun": "Log L (L☉)",
        }
        for idx, (key, text) in enumerate(seen_labels.items()):
            edit = QLineEdit()
            edit.setPlaceholderText("default")
            edit.setMinimumSize(96, 26)
            edit.setToolTip(
                {
                    "period_days": "Kısıtlı doğrulama için T0 ile birlikte doldurun.",
                    "t0_btjd": "Birinci transit zamanı (BTJD); Periyot ile birlikte zorunlu.",
                    "impact_parameter": "Boş bırakılırsa a/Rs + i geometrisinden hesaplanır.",
                    "teff_k": "Log L ile birlikte girilirse yıldız yarıçapı formülle hesaplanır.",
                    "log_l_lsun": "log10(L/L☉); Sıcaklık ile birlikte girilirse R★ hesaplanır.",
                }.get(key, "Boş = varsayılan/katalog değeri.")
            )
            row, col = divmod(idx, 2)
            label = QLabel(text)
            label.setMinimumSize(82, 26)
            params_grid.addWidget(label, row, col * 2)
            params_grid.addWidget(edit, row, col * 2 + 1)
            self._param_fields[key] = edit
        params_hint = QLabel(
            "Boş bırakılan alanlar varsayılanla arar. Periyot + T0 doluysa\n"
            "kör arama yerine KISITLI DOĞRULAMA (MAP fit) yapılır."
        )
        params_hint.setObjectName("appSubtitle")
        params_grid.addWidget(params_hint, params_grid.rowCount(), 0, 1, 4)
        form.addRow("", self.params_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        form.addRow(_field_label("İlerleme"), self.progress_bar)
        self.progress_label = QLabel("")
        form.addRow("", self.progress_label)

        summary_label = QLabel(
            "Çıktılar outputs/ dizinine yazılır; ayrıntılı sonuçlar 'Sonuçlar' sekmesinde,\n"
            "gerçek zamanlı loglar 'Log' sekmesinde görünür."
        )
        summary_label.setObjectName("appSubtitle")
        summary_label.setWordWrap(True)
        form.addRow(summary_label)
        # form_scroll zaten splitter'a eklendi (satır ~124)

        self.run_results_table = self._build_table()
        splitter.addWidget(self.run_results_table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([660, 560])
        self._on_mode_changed(self.mode_combo.currentText())
        return panel

    def _on_mode_changed(self, mode: str) -> None:
        """Girdi alanlarını moda göre açar/kapatır ve buton metnini uyarlar."""

        discovery = mode == "Otomatik Keşif"
        single = mode == "Tek Hedef"
        batch = mode == "Toplu Hedefler"
        self.target_edit.setEnabled(single)
        self.batch_edit.setEnabled(batch)
        self.discovery_spin.setEnabled(discovery)
        self.sectors_edit.setEnabled(not discovery)
        # Analiz parametreleri yalnız Tek Hedef modunda anlamlı
        self.params_group.setEnabled(single)
        self.run_button.setText(
            "Keşif + Analizi Başlat" if discovery else "Analizi Başlat"
        )

    def _collect_plan_params(self) -> Optional[dict[str, str]]:
        """Panel alanlarını sözlük olarak toplar; tamamen boşsa None."""

        values = {key: edit.text() for key, edit in self._param_fields.items()}
        if all(v.strip() == "" for v in values.values()):
            return None
        return values

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
            discovery = mode == "Otomatik Keşif"
            if mode == "Tek Hedef":
                targets = [self.target_edit.text().strip()]
                if not targets[0]:
                    raise AnalysisError("TIC ID boş olamaz.")
            elif mode == "Toplu Hedefler":
                targets = self._collect_batch_targets()
                if not targets:
                    raise AnalysisError("Toplu hedef listesi boş.")
            else:
                targets = []  # keşif worker'ı doldurur
            sectors = [] if discovery else parse_sectors(self.sectors_edit.text())
            plan_values = self._collect_plan_params()
            plan_params = None
            if plan_values:
                from astrotransit.pipelines.plan_params import (
                    plan_params_from_user_input,
                )

                if mode != "Tek Hedef":
                    raise AnalysisError(
                        "Analiz Parametreleri yalnız 'Tek Hedef' modunda kullanılabilir."
                    )
                try:
                    plan_params = plan_params_from_user_input(plan_values)
                except ValueError as error:
                    raise AnalysisError(str(error)) from error
        except ValueError as error:
            QMessageBox.critical(self, "Girdi hatası", str(error))
            return

        base_config = AnalysisConfig(
            targets=targets,
            sectors=sectors,
            force_map=self.force_map_check.isChecked(),
            force_mcmc=not self.force_map_check.isChecked(),
            skip_visualization=self.skip_viz_check.isChecked(),
            skip_catalog=self.skip_catalog_check.isChecked(),
            log_level="INFO",
            plan_params=plan_params,
        )

        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Kuruluyor…")
        if discovery:
            count = self.discovery_spin.value()
            self.progress_label.setText(f"Keşif başlıyor ({count} hedef)…")
            self._worker = DiscoveryWorker(count, base_config)
        else:
            self._worker = AnalysisWorker(base_config)
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
