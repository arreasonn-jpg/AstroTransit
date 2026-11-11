"""AstroTransit masaüstü ana penceresi v2 (PySide6).

Profesyonel restorasyon: kenar çubuğu navigasyonu + sayfa yapısı,
durum çipleri, metrik kartları, programatik marka (branding) ve
QSettings ile oturum kalıcılığı. İş mantığı `desktop.analysis` /
`desktop.helpers` içinde kalır; bu modül yalnızca pencere, tablo ve
sinyal bağlantılarını kurar. Görsel katman olduğu için coverage
dışıdır (pyproject omit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
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
from desktop.theme import BORDER
from desktop.worker import AnalysisWorker, DiscoveryWorker

# ── Navigasyon tanımı: (sayfa anahtarı, buton etiketi, sayfa başlığı) ──
NAV_PAGES = [
    ("run", "▶  Analiz", "Analiz Konsolu"),
    ("results", "◎  Sonuçlar", "Sonuçlar"),
    ("library", "▤  Çıktı Kütüphanesi", "Kayıtlı Çıktılar"),
    ("log", "⌗  Konsol", "Gerçek Zamanlı Konsol"),
    ("about", "ⓘ  Hakkında", "Hakkında"),
]


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
        self.resize(1360, 820)
        self.setMinimumSize(1020, 660)
        self._worker: Optional[AnalysisWorker | DiscoveryWorker] = None
        self._roots = output_roots(project_root())
        self._settings = QSettings("AstroTransit", "Desktop")

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_topbar())
        self.pages = QStackedWidget()
        right_layout.addWidget(self.pages, 1)
        root_layout.addWidget(right_column, 1)

        self._build_pages()  # self.pages'e sırayla ekler
        self._install_shortcuts()
        self.setCentralWidget(central)
        self._restore_settings()
        self._select_nav(0)
        self._set_chip("Hazır", "info")

    # ── Kenar çubuğu / üst bar / sayfalar ────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 16, 10, 14)
        layout.setSpacing(2)

        brand_title = QLabel("✦ ASTROTRANSIT")
        brand_title.setObjectName("brandMini")
        layout.addWidget(brand_title)
        brand_sub = QLabel("Keşif Konsolu")
        brand_sub.setObjectName("appSubtitle")
        layout.addWidget(brand_sub)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER};")
        layout.addSpacing(10)
        layout.addWidget(divider)

        self._nav_group = QButtonGroup(self)
        self._nav_buttons: dict[int, QToolButton] = {}
        for page_index, (_key, label, _title) in enumerate(NAV_PAGES):
            button = QToolButton()
            button.setObjectName("navBtn")
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, idx=page_index: self._select_nav(idx)
            )
            self._nav_group.addButton(button, page_index)
            layout.addWidget(button)
            self._nav_buttons[page_index] = button

        layout.addStretch(1)

        self.version_label = QLabel(f"AstroTransit {self._version()}")
        self.version_label.setObjectName("appSubtitle")
        layout.addWidget(self.version_label)
        return sidebar

    @staticmethod
    def _version() -> str:
        """Paket sürümü (kurulu değilse geliştirme etiketi)."""

        try:
            from importlib.metadata import version as _version

            return f"v{_version('astrotransit')}"
        except Exception:
            return "v-dev"

    def _build_topbar(self) -> QWidget:
        topbar = QWidget()
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(22, 14, 22, 10)
        self.page_title = QLabel("Analiz Konsolu")
        self.page_title.setObjectName("pageHeader")
        layout.addWidget(self.page_title)
        layout.addStretch(1)

        self.chip = QFrame()
        self.chip.setObjectName("chip")
        self.chip.setProperty("chipTone", "info")
        chip_layout = QHBoxLayout(self.chip)
        chip_layout.setContentsMargins(12, 4, 12, 4)
        self.chip_label = QLabel("Hazır")
        self.chip_label.setObjectName("appSubtitle")
        self.chip_label.setStyleSheet("color: inherit; font-weight: 700;")
        chip_layout.addWidget(self.chip_label)
        layout.addWidget(self.chip)
        return topbar

    def _build_pages(self) -> None:
        self.pages.addWidget(self._build_run_page())
        self.pages.addWidget(self._build_results_page())
        self.pages.addWidget(self._build_library_page())
        self.pages.addWidget(self._build_log_page())
        self.pages.addWidget(self._build_about_page())

    # ── Analiz sayfası ───────────────────────────────────────

    def _build_run_page(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 6, 14, 12)
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
        self.target_edit.setPlaceholderText("TIC 123456789")
        self.target_edit.returnPressed.connect(self._start_analysis)
        form.addRow(_field_label("TIC ID (tek)"), self.target_edit)

        self.batch_edit = QLineEdit()
        self.batch_edit.setPlaceholderText("CSV dosyası ya da virgülle ayrılmış TIC listesi")
        self.batch_edit.setMaximumWidth(420)
        form.addRow(_field_label("Toplu"), self.batch_edit)
        browse_button = QPushButton("CSV Seç…")
        browse_button.setObjectName("secondary")
        browse_button.setMaximumWidth(420)
        browse_button.setCursor(Qt.PointingHandCursor)
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

        self.run_button = QPushButton("▶  ️Analizi Başlat")
        self.run_button.setObjectName("runBtn")
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.setToolTip("Ctrl+Enter da çalıştırır")
        self.run_button.clicked.connect(self._start_analysis)
        form.addRow("", self.run_button)

        # ── Analiz Parametreleri paneli (butonun hemen ardında) ──
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
        for idx, (key, label_text) in enumerate(seen_labels.items()):
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
            label = QLabel(label_text)
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
            "Çıktılar outputs/ dizinine yazılır ayrıntılı sonuçlar 'Sonuçlar' sayfasında,\n"
            "gerçek zamanlı loglar 'Konsol' sayfasında görünür."
        )
        summary_label.setObjectName("appSubtitle")
        summary_label.setWordWrap(True)
        form.addRow(summary_label)

        self.run_results_table = self._build_table()
        splitter.addWidget(self.run_results_table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([660, 620])
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
            "✧  Keşif + Analiz" if discovery else "▶  Analizi Başlat"
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
        self._set_chip("Çalışıyor…", "warn")

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
        self._fill_metric_cards(results or [])
        self._select_nav(1)
        self._set_chip("Tamamlandı ✓", "ok")

    def _on_analysis_failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.progress_label.setText("Başarısız")
        self.append_log(f"HATA: {message}")
        self._set_chip("Hata ✕", "danger")
        QMessageBox.critical(self, "Analiz hatası", message)

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    # ── Sonuçlar / çıktı kütüphanesi / konsol / hakkında ─────

    def _build_results_page(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 6, 22, 12)
        layout.setSpacing(10)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self.metric_cards: dict[str, QLabel] = {}
        for key, title in (
            ("targets", "HEDEF"),
            ("success", "BAŞARILI SEKTÖR"),
            ("confirmed", "ONAYLI ADAY"),
        ):
            cards_row.addWidget(self._build_metric_card(key, title))
        cards_row.addStretch(1)
        layout.addLayout(cards_row)

        self.results_table = self._build_table()
        layout.addWidget(self.results_table, 1)
        hint = QLabel(
            "Adaylara tıklayınca detay penceresi açılır (metrikler + kullanım görselleri)."
        )
        hint.setObjectName("appSubtitle")
        layout.addWidget(hint)
        return panel

    def _build_metric_card(self, key: str, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumSize(180, 74)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_title = QLabel(title)
        card_title.setObjectName("metricTitle")
        card_layout.addWidget(card_title)
        value = QLabel("0")
        value.setObjectName("metricValue")
        card_layout.addWidget(value)
        self.metric_cards[key] = value
        return card

    def _build_library_page(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 6, 22, 12)
        layout.setSpacing(10)

        row = QHBoxLayout()
        hint = QLabel("outputs/ dizinindeki kayıtlı JSON kanıt dosyasi yüklenir.")
        hint.setObjectName("appSubtitle")
        row.addWidget(hint)
        row.addStretch(1)
        refresh = QPushButton("⟳  Yenile")
        refresh.setObjectName("secondary")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self._load_saved_json)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.json_table = self._build_table()
        layout.addWidget(self.json_table, 1)
        return panel

    def _build_log_page(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 6, 22, 12)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)
        return panel

    def _build_about_page(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 6, 22, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setSpacing(10)

        about = QLabel(
            "✦ AstroTransit, TESS ışık eğrilerinde transit keşfi için geliştirilmiş\n"
            "bir analiz konsoludur. Pipeline akışı:\n"
            "\n"
            "  1) SPOC ışık eğrisi indirme + ürün doğrulama\n"
            "  2) Kalite maskeleme + wotan detrending (BLS→TLS kademeli algılama)\n"
            "  3) MAP fit (MCMC ancak istek üzerine) ile fiziksel parametreler\n"
            "  4) Kalite katmanı: S/N, FPP, yanlış-pozitif metrikleri\n"
            "  5) outputs/ altında JSON kanıt + sentez görselleri\n"
            "\n"
            "Kısayollar:\n"
            "   Ctrl+Enter        Analizi Başlat\n"
            "   Ctrl+1 … Ctrl+5   Sayfa geçişleri\n"
        )
        about.setWordWrap(True)
        inner.addWidget(about)

        card = QFrame()
        card.setObjectName("card")
        card_msg = QVBoxLayout(card)
        card_msg.setContentsMargins(14, 12, 14, 12)
        card_head = QLabel("Kanıt-first tasarım")
        card_head.setObjectName("pageHeader")
        card_msg.addWidget(card_head)
        card_body = QLabel(
            "Her koşum eşiğini kanıttan ÖNCE ilan eder; kanıt dosyaları hash ile\n"
            "dondurulur ve sonradan eşik kaydırma kapıyı geçersiz kılar."
        )
        card_body.setObjectName("appSubtitle")
        card_body.setWordWrap(True)
        card_msg.addWidget(card_body)
        inner.addWidget(card)
        inner.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return panel

    # ── Navigasyon + çip + pencereleri ───────────────────────

    def _select_nav(self, page_index: int) -> None:
        """Kenar çubuğu butonunu işaretler ve sayfayı açar."""

        button = self._nav_buttons.get(page_index)
        if button is not None:
            button.setChecked(True)
        self.pages.setCurrentIndex(page_index)
        if 0 <= page_index < len(NAV_PAGES):
            self.page_title.setText(NAV_PAGES[page_index][2])

    def _install_shortcuts(self) -> None:
        run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_shortcut.activated.connect(self._start_analysis)
        for idx in range(len(NAV_PAGES)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            shortcut.activated.connect(
                lambda pidx=idx: self._select_nav(pidx)
            )

    def _set_chip(self, text: str, tone: str) -> None:
        """Üst bar durum çipini günceller (dinamik özellik + repolish)."""

        self.chip_label.setText(text)
        self.chip.setProperty("chipTone", tone)
        style = self.chip.style()
        style.unpolish(self.chip)
        style.polish(self.chip)

    # ── Ayarlar (oturum kalıcılığı) ──────────────────────────

    def _restore_settings(self) -> None:
        """Kapatırken kaydedilen girdileri geri yükler."""

        mode = str(self._settings.value("run/mode", ""))
        if mode:
            index = self.mode_combo.findText(mode)
            if index >= 0:
                self.mode_combo.setCurrentIndex(index)
        target = str(self._settings.value("run/target", ""))
        if target:
            self.target_edit.setText(target)
        sectors = str(self._settings.value("run/sectors", ""))
        self.sectors_edit.setText(sectors)
        for key, check in (
            ("force_map", self.force_map_check),
            ("skip_viz", self.skip_viz_check),
            ("skip_catalog", self.skip_catalog_check),
        ):
            value = self._settings.value(f"run/{key}", None)
            if value is None:
                continue
            check.setChecked(str(value) in ("true", "True", "1"))
        plan_values = self._settings.value("run/plan", {})
        if isinstance(plan_values, dict):
            for key, value in plan_values.items():
                edit = self._param_fields.get(str(key))
                if edit is not None:
                    edit.setText(str(value))
        geometry = self._settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        """Kapanışta kullanıcı girdilerini QSettings'e kaydeder."""

        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("run/mode", self.mode_combo.currentText())
        self._settings.setValue("run/target", self.target_edit.text())
        self._settings.setValue("run/sectors", self.sectors_edit.text())
        self._settings.setValue("run/force_map", self.force_map_check.isChecked())
        self._settings.setValue("run/skip_viz", self.skip_viz_check.isChecked())
        self._settings.setValue("run/skip_catalog", self.skip_catalog_check.isChecked())
        self._settings.setValue(
            "run/plan",
            {key: edit.text() for key, edit in self._param_fields.items()},
        )
        super().closeEvent(event)

    # ── Sonuçlar / tablo ─────────────────────────────────────

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(RESULT_TABLE_COLUMNS))
        table.setHorizontalHeaderLabels(RESULT_TABLE_COLUMNS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.cellClicked.connect(self._show_row_detail)
        return table

    def _fill_table(self, table: QTableWidget, rows: list[dict[str, Any]]) -> None:
        # Ölçekli doldurma: tek seferde satır-sayısı ayarlanır; yeniden çizim
        # topluca açılır (yüzlerce satırda UI takılması olmaması için).
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        try:
            table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
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
        finally:
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)

    def _fill_metric_cards(self, results: list[Any]) -> None:
        """Analiz sonucu üç metrik kartını doldurur."""

        n = len(results)
        confirmed = 0
        sector_success = 0
        for result in results:
            confirmed += int(getattr(result, "candidates_confirmed", 0) or 0)
            sector_results = getattr(result, "sector_results", []) or []
            sector_success += sum(
                1 for sector in sector_results if getattr(sector, "success", False)
            )
        if not sector_success:
            sector_success = sum(
                1 for r in results if getattr(r, "success", False)
            )
        self.metric_cards["targets"].setText(str(n))
        self.metric_cards["success"].setText(str(sector_success))
        self.metric_cards["confirmed"].setText(str(confirmed))

    def _load_saved_json(self) -> None:
        rows = rows_from_json_files(list_json_results(self._roots))
        self._fill_table(self.json_table, rows)
        self._select_nav(2)

    # ── Detay pencere ────────────────────────────────────────

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
            sector = int(sector_item.text()) if sector_item else 0
        except (TypeError, ValueError):
            sector = 0
        dialog = DetailDialog(self, target_id, sector, find_figures(self._roots, target_id, sector))
        dialog.exec()


class DetailDialog(QDialog):
    """Tek adayın metrikleri ve görselleri (kaydırılabilir, klasör bağlantılı)."""

    def __init__(
        self,
        parent: QWidget,
        target_id: str,
        sector: int,
        figures: list[Path],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Detay — {target_id} S{sector:02d}")
        self.resize(860, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        header = QLabel(f"Hedef: {target_id}  •  Sektör: {sector}")
        header.setObjectName("pageHeader")
        layout.addWidget(header)

        info = QLabel(f"{len(figures)} görsel bulundu (kanıt zinciri sırasına göre).")
        info.setObjectName("appSubtitle")
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        for path in figures[:6]:
            caption = QLabel(figure_caption(path))
            caption.setObjectName("appSubtitle")
            content_layout.addWidget(caption)
            image_label = QLabel()
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    820, 620, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                image_label.setPixmap(scaled)
            else:
                image_label.setText(f"Görsel okunamadı: {path}")
            content_layout.addWidget(image_label)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        if figures:
            open_dir = QPushButton("📁  Klasörü Aç")
            open_dir.setObjectName("secondary")
            folder = figures[0].parent
            open_dir.clicked.connect(
                lambda: self._open_in_explorer(folder)
            )
            row.addWidget(open_dir)
        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        row.addWidget(close_button)
        layout.addLayout(row)

    def _open_in_explorer(self, folder: Path) -> None:
        """Windows Explorer'da klasörü açar (frozen pakette kullanılan yol)."""

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = folder if folder.exists() else folder.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


__all__ = ["DetailDialog", "MainWindow"]
