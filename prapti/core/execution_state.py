from typing import Any
from dataclasses import dataclass, field
import pathlib

from .logger import DiagnosticsLogger
from .configuration import RootConfiguration
from .command_message import Message
from .responder import ResponderContext

@dataclass
class ExecutionState:
    """
        An ExecutionState is the overall state associated with a single run of
        processing a markdown file and producing responses.
    """
    log: DiagnosticsLogger
    input_file_path: pathlib.Path
    user_prapti_config_dir: pathlib.Path|None = None
    prapticonfig_dirs: list[pathlib.Path] = field(default_factory=list)
        # ^^^ in-tree config dirs, ordered starting from dir containing input file and proceding towards root
    root_config: RootConfiguration = field(default_factory=RootConfiguration)
    message_sequence: list[Message] = field(default_factory=list)
    responses: list[Message] = field(default_factory=list)

    selected_responder_context: ResponderContext|None = None

    private_core_state: Any|None = None # private to core. use get_private_core_state() for typesafe access
    test_exfil: dict = field(default_factory=dict) # conduit for test inspection
