"""First-run setup wizard.

Four short screens — language, theme, mode, telemetry opt-in — then
the main window takes over. Skipped if ``Config.first_run_complete``
is already ``True``.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from aegis.core.config import Config
from aegis.core.i18n import available_locales, set_locale, tr
from aegis.ui.theme import current, hex_to_rgb


class _Step(QFrame):
    """One wizard page. Subclasses fill ``self.body`` with widgets."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 14pt; font-weight: 700; color: {current().fg};"
        )
        title_lbl.setWordWrap(True)
        lay.addWidget(title_lbl)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        lay.addLayout(self.body)
        lay.addStretch()


class _LangStep(_Step):
    def __init__(self) -> None:
        super().__init__(tr("wizard.lang.title"))
        self._group = QButtonGroup(self)
        for code, label in available_locales():
            rb = QRadioButton(f"{label}  ({code})")
            rb.setProperty("locale_code", code)
            if code == "en":
                rb.setChecked(True)
            self._group.addButton(rb)
            self.body.addWidget(rb)

    def selected(self) -> str:
        b = self._group.checkedButton()
        return b.property("locale_code") if b else "en"


class _ThemeStep(_Step):
    def __init__(self) -> None:
        super().__init__(tr("wizard.theme.title"))
        self._group = QButtonGroup(self)
        for t in ("dark", "light"):
            rb = QRadioButton(t.capitalize())
            rb.setProperty("theme", t)
            if t == "dark":
                rb.setChecked(True)
            self._group.addButton(rb)
            self.body.addWidget(rb)

    def selected(self) -> str:
        b = self._group.checkedButton()
        return b.property("theme") if b else "dark"


class _ModeStep(_Step):
    def __init__(self) -> None:
        super().__init__(tr("wizard.mode.title"))
        self._group = QButtonGroup(self)
        adv = QRadioButton(tr("wizard.mode.advanced"))
        adv.setProperty("simple", False)
        adv.setChecked(True)
        self._group.addButton(adv)
        self.body.addWidget(adv)
        simple = QRadioButton(tr("wizard.mode.simple"))
        simple.setProperty("simple", True)
        self._group.addButton(simple)
        self.body.addWidget(simple)

    def selected(self) -> bool:
        b = self._group.checkedButton()
        return bool(b.property("simple")) if b else False


class _TelemetryStep(_Step):
    def __init__(self) -> None:
        super().__init__(tr("wizard.telemetry.title"))
        body_lbl = QLabel(tr("wizard.telemetry.body"))
        body_lbl.setWordWrap(True)
        self.body.addWidget(body_lbl)
        self._opt_in = QCheckBox(tr("wizard.telemetry.yes"))
        self.body.addWidget(self._opt_in)

    def selected(self) -> bool:
        return self._opt_in.isChecked()


class FirstRunWizard(QWidget):
    """Modal-ish wizard with Back / Next / Finish buttons."""

    finished = pyqtSignal()  # emitted after Finish

    _STEPS = (_LangStep, _ThemeStep, _ModeStep, _TelemetryStep)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header strip
        header = QLabel(tr("wizard.welcome"))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c = current()
        header.setStyleSheet(
            f"font-size: 18pt; font-weight: 700; padding: 22px 0;"
            f" background: {c.bg2}; color: {c.fg};"
            f" border-bottom: 1px solid {c.border};"
        )
        outer.addWidget(header)

        # Steps
        self._stack = QStackedWidget()
        self._steps: list[_Step] = [Cls() for Cls in self._STEPS]
        for s in self._steps:
            self._stack.addWidget(s)
        outer.addWidget(self._stack, 1)

        # Buttons
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 12, 20, 20)
        self._btn_back = QPushButton("< Back")
        self._btn_next = QPushButton("Next >")
        self._btn_finish = QPushButton(tr("wizard.finish"))
        self._btn_back.clicked.connect(self._on_back)
        self._btn_next.clicked.connect(self._on_next)
        self._btn_finish.clicked.connect(self._on_finish)
        self._btn_finish.setObjectName("primary")
        self._btn_finish.hide()
        bar.addWidget(self._btn_back)
        bar.addStretch()
        bar.addWidget(self._btn_next)
        bar.addWidget(self._btn_finish)
        bw = QFrame(); bw.setLayout(bar)
        bw.setStyleSheet(
            f"background: {c.bg2}; border-top: 1px solid {c.border};"
        )
        outer.addWidget(bw)

        self._update_buttons()

    def _on_back(self) -> None:
        i = self._stack.currentIndex()
        if i > 0:
            self._stack.setCurrentIndex(i - 1)
            self._update_buttons()

    def _on_next(self) -> None:
        i = self._stack.currentIndex()
        # Apply locale on the first Next so the rest of the wizard
        # shows the new language.
        if i == 0:
            set_locale(self._steps[0].selected())
            self._refresh_translations()
        if i < len(self._steps) - 1:
            self._stack.setCurrentIndex(i + 1)
            self._update_buttons()

    def _on_finish(self) -> None:
        self._config.locale = self._steps[0].selected()
        self._config.theme = self._steps[1].selected()
        self._config.simple_mode = self._steps[2].selected()
        self._config.enable_telemetry = self._steps[3].selected()
        self._config.first_run_complete = True
        try:
            self._config.save()
        except Exception:  # noqa: BLE001
            pass
        self.finished.emit()

    def _update_buttons(self) -> None:
        i = self._stack.currentIndex()
        n = len(self._steps)
        self._btn_back.setEnabled(i > 0)
        self._btn_next.setVisible(i < n - 1)
        self._btn_finish.setVisible(i == n - 1)

    def _refresh_translations(self) -> None:
        """Re-apply translations after the language step was confirmed."""
        titles = (
            "wizard.lang.title", "wizard.theme.title",
            "wizard.mode.title", "wizard.telemetry.title",
        )
        for step, key in zip(self._steps, titles):
            step.children()[0].setText(tr(key))  # type: ignore[attr-defined]
        self._btn_finish.setText(tr("wizard.finish"))


def needs_wizard(config: Config) -> bool:
    return not config.first_run_complete