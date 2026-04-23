from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_task_station.skills.base import build_skill_client


class FinanceSkill:
    def __init__(self):
        self.client = build_skill_client()

    def monthly_summary(self, year: int, month: int) -> dict:
        return self.client.monthly_summary(year, month).model_dump(mode="json")

    def transactions(self, month: str | None = None, source_name: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in self.client.list_transactions(month=month, source_name=source_name)]

    def duplicates(self) -> list[dict]:
        return list(self.client.list_duplicates())

    def import_file(self, source_name: str, file_path: str) -> dict:
        return self.client.import_billing_file(source_name, Path(file_path)).model_dump(mode="json")

    def reanalyze(self, import_job_id: int | None = None) -> dict:
        return self.client.reanalyze(import_job_id)

    def undo_merge(self, merged_transaction_id: int) -> dict:
        return self.client.undo_merge(merged_transaction_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Finance skill wrapper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--year", type=int, required=True)
    summary_parser.add_argument("--month", type=int, required=True)

    tx_parser = subparsers.add_parser("transactions")
    tx_parser.add_argument("--month")
    tx_parser.add_argument("--source-name")

    dup_parser = subparsers.add_parser("duplicates")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--source-name", required=True)
    import_parser.add_argument("--file-path", required=True)

    reanalyze_parser = subparsers.add_parser("reanalyze")
    reanalyze_parser.add_argument("--import-job-id", type=int)

    undo_parser = subparsers.add_parser("undo-merge")
    undo_parser.add_argument("--merged-id", type=int, required=True)

    args = parser.parse_args()
    skill = FinanceSkill()
    if args.command == "summary":
        result = skill.monthly_summary(args.year, args.month)
    elif args.command == "transactions":
        result = skill.transactions(month=args.month, source_name=args.source_name)
    elif args.command == "duplicates":
        result = skill.duplicates()
    elif args.command == "import":
        result = skill.import_file(args.source_name, args.file_path)
    elif args.command == "reanalyze":
        result = skill.reanalyze(args.import_job_id)
    else:
        result = skill.undo_merge(args.merged_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
