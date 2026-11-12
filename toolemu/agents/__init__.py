from .agent_executor import AgentExecutorWithToolkit
from .virtual_agent_executor import (
    AdversarialVirtualAgentExecutorWithToolkit,
    StandardVirtualAgentExecutorWithToolkit,
)
from .zero_shot_agent_with_toolkit import AGENT_TYPES, ZeroShotAgentWithToolkit
from .zero_shot_agent_with_toolkit_verified import ZeroShotAgentWithToolkitVerified

SIMULATORS = {
    "normal": AgentExecutorWithToolkit,
    "std_thought": StandardVirtualAgentExecutorWithToolkit,
    "adv_thought": AdversarialVirtualAgentExecutorWithToolkit,
}
