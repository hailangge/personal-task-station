from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from personal_task_station.shared.enums import BillDirection
from personal_task_station.shared.settings import AppSettings


@dataclass(slots=True)
class ClassificationResult:
    category: str
    confidence: float
    reason: str
    classifier_name: str


class BaseTransactionClassifier:
    def classify(self, transaction: dict) -> ClassificationResult:
        raise NotImplementedError


class RuleBasedClassifier(BaseTransactionClassifier):
    CATEGORY_RULES: dict[str, tuple[str, ...]] = {
        "groceries": ("market", "grocery", "supermarket", "fresh", "food hall"),
        "dining": ("coffee", "tea", "restaurant", "bbq", "hotpot", "kfc", "mcdonald", "cafe"),
        "transport": ("metro", "taxi", "rail", "fuel", "gas", "petrol", "ride", "didi"),
        "ecommerce": ("jd", "taobao", "tmall", "pdd", "amazon", "shop", "store"),
        "utilities": ("electric", "water", "internet", "mobile", "utility"),
        "salary": ("salary", "payroll", "bonus", "allowance"),
        "transfer": ("transfer", "bank transfer", "withdraw", "deposit"),
        "housing": ("rent", "mortgage", "property"),
        "healthcare": ("hospital", "clinic", "pharmacy"),
        "entertainment": ("cinema", "movie", "game", "music", "video"),
    }

    def classify(self, transaction: dict) -> ClassificationResult:
        merchant = f"{transaction.get('merchant_name', '')} {transaction.get('note', '')}".lower()
        source = str(transaction.get("source_name", "")).lower()
        if transaction.get("direction") == BillDirection.INCOME:
            category = "salary" if "salary" in merchant else "income"
            return ClassificationResult(
                category=category,
                confidence=0.65,
                reason="Income transaction classified with fallback income rules.",
                classifier_name="fallback_rules",
            )

        for category, keywords in self.CATEGORY_RULES.items():
            if any(keyword in merchant or keyword in source for keyword in keywords):
                return ClassificationResult(
                    category=category,
                    confidence=0.74,
                    reason=f"Matched fallback keyword set for {category}.",
                    classifier_name="fallback_rules",
                )

        amount = Decimal(str(transaction.get("amount", "0")))
        if abs(amount) >= Decimal("1000"):
            category = "large_expense"
            reason = "Large expense fallback rule matched."
            confidence = 0.58
        else:
            category = "other"
            reason = "No rule matched; defaulted to other."
            confidence = 0.4
        return ClassificationResult(
            category=category,
            confidence=confidence,
            reason=reason,
            classifier_name="fallback_rules",
        )


class LiteLLMClassifier(BaseTransactionClassifier):
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or AppSettings.load()

    def classify(self, transaction: dict) -> ClassificationResult:
        if not self.settings.litellm_model:
            raise RuntimeError("LiteLLM model is not configured.")

        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError("LiteLLM is not installed.") from exc

        prompt = {
            "task": "Classify one personal finance transaction into a concise category.",
            "transaction": {
                "merchant_name": transaction.get("merchant_name"),
                "note": transaction.get("note"),
                "direction": str(transaction.get("direction")),
                "amount": str(transaction.get("amount")),
                "source_name": transaction.get("source_name"),
            },
            "response_schema": {
                "category": "string",
                "confidence": "float between 0 and 1",
                "reason": "short string",
            },
        }
        response = completion(
            model=self.settings.litellm_model,
            api_key=self.settings.litellm_api_key,
            api_base=self.settings.litellm_base_url,
            messages=[
                {
                    "role": "system",
                    "content": "You classify finance transactions. Respond with JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
            ],
            timeout=self.settings.request_timeout_seconds,
        )
        content = response.choices[0].message.content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise RuntimeError("LiteLLM response did not contain JSON.")
        payload = json.loads(match.group(0))
        return ClassificationResult(
            category=str(payload.get("category", "other")),
            confidence=float(payload.get("confidence", 0.5)),
            reason=str(payload.get("reason", "LiteLLM classification.")),
            classifier_name="litellm",
        )


class CompositeClassifier(BaseTransactionClassifier):
    def __init__(self, *classifiers: BaseTransactionClassifier):
        self.classifiers = classifiers

    def classify(self, transaction: dict) -> ClassificationResult:
        last_error: Exception | None = None
        for classifier in self.classifiers:
            try:
                return classifier.classify(transaction)
            except (RuntimeError, ImportError, ConnectionError, TimeoutError) as exc:
                last_error = exc
                continue
        raise RuntimeError(f"No classifier available: {last_error}")


def build_classifier() -> BaseTransactionClassifier:
    return CompositeClassifier(LiteLLMClassifier(), RuleBasedClassifier())
