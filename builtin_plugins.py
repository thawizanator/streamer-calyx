"""
Phase 14.5: Launch & First-Party Core Plugins
All official core plugins (Ending Credits, Backstage Teleprompter, Encrypted Peer Chat,
StreamElements, Streamlabs) are distributed as signed .calyxplugin packages and downloaded
on-demand from GitHub via PluginManager.
"""
from __future__ import annotations

from typing import Any, Dict, List


def get_builtin_plugin_specs() -> List[Dict[str, Any]]:
    """No hardcoded built-in plugins; all core plugins are downloadable from GitHub."""
    return []
