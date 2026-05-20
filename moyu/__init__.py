"""MOYU — Zero-trust memory toolkit for AI Agents.

Usage:
    from moyu import context_manager
    from moyu.agent_memory import search
    from moyu.security import verify_operation
"""

import sys
from moyu_toolkit import context_manager
from moyu_toolkit import agent_memory
from moyu_toolkit import security
from moyu_toolkit import forgetting_curve
from moyu_toolkit import updater
from moyu_toolkit import knowledge_graph
from moyu_toolkit import session_bridge
from moyu_toolkit import learner
from moyu_toolkit import memory_merge
from moyu_toolkit import active_context
from moyu_toolkit import self_reflection
from moyu_toolkit import knowledge_base
from moyu_toolkit import moyu_wake
from moyu_toolkit._moyu_paths import get_default_storage, get_config_path

# Expose submodules so from moyu.xxx import yyy works
for _name, _mod in [
    ("context_manager", context_manager),
    ("agent_memory", agent_memory),
    ("security", security),
    ("forgetting_curve", forgetting_curve),
    ("updater", updater),
    ("knowledge_graph", knowledge_graph),
    ("session_bridge", session_bridge),
    ("learner", learner),
    ("memory_merge", memory_merge),
    ("active_context", active_context),
    ("self_reflection", self_reflection),
    ("knowledge_base", knowledge_base),
    ("moyu_wake", moyu_wake),
]:
    sys.modules[f"moyu.{_name}"] = _mod

__version__ = updater.VERSION
