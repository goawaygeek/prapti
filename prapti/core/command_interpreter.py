"""
    Interpret commands
        command processing :
            update message sequence in-place
            update configuration in-place
"""
import re

from ._core_execution_state import get_private_core_state
from .execution_state import ExecutionState
from .configuration import assign_field
from .command_message import Command, Message
from .action import Action, ActionContext
from .source_location import SourceLocation

def _join_alternatives(alternatives: list[str]):
    return ", ".join(alternatives[:-1]) + " or " + alternatives[-1]

def run_action(has_exclamation: bool, action_name: str, raw_args: str, source_loc: SourceLocation, state: ExecutionState) -> None|str|Message:
    core_state = get_private_core_state(state)
    #state.log.debug(f"running action '{'!' if has_exclamation else ''}{action_name}' with raw args '{raw_args}'", source_loc)

    matches: list[Action] = core_state.actions.lookup_action(action_name)
    match len(matches):
        case 0:
            state.log.error("action-not-found", f"couldn't run action '{action_name}'. action not found.", source_loc)
        case 1:
            action = matches[0]
            if action.exclamation_only and not has_exclamation:
                state.log.error("excl-only-action-without-excl", f"didn't run action '{action_name}'. action is !-only but written without a '!'", source_loc)
                return None

            context = ActionContext(state=state, root_config=state.root_config, plugin_config=action.plugin_config, source_loc=source_loc, log=state.log)
            return action.function(action_name, raw_args, context)
        case _:
            alternatives = _join_alternatives([action.qualified_name for action in matches])
            state.log.error("ambiguous-action-name", f"didn't run action '{action_name}'. action name is ambiguous, did you mean: {alternatives}", source_loc)
    return None

# process '%' commands -------------------------------------------------------
# i.e. set configuration fields and run actions

command_regex = re.compile(r"^(!)?\s*([\w\-_./\\]+)(?:\s*(=)|\s+|$)(.*)")
# Regex that matches valid command text (starting with the first non-whitespace
# character after the '%')
# Explanation:
# - `^(!)?` matches an optional exclamation mark at the beginning of the command.
# - `\s*` matches zero or more whitespace characters (spaces and tabs).
# - `([\w\-_./\\]+)` matches the command name. It allows alphanumeric characters, hyphens,
#   underscores, periods, forward slashes, and backslashes.
# - `(?:\s*(=)|\s+|$)` matches either optional whitespace followed by an equal sign (`\s*(=)`)
#   or more whitespace characters (`\s+`) or the end of input(`$`). The `=` is captured as a separate group.
# - `(.*)` matches any remaining characters after the command, if any.

def _interpret_command(command_text: str, is_final_message: bool, source_loc: SourceLocation, state: ExecutionState) -> None|str|Message:
    """
    Interpret one command

    Recognised commands are of two types: 1. assignment, 2. action
    The syntax of a command (after the '%') is either"
      [!] action-name [... args ...]
    or
      [!] field-name = value string
    where action-name and field-name have the same permitted characters: alphanumeric, -_./
    """
    result = None
    if match := re.match(command_regex, command_text):
        has_exclamation = bool(match.group(1))
        name = match.group(2)
        equals_sign = match.group(3)
        rhs = match.group(4).strip() if match.group(4) else ""
        #state.log.debug(f"{has_exclamation = }, {name = }, {equals_sign = }, {rhs = }", source_loc)

        if not has_exclamation or (has_exclamation and is_final_message): # has_exclamation commands only run in final message
            if equals_sign:
                # assignment:
                if len(rhs) == 0: # missing right hand side of assignment
                    state.log.error("skiping-empty-assignment", f"skipping configuration assignment with no right-hand-side '{command_text}'", source_loc)
                else:
                    assign_field(state.root_config, name, rhs, source_loc, state.log)
            else:
                # action:
                result = run_action(has_exclamation, name, rhs, source_loc, state)
    else:
        state.log.error("unknown-command", f"couldn't interpret command '{command_text}'", source_loc)
    return result

def interpret_commands(message_sequence: list[Message], state: ExecutionState, is_final_sequence: bool=False) -> None:
    """"for each enabled message in the sequence, interpret enabled commands. store command results in command.result field
    NOTE: the possible side effects of interpreting commands are:
    - changes to the configuration tree
    - mutation of state or plugin internals, including loading plugins
    - generation of command/action results, which are stored in the command.result field
    this step does not modify the message sequence
    """
    final_message = message_sequence[-1] if is_final_sequence else None
    for message in message_sequence:
        if message.is_enabled:
            is_final_message = message is final_message
            for item in message.content:
                if isinstance(item, Command) and item.is_enabled:
                    item.result = _interpret_command(command_text=item.text, is_final_message=is_final_message, source_loc=item.source_loc, state=state)

# `% config_root = true` helper ----------------------------------------------
# for loading in-tree .prapticonfig.md files

config_root_regex = re.compile(r"^\s*(prapti\.)?(config_root)\s*(=)\s*(true)\s*")
# ^^^ Regex that matches `config_root = true` and `prapti.config_root = true`

def is_config_root(config_message_sequence: list[Message]) -> bool:
    """given a .prapticonfig.md message sequence, return true if `true` is assigned to `prapti.config_root`, without executing or interpreting any commands."""
    for message in config_message_sequence:
        if message.is_enabled:
            for item in message.content:
                if isinstance(item, Command) and item.is_enabled:
                    if re.match(config_root_regex, item.text):
                        return True
    return False
