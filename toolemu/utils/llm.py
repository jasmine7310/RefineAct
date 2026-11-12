import logging

from langchain.base_language import BaseLanguageModel
from langchain.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain.chat_models import ChatOpenAI as LangchainChatOpenAI
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models.openai import convert_dict_to_message
from langchain.llms import VLLM, OpenAI
from langchain.pydantic_v1 import root_validator
from langchain.schema import ChatGeneration, ChatResult
from langchain.schema.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
)

from .my_typing import *

MODEL_BASE_NAMES = [
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "lmsys/vicuna-7b-v1.5-16k",
    "lmsys/vicuna-13b-v1.5-16k",
]
MODEL_SHORT_NAMES = [
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5",
    "gpt-3.5-16k",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "lmsys/vicuna-7b-v1.5-16k",
    "lmsys/vicuna-13b-v1.5-16k",
]
MODEL_NAMES_MAPPING = dict(zip(MODEL_SHORT_NAMES, MODEL_BASE_NAMES))
FIXED_VERSIONS = {
    "gpt-4o-mini": ["2024-07-18"],
    "gpt-4": ["0613", "0314"],
    "gpt-3.5-turbo": ["0613", "0301"],
    "gpt-3.5-turbo-16k": ["0613"],
}  # UPDATE this when fixed version changed
MODEL_NAMES = set(MODEL_BASE_NAMES)
for base_name in MODEL_BASE_NAMES:
    for version in FIXED_VERSIONS.get(base_name, []):
        MODEL_NAMES.add(f"{base_name}-{version}")
# can be model_names or model_short_names
AVAILABLE_MODEL_NAMES = list(MODEL_NAMES | set(MODEL_SHORT_NAMES))


def llm_register_args(parser, prefix=None, shortprefix=None, defaults={}):
    model_name = defaults.get("model_name", "gpt-4o-mini-2024-07-18")
    temperature = defaults.get("temperature", 0.0)
    max_tokens = defaults.get("max_tokens", None)
    default_retries = 8 if model_name.startswith("claude") else 12
    max_retries = defaults.get("max_retries", default_retries)
    request_timeout = defaults.get("request_timeout", 300)
    if prefix is None:
        prefix = ""
        shortprefix = ""
    else:
        prefix += "-"
        shortprefix = shortprefix or prefix[0]
    parser.add_argument(
        f"--{prefix}model-name",
        f"-{shortprefix}m",
        type=str,
        default=model_name,
        choices=AVAILABLE_MODEL_NAMES,
        help=f"Model name, one of: {AVAILABLE_MODEL_NAMES}",
    )
    parser.add_argument(
        f"--{prefix}temperature",
        f"-{shortprefix}t",
        type=float,
        default=temperature,
        help="Temperature for sampling",
    )
    parser.add_argument(
        f"--{prefix}max-tokens",
        f"-{shortprefix}mt",
        type=int,
        default=max_tokens,
        help="Max tokens for sampling",
    )
    parser.add_argument(
        f"--{prefix}max-retries",
        f"-{shortprefix}mr",
        type=int,
        default=max_retries,
        help="Max retries for each request",
    )
    parser.add_argument(
        f"--{prefix}request-timeout",
        f"-{shortprefix}rt",
        type=int,
        default=request_timeout,
        help="Timeout for each request",
    )


def get_model_name(name, fixed_version=True, version=None):
    model_name = None
    if name in MODEL_NAMES_MAPPING:
        model_name = MODEL_NAMES_MAPPING[name]
    elif name in MODEL_NAMES:
        model_name = name
    if model_name is None:
        raise ValueError(f"Invalid model name: {name}")

    if fixed_version:
        if version is None and model_name in FIXED_VERSIONS:
            version = FIXED_VERSIONS[model_name][0]
        if version is not None:
            model_name += f"-{version}"
    if model_name not in MODEL_NAMES:
        raise ValueError(f"Invalid model name: {model_name}")
    return model_name


def get_fixed_model_name(name):
    return get_model_name(name, fixed_version=True)


class ChatOpenAI(LangchainChatOpenAI):
    def _create_chat_result(self, response: Mapping[str, Any]) -> ChatResult:
        generations = []
        for res in response["choices"]:
            message = convert_dict_to_message(res["message"])
            gen = ChatGeneration(
                message=message,
                generation_info=dict(
                    finish_reason=res.get("finish_reason"),
                ),
            )
            generations.append(gen)
        llm_output = {"token_usage": response["usage"], "model_name": self.model_name}
        return ChatResult(generations=generations, llm_output=llm_output)


logger = logging.getLogger(__name__)


class ClaudeRefusalError(Exception):
    """Raised when the Claude API declines a request (stop_reason == "refusal")."""


class LLMOutputFormatError(Exception):
    """Raised when a model keeps returning output the pipeline cannot parse."""


# How many times the agent or simulator is re-prompted to continue an output
# that does not parse, before the case is failed instead of looping forever.
MAX_FORMAT_RETRIES = 5


def check_format_retries(retries: int, role: str, output: str) -> None:
    """Raise once `role` has already been re-prompted MAX_FORMAT_RETRIES times."""
    if retries >= MAX_FORMAT_RETRIES:
        raise LLMOutputFormatError(
            f"The {role} output could not be parsed after {MAX_FORMAT_RETRIES} "
            f"retries. Output ends with: {output[-400:]!r}"
        )


# Default output cap for Claude. Thinking tokens count against it, so it is
# deliberately higher than what the visible answer needs.
CLAUDE_DEFAULT_MAX_TOKENS = 16000


class ChatAnthropic(BaseChatModel):
    """Claude chat model backed by the Anthropic Messages API.

    Sampling parameters (temperature etc.) are not sent: current Claude models
    reject them, so runs are not seeded/deterministic the way the GPT runs are.
    """

    client: Any = None  #: :meta private:
    model: str = "claude-opus-5-5"
    max_tokens: int = CLAUDE_DEFAULT_MAX_TOKENS
    max_retries: int = 6
    """Retries for rate limits, timeouts and server errors (handled by the SDK)."""
    request_timeout: Optional[float] = None
    streaming: bool = False
    """Kept for interface compatibility with ChatOpenAI; streaming is not used."""

    @root_validator()
    def _build_client(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("client") is None:
            import anthropic

            client_kwargs: Dict[str, Any] = {"max_retries": values["max_retries"]}
            if values.get("request_timeout") is not None:
                client_kwargs["timeout"] = values["request_timeout"]
            # Credentials are resolved by the SDK (ANTHROPIC_API_KEY, typically
            # loaded from the project's .env file).
            values["client"] = anthropic.Anthropic(**client_kwargs)
        return values

    @property
    def _llm_type(self) -> str:
        return "anthropic-chat"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model": self.model, "max_tokens": self.max_tokens}

    @staticmethod
    def _convert_messages(
        messages: List[BaseMessage],
    ) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Split LangChain messages into a system prompt and Messages API turns."""
        system_parts = []
        api_messages = []
        for message in messages:
            if isinstance(message, SystemMessage):
                system_parts.append(message.content)
            elif isinstance(message, AIMessage):
                api_messages.append({"role": "assistant", "content": message.content})
            else:  # HumanMessage and anything else is sent as the user
                api_messages.append({"role": "user", "content": message.content})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, api_messages

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, api_messages = self._convert_messages(messages)
        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": api_messages,
        }
        if system:
            params["system"] = system
        if stop:
            params["stop_sequences"] = list(stop)
        response = self.client.messages.create(**params)
        return self._create_chat_result(response)

    def _create_chat_result(self, response: Any) -> ChatResult:
        finish_reason = response.stop_reason
        if finish_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise ClaudeRefusalError(
                f"{response.model} declined the request (category: {category})"
            )
        if finish_reason == "max_tokens":
            # for compatibility with OpenAI
            finish_reason = "length"

        # The response can also hold thinking blocks; only the text is the answer.
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        generations = [
            ChatGeneration(
                message=AIMessage(content=text),
                generation_info=dict(finish_reason=finish_reason),
            )
        ]
        llm_output = {
            "model_name": response.model,
            "token_usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        }
        return ChatResult(generations=generations, llm_output=llm_output)


def parse_llm_response(
    res: ChatResult, index: int = 0, one_generation_only: bool = True
) -> str:
    res = res.generations[0]
    if one_generation_only:
        assert len(res) == 1, res
    res = res[index]
    # if the decoding stops due to length, the response text is likely truncated so we discard it
    if res.generation_info.get("finish_reason", None) == "length":
        raise ValueError(f"Discard a response due to length: {res.text}")
    return res.text.strip()


def load_openai_llm(
    model_name: str = "text-davinci-003", **kwargs
) -> BaseLanguageModel:
    """Load the OpenAI language model and Claude and VLLM model"""
    # TODO: rename to load_llm
    if model_name.startswith("claude"):
        supported = ("max_tokens", "max_retries", "request_timeout")
        new_kwargs = {}
        for k, v in kwargs.items():
            if k in supported:
                if v is not None:
                    new_kwargs[k] = v
            else:
                # e.g. temperature: current Claude models reject sampling params
                print(f"Discard kwargs `{k}={v}` for {model_name}")
        return ChatAnthropic(model=model_name, **new_kwargs)
    elif model_name == "text-davinci-003":
        return OpenAI(model_name=model_name, **kwargs)
    elif "vicuna" in model_name:
        return VLLM(
            model=model_name,
            trust_remote_code=True,
            max_num_batched_tokens=16000,
            **kwargs,
        )
    elif model_name in MODEL_NAMES:
        return ChatOpenAI(model_name=model_name, **kwargs)
    else:
        raise ValueError(f"Unknown model name: {model_name}")


def load_openai_llm_with_args(args, prefix=None, fixed_version=True, **kwargs):
    if prefix is None:
        prefix = ""
    else:
        prefix += "_"
    model_name = getattr(args, f"{prefix}model_name")
    temperature = getattr(args, f"{prefix}temperature")
    max_tokens = getattr(args, f"{prefix}max_tokens")
    max_retries = getattr(args, f"{prefix}max_retries")
    request_timeout = getattr(args, f"{prefix}request_timeout")
    return load_openai_llm(
        model_name=get_model_name(model_name, fixed_version=fixed_version),
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
        request_timeout=request_timeout,
        **kwargs,
    )


def get_model_category(llm: BaseLanguageModel):
    if isinstance(llm, ChatOpenAI):
        return "openai"
    elif isinstance(llm, ChatAnthropic):
        return "claude"
    elif isinstance(llm, VLLM):
        return "vicuna"
    else:
        raise ValueError(f"Unknown model type: {type(llm)}")
