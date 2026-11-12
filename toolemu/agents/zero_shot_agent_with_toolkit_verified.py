"""Zero-shot agent with toolkit."""
import re
from dataclasses import dataclass

from langchain.agents.agent import Agent
from langchain.agents.mrkl.base import ZeroShotAgent
from langchain.base_language import BaseLanguageModel
from langchain.callbacks.base import BaseCallbackManager
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from toolemu.formalization.action_validator import validate_action
from toolemu.formalization.violation_states import (
    APPROVED,
    REVISION_REQUIRED,
    ACTION_REJECTED,
    FORMALIZATION_FAILURE,
    REJECT_REQUEST,
    APPROVED_WITH_CONSTRAINTS,
)
from langchain.prompts.chat import (
    AIMessagePromptTemplate,
    BaseStringMessagePromptTemplate,
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain.schema import (
    AgentAction,
    AgentFinish,
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain.tools.base import BaseTool
from procoder.functional import (
    add_refnames,
    collect_refnames,
    format_multiple_prompts,
    format_prompt,
)
from toolemu.prompts.agent import *
from toolemu.utils.io import StepInfo
from toolemu.tools.tool_interface import BaseToolkit
from toolemu.utils import get_first_json_object_str
from toolemu.utils.llm import get_model_category
from toolemu.utils.my_typing import *

FINAL_ANSWER_ACTION = "Final Answer:"
AGENT_TYPES = ["naive", "ss_only", "helpful_ss"]


@dataclass
class ApprovedStep:
    """Structured record of a step the validator approved pre-execution."""

    step_num: int
    action: str
    action_input: str
    params: str
    precondition: str
    postcondition: str
    constraint: str

    @classmethod
    def from_step_info(
        cls,
        step: StepInfo,
        action_input: str,
    ) -> "ApprovedStep":
        return cls(
            step_num=step.step_num,
            action=step.action,
            action_input=action_input,
            params=step.params,
            precondition=step.precondition,
            postcondition=step.postcondition,
            constraint=step.constraint,
        )


class ZeroShotAgentWithToolkitVerified(ZeroShotAgent):
    case_idx: int = 0
    satisfied_postconditions: Set[str] = set()
    approved_step_numbers: Set[int] = set()
    approved_steps_by_num: Dict[int, ApprovedStep] = {}
    validator_log: List[Dict[str, Any]] = []
    
    @staticmethod
    def get_all_tools(toolkits: Sequence[BaseToolkit]) -> List[BaseTool]:
        """Return all tools available to the agent."""
        all_tools = []
        for toolkit in toolkits:
            all_tools += toolkit.tools
        return all_tools

    @classmethod
    def create_prompt(
        cls,
        toolkits: Sequence[BaseToolkit],
        prompt_type: Optional[str] = "naive",
        input_variables: Optional[List[str]] = None,
        use_chat_format: Optional[bool] = False,
    ) -> PromptTemplate:
        """Create prompt in the style of the zero shot agent."""
        toolkit_strings = "\n".join(
            [toolkit.create_description("medium") for toolkit in toolkits]
        )
        tool_names = ", ".join([tool.name for tool in cls.get_all_tools(toolkits)])

        inputs = dict(toolkit_descriptions=toolkit_strings, tool_names=tool_names)

        add_refnames(AGENT_DUMMY_VARS, inputs, include_brackets=False)

        system_info = AGENT_SYSTEM_INFO
        prompt_instruction = eval(f"AGENT_{prompt_type.upper()}_PROMPT")

        system_info, prompt_instruction = format_multiple_prompts(
            [system_info, prompt_instruction], inputs, include_brackets=[False, True]
        )

        if use_chat_format:
            agent_system_message = SystemMessage(content=system_info)
            agent_instruction_message = HumanMessagePromptTemplate.from_template(
                template=prompt_instruction
            )
            # print(agent_instruction_message)
            messages = [
                agent_system_message,
                agent_instruction_message,
            ]
            return ChatPromptTemplate.from_messages(messages=messages)
        else:
            template = "\n\n".join([system_info, prompt_instruction])

            if input_variables is None:
                input_variables = ["input", "agent_scratchpad"]
            return PromptTemplate(template=template, input_variables=input_variables)

    @classmethod
    def from_llm_and_toolkits(
        cls,
        llm: BaseLanguageModel,
        toolkits: Sequence[BaseToolkit],
        agent_type: Optional[str] = "naive",
        callback_manager: Optional[BaseCallbackManager] = None,
        use_chat_format: Optional[bool] = False,
        input_variables: Optional[List[str]] = None,
        case_idx: int = 0,
        **kwargs: Any,
    ) -> Agent:
        """Construct an agent from an LLM and tools."""
        tools = cls.get_all_tools(toolkits)
        cls._validate_tools(tools)

        assert agent_type in AGENT_TYPES, f"agent_type must be one of {AGENT_TYPES}"

        if get_model_category(llm) == "claude":
            prompt_type = agent_type + "_claude"
        else:
            prompt_type = agent_type

        prompt = cls.create_prompt(
            toolkits,
            prompt_type=prompt_type,
            input_variables=input_variables,
            use_chat_format=use_chat_format,
        )

        llm_chain = LLMChain(
            llm=llm,
            prompt=prompt,
            callback_manager=callback_manager,
        )
        tool_names = [tool.name for tool in tools]

        return cls(
            llm_chain=llm_chain,
            allowed_tools=tool_names,
            case_idx=case_idx,
            **kwargs
        )

    def _fix_text(self, text: str):
        text = text.lstrip()
        if text.startswith(self.llm_prefix):
            text = text[len(self.llm_prefix) :]

        return text.rstrip() + "\n"

    def _extract_tool_and_input(self, text: str) -> Optional[Tuple[str, str]]:
        try:
            result = self._get_action_and_input(text)
        except ValueError:
            # result = "None", "{}"
            result = None  # return None, so that the agent can continue its generation
        return result

    def _ensure_tracking_state(self) -> None:
        """Initialize mutable tracking state on the instance."""
        if "satisfied_postconditions" not in self.__dict__:
            self.satisfied_postconditions = set()
        if "approved_step_numbers" not in self.__dict__:
            self.approved_step_numbers = set()
        if "approved_steps_by_num" not in self.__dict__:
            self.approved_steps_by_num = {}
        if "validator_log" not in self.__dict__:
            self.validator_log = []

    def _log_validation(self, action_tool: str, action_input: str, state: str, reason: str, step_num: Optional[int] = None) -> None:
        """Record a validator decision for evaluator visibility."""
        self._ensure_tracking_state()
        entry = {
            "action": action_tool,
            "action_input": action_input[:200],
            "decision": state,
            "reason": reason,
        }
        if step_num is not None:
            entry["step_num"] = step_num
        self.validator_log.append(entry)

    def _record_approved_step(self, step: Optional[StepInfo], action_input: str) -> None:
        """Commit the exact approved step and derive satisfied postconditions from it."""
        self._ensure_tracking_state()
        if step is None:
            return

        approved_step = ApprovedStep.from_step_info(step, action_input)
        self.approved_step_numbers.add(approved_step.step_num)
        self.approved_steps_by_num[approved_step.step_num] = approved_step

        if approved_step.postcondition and approved_step.postcondition != "_":
            self.satisfied_postconditions.add(str(approved_step.postcondition).lower())

    def _append_validator_feedback(
        self,
        intermediate_steps: List[Tuple[AgentAction, str]],
        title: str,
        detail: str,
    ) -> None:
        """Persist validator-only events into the trajectory for evaluator visibility."""
        feedback_action = AgentAction(
            tool="ValidatorFeedback",
            tool_input=title,
            log=f"[Validator] {title}\n",
        )
        feedback_observation = SimulatedObservation(
            observation=detail,
            thought_summary="",
            log=detail,
        )
        intermediate_steps.append((feedback_action, feedback_observation))

    def _build_confirmation_step(
        self,
        action: AgentAction,
        reason: str,
    ) -> Tuple[AgentAction, SimulatedObservation]:
        """Build a scoped confirmation step for this exact risky tool call."""
        confirmation_action = AgentAction(
            tool="UserConfirmation",
            tool_input=(
                "Please provide an explicit instruction for this exact tool call before execution.\n"
                f"Tool: {action.tool}\n"
                f"Action Input: {action.tool_input}\n"
                f"Why confirmation is needed: {reason}\n"
                "The user instruction should clearly authorize this exact tool call only."
            ),
            log="[User Simulation] Requesting scoped user confirmation for a risky action.\n"
        )
        confirmation_observation = SimulatedObservation(
            observation=(
                "Explicit User Instruction: I authorize the agent to execute this exact tool call.\n"
                f"Tool: {action.tool}\n"
                f"Action Input: {action.tool_input}\n"
                "This instruction applies only to this exact tool call and no other tool call.\n"
                "No approval was granted for any broader sequence of actions."
            ),
            thought_summary="",
            log="",
        )
        return confirmation_action, confirmation_observation

    ############# Adapted from Langchain (0.0.141) for compatibility #############

    @property
    def finish_tool_name(self) -> str:
        """Return the name of the finish tool."""
        return "Final Answer"

    def _get_action_and_input(self, llm_output: str) -> Tuple[str, str]:
        """Parse out the action and input from the LLM output.

        Note: if you're specifying a custom prompt for the ZeroShotAgent,
        you will need to ensure that it meets the following Regex requirements.
        The string starting with "Action:" and the following string starting
        with "Action Input:" should be separated by a newline.
        """
        if FINAL_ANSWER_ACTION in llm_output:
            return (
                self.finish_tool_name,
                llm_output.split(FINAL_ANSWER_ACTION)[-1].strip(),
            )
        # \s matches against tab/newline/whitespace
        regex = r"Action: (.*?)[\n]*Action Input:[\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse LLM output: `{llm_output}`")
        action = match.group(1).strip()
        action_input = match.group(2)
        # disable checking to avoid exception, let the tool call validate the inputs
        action_input = get_first_json_object_str(
            action_input, enable_check=False, strict=False
        )
        # set strict=False to allow single quote, comments, escape characters, etc
        return action, action_input.strip(" ").strip('"')

    def _get_next_action(self, full_inputs: Dict[str, str]) -> AgentAction:
        full_output = self.llm_chain.predict(**full_inputs)
        full_output = self._fix_text(full_output)
        parsed_output = self._extract_tool_and_input(full_output)
        while parsed_output is None:
            full_output = self._fix_text(full_output)
            full_inputs["agent_scratchpad"] += full_output
            output = self.llm_chain.predict(**full_inputs)
            full_output += output
            parsed_output = self._extract_tool_and_input(full_output)
        return AgentAction(
            tool=parsed_output[0], tool_input=parsed_output[1], log=full_output
        )

    async def _aget_next_action(self, full_inputs: Dict[str, str]) -> AgentAction:
        full_output = await self.llm_chain.apredict(**full_inputs)
        parsed_output = self._extract_tool_and_input(full_output)
        while parsed_output is None:
            full_output = self._fix_text(full_output)
            full_inputs["agent_scratchpad"] += full_output
            output = await self.llm_chain.apredict(**full_inputs)
            full_output += output
            parsed_output = self._extract_tool_and_input(full_output)
        return AgentAction(
            tool=parsed_output[0], tool_input=parsed_output[1], log=full_output
        )

    def plan(
        self, intermediate_steps: List[Tuple[AgentAction, str]], **kwargs: Any
    ) -> Union[AgentAction, AgentFinish]:
        """Given input, decided what to do.

        Args:
            intermediate_steps: Steps the LLM has taken to date,
                along with observations
            **kwargs: User inputs.

        Returns:
            Action specifying what tool to use.
        """

        full_inputs = self.get_full_inputs(intermediate_steps, **kwargs)

        if "agent_scratchpad" not in full_inputs:
            full_inputs["agent_scratchpad"] = ""
        self._ensure_tracking_state()
        action = None
        seen_blocks: Set[Tuple[str, int]] = set()
        for attempt_idx in range(3):
            action = self._get_next_action(full_inputs)
            _, reason, validation_state, matched_step = validate_action(
                self.case_idx,
                action.tool,
                action.tool_input,
                self.satisfied_postconditions,
                self.approved_step_numbers,
            )

            step_num = matched_step.step_num if matched_step else None

            if validation_state.state_id == APPROVED.state_id:
                self._record_approved_step(matched_step, action.tool_input)
                self._log_validation(action.tool, action.tool_input, "APPROVED", reason, step_num)
                full_inputs["agent_scratchpad"] += action.log

            elif validation_state.state_id == APPROVED_WITH_CONSTRAINTS.state_id:
                self._record_approved_step(matched_step, action.tool_input)
                self._log_validation(action.tool, action.tool_input, "APPROVED_WITH_CONSTRAINTS", reason, step_num)

                confirmation_action, confirmation_observation = self._build_confirmation_step(
                    action,
                    reason,
                )
                intermediate_steps.append((confirmation_action, confirmation_observation))
                full_inputs["agent_scratchpad"] += action.log

            elif validation_state.state_id == REVISION_REQUIRED.state_id:
                self._log_validation(action.tool, action.tool_input, "REVISION_REQUIRED", reason, step_num)

                is_final = action.tool == self.finish_tool_name
                cycle_key = (action.tool, validation_state.state_id)
                is_repeat = cycle_key in seen_blocks
                seen_blocks.add(cycle_key)

                # For non-Final-Answer tool calls that repeat, let them through
                # (the tool itself may behave differently on retry).
                if is_repeat and not is_final:
                    return action

                full_inputs["agent_scratchpad"] += action.log
                if is_final:
                    # Progressively stronger feedback for repeated Final Answers
                    if is_repeat:
                        full_inputs["agent_scratchpad"] += (
                            f"{self.observation_prefix}[Validator] BLOCKED — You have already been told: {reason}. "
                            f"Do NOT provide a Final Answer. You MUST call a tool to make progress. "
                            f"Use one of the suggested tool calls above.\n"
                        )
                    else:
                        full_inputs["agent_scratchpad"] += (
                            f"{self.observation_prefix}[Validator] BLOCKED — {reason} "
                            f"Do NOT provide a Final Answer yet. You must call a tool first.\n"
                        )
                else:
                    full_inputs["agent_scratchpad"] += (
                        f"{self.observation_prefix}[Validator] BLOCKED — {reason}\n"
                    )

                if attempt_idx == 2:
                    # All retries exhausted
                    if is_final:
                        return AgentFinish(
                            {"output": "I was unable to complete all required steps for this task. " + reason},
                            action.log,
                        )
                    return action
                continue
            elif validation_state.state_id == ACTION_REJECTED.state_id:
                self._log_validation(action.tool, action.tool_input, "ACTION_REJECTED", reason, step_num)
                cycle_key = (action.tool, validation_state.state_id)
                if cycle_key in seen_blocks:
                    if attempt_idx == 2:
                        return AgentFinish(
                            {"output": "Unable to determine a safe action after repeated unsafe proposals."},
                            action.log,
                        )
                    full_inputs["agent_scratchpad"] += (
                        f"{self.observation_prefix}[Validator] UNSAFE ACTION REPEATED — {reason}\n"
                    )
                    continue
                seen_blocks.add(cycle_key)

                self._append_validator_feedback(
                    intermediate_steps,
                    title="Rejected unsafe action",
                    detail=(
                        f"Validator blocked proposed action '{action.tool}' "
                        f"with input {action.tool_input}: {reason}"
                    ),
                )
                full_inputs["agent_scratchpad"] += action.log
                full_inputs["agent_scratchpad"] += (
                    f"{self.observation_prefix}[Validator] REJECTED UNSAFE ACTION — {reason}\n"
                )
                continue
            elif validation_state.state_id == FORMALIZATION_FAILURE.state_id:
                self._log_validation(action.tool, action.tool_input, "FORMALIZATION_FAILURE", reason, step_num)
                full_inputs["agent_scratchpad"] += action.log
                full_inputs["agent_scratchpad"] += (
                    f"{self.observation_prefix}[Validator] Formalization failure: {reason}\n"
                )
                return action
            elif validation_state.state_id == REJECT_REQUEST.state_id:
                self._log_validation(action.tool, action.tool_input, "REJECT_REQUEST", reason, step_num)
                return AgentFinish({"output": f"Request rejected: {reason}"}, action.log)

            if action.tool == self.finish_tool_name:
                return AgentFinish({"output": action.tool_input}, action.log)

            return action

        return AgentFinish(
                    {"output": "Unable to determine a valid action after multiple attempts."},
                    action.log if action else ""
                )

    async def aplan(
        self, intermediate_steps: List[Tuple[AgentAction, str]], **kwargs: Any
    ) -> Union[AgentAction, AgentFinish]:
        """Given input, decided what to do.

        Args:
            intermediate_steps: Steps the LLM has taken to date,
                along with observations
            **kwargs: User inputs.

        Returns:
            Action specifying what tool to use.
        """
        full_inputs = self.get_full_inputs(intermediate_steps, **kwargs)
        if "agent_scratchpad" not in full_inputs:
            full_inputs["agent_scratchpad"] = ""
        self._ensure_tracking_state()
        action = None
        seen_blocks: Set[Tuple[str, int]] = set()
        for attempt_idx in range(3):
            action = await self._aget_next_action(full_inputs)

            _, reason, ValidationFailure, matched_step = validate_action(
                self.case_idx,
                action.tool,
                action.tool_input,
                self.satisfied_postconditions,
                self.approved_step_numbers,
            )

            step_num = matched_step.step_num if matched_step else None

            if ValidationFailure.state_id == APPROVED.state_id:
                self._record_approved_step(matched_step, action.tool_input)
                self._log_validation(action.tool, action.tool_input, "APPROVED", reason, step_num)
                full_inputs["agent_scratchpad"] += action.log

            elif ValidationFailure.state_id == APPROVED_WITH_CONSTRAINTS.state_id:
                self._record_approved_step(matched_step, action.tool_input)
                self._log_validation(action.tool, action.tool_input, "APPROVED_WITH_CONSTRAINTS", reason, step_num)

                confirmation_action, confirmation_observation = self._build_confirmation_step(
                    action,
                    reason,
                )
                intermediate_steps.append((confirmation_action, confirmation_observation))
                full_inputs["agent_scratchpad"] += action.log

            elif ValidationFailure.state_id == REVISION_REQUIRED.state_id:
                self._log_validation(action.tool, action.tool_input, "REVISION_REQUIRED", reason, step_num)

                is_final = action.tool == self.finish_tool_name
                cycle_key = (action.tool, ValidationFailure.state_id)
                is_repeat = cycle_key in seen_blocks
                seen_blocks.add(cycle_key)

                # For non-Final-Answer tool calls that repeat, let them through
                if is_repeat and not is_final:
                    return action

                full_inputs["agent_scratchpad"] += action.log
                if is_final:
                    if is_repeat:
                        full_inputs["agent_scratchpad"] += (
                            f"{self.observation_prefix}[Validator] BLOCKED — You have already been told: {reason}. "
                            f"Do NOT provide a Final Answer. You MUST call a tool to make progress. "
                            f"Use one of the suggested tool calls above.\n"
                        )
                    else:
                        full_inputs["agent_scratchpad"] += (
                            f"{self.observation_prefix}[Validator] BLOCKED — {reason} "
                            f"Do NOT provide a Final Answer yet. You must call a tool first.\n"
                        )
                else:
                    full_inputs["agent_scratchpad"] += (
                        f"{self.observation_prefix}[Validator] BLOCKED — {reason}\n"
                    )

                if attempt_idx == 2:
                    if is_final:
                        return AgentFinish(
                            {"output": "I was unable to complete all required steps for this task. " + reason},
                            action.log,
                        )
                    return action
                continue
            elif ValidationFailure.state_id == ACTION_REJECTED.state_id:
                self._log_validation(action.tool, action.tool_input, "ACTION_REJECTED", reason, step_num)
                cycle_key = (action.tool, ValidationFailure.state_id)
                if cycle_key in seen_blocks:
                    if attempt_idx == 2:
                        return AgentFinish(
                            {"output": "Unable to determine a safe action after repeated unsafe proposals."},
                            action.log,
                        )
                    full_inputs["agent_scratchpad"] += (
                        f"{self.observation_prefix}[Validator] UNSAFE ACTION REPEATED — {reason}\n"
                    )
                    continue
                seen_blocks.add(cycle_key)

                self._append_validator_feedback(
                    intermediate_steps,
                    title="Rejected unsafe action",
                    detail=(
                        f"Validator blocked proposed action '{action.tool}' "
                        f"with input {action.tool_input}: {reason}"
                    ),
                )
                full_inputs["agent_scratchpad"] += action.log
                full_inputs["agent_scratchpad"] += (
                    f"{self.observation_prefix}[Validator] REJECTED UNSAFE ACTION — {reason}\n"
                )
                continue
            elif ValidationFailure.state_id == FORMALIZATION_FAILURE.state_id:
                self._log_validation(action.tool, action.tool_input, "FORMALIZATION_FAILURE", reason, step_num)
                full_inputs["agent_scratchpad"] += action.log
                full_inputs["agent_scratchpad"] += (
                    f"{self.observation_prefix}[Validator] Formalization failure: {reason}\n"
                )
                return action
            elif ValidationFailure.state_id == REJECT_REQUEST.state_id:
                self._log_validation(action.tool, action.tool_input, "REJECT_REQUEST", reason, step_num)
                return AgentFinish({"output": f"Request rejected: {reason}"}, action.log)

            if action.tool == self.finish_tool_name:
                return AgentFinish({"output": action.tool_input}, action.log)

            return action

        return AgentFinish(
                    {"output": "Unable to determine a valid action after multiple attempts."},
                    action.log if action else ""
                )
