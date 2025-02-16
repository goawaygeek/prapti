"""
    Koboldcpp text completions responder plugin.

    Targetting the text generation subset of the kobold API supported by koboldcpp

    Kobold API reference: https://petstore.swagger.io/?url=https://lite.koboldai.net/kobold_api.json#/generate/post_generate

    Koboldcpp:  https://github.com/LostRuins/koboldcpp
                https://github.com/LostRuins/koboldcpp/blob/concedo/koboldcpp.py
"""
import datetime
from typing import Literal
import json

import requests
from pydantic import BaseModel, ConfigDict, Field

from ...core.plugin import Plugin, PluginCapabilities, PluginContext
from ...core.command_message import Message
from ...core.configuration import VarRef, resolve_var_refs
from ...core.responder import Responder, ResponderContext
from ...core.logger import DiagnosticsLogger

class KoboldcppResponderConfiguration(BaseModel):
    """Configuration parameters for koboldcpp responder."""
    model_config = ConfigDict(
        validate_assignment=True)

    api_base: str = "http://localhost:5001/api/v1"

    max_context_length: int|None = None
    max_length: int = 50
    temperature: float = 0.8
    top_k: int = 120
    top_a: float = 0.0
    top_p: float = 0.85
    typical_p: float = 1.0 # `typical` in the koboldcpp API
    tfs: float = 1.0
    rep_pen: float = 1.1
    rep_pen_range: int = 128
    mirostat: Literal[0, 1, 2] = 0
    mirostat_tau: float = 5.0
    mirostat_eta: float = 0.1
    sampler_order: list[int] = Field(default_factory=lambda: list([6,0,1,3,4,2,5])) # max len sampler_order_max
    seed: int = -1
    stop_sequence: list[str] = Field(default_factory=list) # max len stop_token_max

    # TODO:
    # n number of generations
    # stream via generate/stream route

def convert_message_sequence_to_text_prompt(message_sequence: list[Message], log: DiagnosticsLogger) -> str:
    result = ""
    for message in message_sequence:
        if not message.is_enabled or message.is_private:
            continue # skip disabled and private messages

        if message.role == "prompt":
            assert len(message.content) == 1 and isinstance(message.content[0], str), "koboldcpp.text: expected flattened message content"
            result += message.content[0]
        elif message.role in ("user", "assistant"):
            log.warning("unsupported-chat-role", f"message will not be included in LLM prompt. role '{message.role}' is not supported. use '### @prompt:'.", message.source_loc)
        else:
            log.warning("unrecognised-public-role", f"message will not be included in LLM prompt. public role '{message.role}' is not recognised.", message.source_loc)
            continue

    return result

class KoboldcppResponder(Responder):
    def construct_configuration(self, context: ResponderContext) -> BaseModel|tuple[BaseModel, list[tuple[str,VarRef]]]|None:
        return KoboldcppResponderConfiguration(), [("temperature", VarRef("temperature"))]

    def generate_responses(self, input_: list[Message], context: ResponderContext) -> list[Message]:
        config: KoboldcppResponderConfiguration = context.responder_config
        context.log.debug(f"koboldcpp.text: input: {config = }", context.state.input_file_path)
        config = resolve_var_refs(config, context.root_config, context.log)
        context.log.debug(f"koboldcpp.text: resolved: {config = }", context.state.input_file_path)

        prompt = convert_message_sequence_to_text_prompt(input_, context.log)
        if not prompt:
            context.log.error("koboldcpp.text: can't generate completion. prompt is empty.")
            return []

        if context.root_config.prapti.dry_run:
            context.log.info("koboldcpp-text-dry-run", "koboldcpp.text: dry run: bailing before hitting the Kobold API", context.state.input_file_path)
            current_time = str(datetime.datetime.now())
            return [Message(role="assistant", name=None, content=[f"dry run mode. {current_time}\nconfig = {json.dumps(config.model_dump())}"])]

        generate_args = config.model_dump(exclude_none=True, exclude_defaults=True)
        context.log.debug(f"koboldcpp.text: {generate_args = }")

        response = requests.post(f"{config.api_base}/generate", json={"prompt": prompt, **generate_args}, timeout=1000)
        response_json = response.json()
        response_text = response_json["results"][0]["text"]

        return [Message(role="completion", name=None, content=[response_text])]

class KoboldcppResponderPlugin(Plugin):
    def __init__(self):
        super().__init__(
            api_version = "0.1.0",
            name = "koboldcpp.text",
            version = "0.0.1",
            description = "Responder using the Koboldcpp text completions API",
            capabilities = PluginCapabilities.RESPONDER
        )

    def construct_responder(self, context: PluginContext) -> Responder|None:
        return KoboldcppResponder()

prapti_plugin = KoboldcppResponderPlugin()
