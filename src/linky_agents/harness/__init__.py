"""Harness de agentes do linky-dev (PRD §7.3 e §7.4).

Uso:
    harness = Harness.from_repo()            # lê config/models.yaml, config/prices.yaml e prompts/
    result = harness.run(spec, entrada)      # saída validada pelo contrato do agente
"""

from .config import ModelsConfig, PriceTable, load_models, load_prices
from .core import AgentSpec, Harness, RunResult
from .errors import BudgetExceeded, HarnessError, RunFailed
from .ledger import Alert
from .prompt import WebDocument
from .providers import FakeProvider, Message, ProviderError, Reply, Request, build_providers

__all__ = [
    "AgentSpec",
    "Alert",
    "BudgetExceeded",
    "FakeProvider",
    "Harness",
    "HarnessError",
    "Message",
    "ModelsConfig",
    "PriceTable",
    "ProviderError",
    "Reply",
    "Request",
    "RunFailed",
    "RunResult",
    "WebDocument",
    "build_providers",
    "load_models",
    "load_prices",
]
