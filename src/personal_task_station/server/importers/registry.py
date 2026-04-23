from __future__ import annotations

from personal_task_station.server.importers.base import TransactionImporter


class ImporterRegistry:
    _importers: dict[str, TransactionImporter] = {}

    @classmethod
    def register(cls, name: str, importer: TransactionImporter) -> None:
        cls._importers[name] = importer

    @classmethod
    def get(cls, name: str) -> TransactionImporter | None:
        return cls._importers.get(name)

    @classmethod
    def list_names(cls) -> list[str]:
        return list(cls._importers.keys())
