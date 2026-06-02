from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from personal_task_station.shared.schemas import ClientSettings, ConnectionConfig
from personal_task_station.skills.base import build_skill_client, load_skill_settings, skill_config_store


class FinanceSkill:
    def __init__(self):
        self.client = build_skill_client()
        self._settings = load_skill_settings()

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

    def email_sync(self, since: str | None = None) -> list[dict]:
        since_date = date.fromisoformat(since) if since else None
        jobs = self.client.sync_email_accounts(since_date=since_date)
        return [j.model_dump(mode="json") for j in jobs]

    def list_email_accounts(self) -> list[dict]:
        return [a.model_dump(mode="json") for a in self.client.list_email_accounts()]

    def email_import(
        self,
        account_id: int | None = None,
        since: str | None = None,
        reimport: bool = False,
    ) -> dict:
        aid = account_id or self._settings.default_email_account_id
        if aid is None:
            raise ValueError(
                "No email account specified. Run 'configure --email-account-id N' first "
                "or pass --account-id explicitly."
            )
        since_date = date.fromisoformat(since) if since else None
        return self.client.trigger_email_import(
            aid, since_date=since_date, ignore_seen=reimport
        ).model_dump(mode="json")


def _configure(args: argparse.Namespace) -> dict:
    store = skill_config_store()
    settings = store.load() if store.path.exists() else ClientSettings()
    conn = settings.connection

    if args.base_url:
        conn = conn.model_copy(update={"base_url": args.base_url})
    if args.api_key:
        conn = conn.model_copy(update={"api_key": args.api_key})
    if args.allow_insecure_localhost is not None:
        conn = conn.model_copy(update={"allow_insecure_localhost": args.allow_insecure_localhost})

    updated = settings.model_copy(update={"connection": conn})
    if args.email_account_id is not None:
        updated = updated.model_copy(update={"default_email_account_id": args.email_account_id})

    store.save(updated)
    return {
        "config_path": str(store.path),
        "base_url": updated.connection.base_url,
        "api_key": updated.connection.api_key,
        "allow_insecure_localhost": updated.connection.allow_insecure_localhost,
        "default_email_account_id": updated.default_email_account_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Finance skill wrapper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cfg_parser = subparsers.add_parser("configure", help="Save connection settings to config file")
    cfg_parser.add_argument("--base-url", help="Server base URL, e.g. http://localhost:8080")
    cfg_parser.add_argument("--api-key", help="API key")
    cfg_parser.add_argument("--email-account-id", type=int, help="Default email account ID for imports")
    cfg_parser.add_argument("--allow-insecure-localhost", action=argparse.BooleanOptionalAction, default=None)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--year", type=int, required=True)
    summary_parser.add_argument("--month", type=int, required=True)

    tx_parser = subparsers.add_parser("transactions")
    tx_parser.add_argument("--month")
    tx_parser.add_argument("--source-name")

    subparsers.add_parser("duplicates")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--source-name", required=True)
    import_parser.add_argument("--file-path", required=True)

    reanalyze_parser = subparsers.add_parser("reanalyze")
    reanalyze_parser.add_argument("--import-job-id", type=int)

    undo_parser = subparsers.add_parser("undo-merge")
    undo_parser.add_argument("--merged-id", type=int, required=True)

    sync_parser = subparsers.add_parser("email-sync", help="Sync all active email accounts for new transactions")
    sync_parser.add_argument("--since", help="Only import emails since this date (YYYY-MM-DD)")

    subparsers.add_parser("email-accounts", help="List registered email accounts")

    email_import_parser = subparsers.add_parser("email-import", help="Trigger email import")
    email_import_parser.add_argument("--account-id", type=int, help="Override default email account ID")
    email_import_parser.add_argument("--since", help="Only import emails since this date (YYYY-MM-DD)")
    email_import_parser.add_argument("--reimport", action="store_true", help="Re-process already-read emails")

    args = parser.parse_args()

    if args.command == "configure":
        result = _configure(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

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
    elif args.command == "undo-merge":
        result = skill.undo_merge(args.merged_id)
    elif args.command == "email-sync":
        result = skill.email_sync(since=args.since)
    elif args.command == "email-accounts":
        result = skill.list_email_accounts()
    else:
        result = skill.email_import(
            account_id=args.account_id,
            since=args.since,
            reimport=args.reimport,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
