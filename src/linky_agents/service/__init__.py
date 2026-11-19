"""Serviço HTTP interno do harness: expõe a fila editorial e o ledger para o n8n (ADR 0003)."""

from .app import App

__all__ = ["App"]
