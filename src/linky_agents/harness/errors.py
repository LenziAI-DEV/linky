"""Erros do harness. Toda falha de execução gera também o registro JSON da execução."""


class HarnessError(Exception):
    """Base dos erros do harness."""


class RunFailed(HarnessError):
    """Nenhum modelo da cadeia entregou uma saída válida."""

    def __init__(self, message: str, record_path=None):
        super().__init__(message)
        self.record_path = record_path


class BudgetExceeded(RunFailed):
    """A chamada estouraria um teto de custo (execução, dia ou mês). Nada foi gasto nela."""

    def __init__(self, message: str, scope: str, record_path=None):
        super().__init__(message, record_path)
        self.scope = scope
