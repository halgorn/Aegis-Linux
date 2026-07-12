"""Lightweight in-process translation.

Ponytail-mode i18n:

* No gettext setup, no .po/.mo files, no Qt Linguist toolchain.
* Each translation is a plain ``dict[str, str]`` in this module.
* Lookups go through :func:`tr`, which picks the right dictionary
  from :data:`_LOCALES` based on :func:`current_locale`.
* Falls back to ``en`` (English) when a key is missing — never
  raises a KeyError, never shows raw English to a non-English user
  if the string was translated under a different spelling.
* :func:`tr` accepts optional ``**kwargs`` for ``str.format``
  interpolation, e.g. ``tr("greeting", name=user)``.

Adding a new locale: drop a ``MESSAGES_xx = {...}`` dict and add
its code to :data:`_LOCALES`.
"""
from __future__ import annotations

import os
from functools import lru_cache

# ── dictionaries ──────────────────────────────────────────────────────────────

MESSAGES_EN: dict[str, str] = {
    "app.title": "Aegis Linux",
    "nav.dashboard": "Dashboard",
    "nav.cleaner": "Cleaner",
    "nav.monitor": "Monitor",
    "nav.performance": "Performance",
    "nav.health": "Health",
    "nav.security": "Security",
    "nav.network": "Network",
    "nav.disks": "Disks",
    "nav.drivers": "Drivers",
    "nav.packages": "Packages",
    "nav.startup": "Startup",
    "nav.restore": "Restore",
    "nav.logs": "Logs",
    "nav.settings": "Settings",
    "greeting.morning": "Good morning",
    "greeting.afternoon": "Good afternoon",
    "greeting.evening": "Good evening",
    "dashboard.subtitle": "Welcome to Aegis Linux on {host}. Here's an overview of your system.",
    "cleaner.title": "Cleaner",
    "cleaner.subtitle": "Select what to clean. Dry-run is on by default - no files are removed until you confirm.",
    "cleaner.select_all": "Select all",
    "cleaner.select_none": "Select none",
    "cleaner.dry_run": "Dry run",
    "cleaner.scan": "Scan",
    "cleaner.clean_selected": "Clean selected",
    "cleaner.cleaning": "Cleaning…",
    "cleaner.total_reclaimable": "Total reclaimable:",
    "cleaner.selection_details": "Selection details",
    "cleaner.no_selection": "No targets selected.",
    "health.title": "Health",
    "health.subtitle": "System wellness score (0-100).",
    "health.run_scan": "Run scan",
    "health.summary_idle": "Run a scan to compute the score.",
    "settings.title": "Settings",
    "settings.appearance": "Appearance",
    "settings.theme": "Theme",
    "settings.accent": "Accent",
    "settings.safety": "Safety",
    "settings.apply": "Apply",
    "settings.dry_run": "Always preview cleaner with dry-run",
    "settings.backup": "Create backup before every clean",
    "settings.simple_mode": "Simple mode (only Dashboard, Cleaner and Health)",
    "settings.applied": "Settings applied.",
    "cleaner.toast_clean_done": "Reclaimed {size} across {n} items.",
    "cleaner.toast_clean_done_dry": "[DRY] Reclaimed {size} across {n} items.",
    "cleaner.toast_clean_failed": "Clean failed: {err}",
    "cleaner.confirm_title": "Confirm cleanup",
    "cleaner.confirm_body": "Delete files from {n} targets?\nThis action is reversible only via the Restore page if a backup was made.",
    "restore.confirm_title": "Confirm restore",
    "restore.confirm_body": "Restore backup #{id}?",
    "restore.toast_done": "Backup #{id} restored.",
    "restore.toast_failed": "Restore failed: {err}",
    "common.cancel": "Cancel",
    "common.refresh": "Refresh",
    "common.apply": "Apply",
    "common.backup_now": "Backup now",
    "common.quick_actions": "Quick actions",
    "wizard.welcome": "Welcome to Aegis Linux",
    "wizard.lang.title": "Choose your language",
    "wizard.theme.title": "Choose a theme",
    "wizard.mode.title": "Choose a complexity level",
    "wizard.mode.simple": "Simple - only the essentials (Dashboard, Cleaner, Health)",
    "wizard.mode.advanced": "Advanced - all 14 pages",
    "wizard.telemetry.title": "Anonymous usage stats",
    "wizard.telemetry.body": "Aegis can collect anonymous crash reports and feature usage to help us improve. No personal data is ever sent. You can change this later in Settings.",
    "wizard.telemetry.yes": "Help improve Aegis",
    "wizard.telemetry.no": "No, keep it local",
    "wizard.finish": "Finish",
    "scan.failed": "{name} failed: {err}",
}

MESSAGES_PT_BR: dict[str, str] = {
    "app.title": "Aegis Linux",
    "nav.dashboard": "Painel",
    "nav.cleaner": "Limpeza",
    "nav.monitor": "Monitor",
    "nav.performance": "Desempenho",
    "nav.health": "Saúde",
    "nav.security": "Segurança",
    "nav.network": "Rede",
    "nav.disks": "Discos",
    "nav.drivers": "Drivers",
    "nav.packages": "Pacotes",
    "nav.startup": "Inicialização",
    "nav.restore": "Restaurar",
    "nav.logs": "Logs",
    "nav.settings": "Configurações",
    "greeting.morning": "Bom dia",
    "greeting.afternoon": "Boa tarde",
    "greeting.evening": "Boa noite",
    "dashboard.subtitle": "Bem-vindo ao Aegis Linux em {host}. Aqui está uma visão geral do seu sistema.",
    "cleaner.title": "Limpeza",
    "cleaner.subtitle": "Selecione o que limpar. O modo de simulação vem ativado - nenhum arquivo é removido até você confirmar.",
    "cleaner.select_all": "Selecionar todos",
    "cleaner.select_none": "Selecionar nenhum",
    "cleaner.dry_run": "Simular",
    "cleaner.scan": "Analisar",
    "cleaner.clean_selected": "Limpar selecionados",
    "cleaner.cleaning": "Limpando…",
    "cleaner.total_reclaimable": "Recuperável total:",
    "cleaner.selection_details": "Detalhes da seleção",
    "cleaner.no_selection": "Nenhum alvo selecionado.",
    "health.title": "Saúde",
    "health.subtitle": "Pontuação de saúde do sistema (0-100).",
    "health.run_scan": "Analisar",
    "health.summary_idle": "Execute uma análise para calcular a pontuação.",
    "settings.title": "Configurações",
    "settings.appearance": "Aparência",
    "settings.theme": "Tema",
    "settings.accent": "Cor de destaque",
    "settings.safety": "Segurança",
    "settings.apply": "Aplicar",
    "settings.dry_run": "Sempre simular antes de limpar",
    "settings.backup": "Criar backup antes de cada limpeza",
    "settings.simple_mode": "Modo simples (apenas Painel, Limpeza e Saúde)",
    "settings.applied": "Configurações aplicadas.",
    "cleaner.toast_clean_done": "Recuperado {size} em {n} itens.",
    "cleaner.toast_clean_done_dry": "[SIMULAÇÃO] Recuperado {size} em {n} itens.",
    "cleaner.toast_clean_failed": "Falha na limpeza: {err}",
    "cleaner.confirm_title": "Confirmar limpeza",
    "cleaner.confirm_body": "Excluir arquivos de {n} alvos?\nEsta ação é reversível apenas pela página Restaurar, se um backup foi criado.",
    "restore.confirm_title": "Confirmar restauração",
    "restore.confirm_body": "Restaurar backup #{id}?",
    "restore.toast_done": "Backup #{id} restaurado.",
    "restore.toast_failed": "Falha ao restaurar: {err}",
    "common.cancel": "Cancelar",
    "common.refresh": "Atualizar",
    "common.apply": "Aplicar",
    "common.backup_now": "Fazer backup agora",
    "common.quick_actions": "Ações rápidas",
    "wizard.welcome": "Bem-vindo ao Aegis Linux",
    "wizard.lang.title": "Escolha seu idioma",
    "wizard.theme.title": "Escolha um tema",
    "wizard.mode.title": "Escolha o nível de complexidade",
    "wizard.mode.simple": "Simples - apenas o essencial (Painel, Limpeza, Saúde)",
    "wizard.mode.advanced": "Avançado - todas as 14 páginas",
    "wizard.telemetry.title": "Estatísticas anônimas de uso",
    "wizard.telemetry.body": "O Aegis pode coletar relatórios anônimos de falhas e uso de funções para nos ajudar a melhorar. Nenhum dado pessoal é enviado. Você pode mudar isso depois em Configurações.",
    "wizard.telemetry.yes": "Quero ajudar a melhorar",
    "wizard.telemetry.no": "Não, manter local",
    "wizard.finish": "Concluir",
    "scan.failed": "{name} falhou: {err}",
}

_LOCALES: dict[str, dict[str, str]] = {
    "en": MESSAGES_EN,
    "pt-BR": MESSAGES_PT_BR,
}

SUPPORTED: tuple[str, ...] = tuple(_LOCALES.keys())


@lru_cache(maxsize=1)
def current_locale() -> str:
    """Pick the active locale from env or config; cached."""
    # 1. explicit env override (used by tests)
    env = os.environ.get("AEGIS_LANG", "").strip()
    if env in _LOCALES:
        return env
    # 2. system LANG/LC_ALL
    for var in ("LC_ALL", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v:
            short = v.split(".")[0].replace("_", "-")
            if short in _LOCALES:
                return short
            prefix = short.split("-")[0]
            for code in _LOCALES:
                if code.startswith(prefix):
                    return code
    return "en"


def set_locale(code: str) -> None:
    """Override the cached locale (used after config update)."""
    if code in _LOCALES:
        current_locale.cache_clear()
        os.environ["AEGIS_LANG"] = code


def tr(key: str, **kwargs) -> str:
    """Translate ``key`` using :func:`current_locale`; format with kwargs.

    Falls back to English if the active locale is missing the key,
    then falls back to the key itself if English is also missing it
    (so missing translations never crash the UI).
    """
    loc = current_locale()
    msg = _LOCALES.get(loc, MESSAGES_EN).get(key)
    if msg is None and loc != "en":
        msg = MESSAGES_EN.get(key)
    if msg is None:
        return key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg


def available_locales() -> list[tuple[str, str]]:
    """Return [(code, label), ...] for the locale picker."""
    return [("en", "English"), ("pt-BR", "Português (Brasil)")]