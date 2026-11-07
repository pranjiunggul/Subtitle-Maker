"""
Subtitle Maker — Vocabulary & Pronunciation Rules Manager
Allows automatic replacement of misrecognized terms with user corrections.
"""

import json
import os
import re
from typing import Dict, List, Any

VOCAB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "vocabulary.json")


class VocabularyManager:
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or VOCAB_FILE
        self.rules: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if os.path.isfile(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
            except Exception:
                self.rules = []
        else:
            # Default Indonesian & Tech rules
            self.rules = [
                {"raw": "open word", "corrected": "OpenWrt", "domain": "networking"},
                {"raw": "open wrt", "corrected": "OpenWrt", "domain": "networking"},
                {"raw": "micro tik", "corrected": "MikroTik", "domain": "networking"},
                {"raw": "mikrotik", "corrected": "MikroTik", "domain": "networking"},
                {"raw": "wire guard", "corrected": "WireGuard", "domain": "networking"},
                {"raw": "sql light", "corrected": "SQLite", "domain": "database"},
                {"raw": "sqllite", "corrected": "SQLite", "domain": "database"},
                {"raw": "post gres", "corrected": "PostgreSQL", "domain": "database"},
                {"raw": "fast api", "corrected": "FastAPI", "domain": "programming"},
                {"raw": "f f mpeg", "corrected": "FFmpeg", "domain": "multimedia"},
                {"raw": "ff mpeg", "corrected": "FFmpeg", "domain": "multimedia"},
            ]
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add_rule(self, raw: str, corrected: str, domain: str = "general") -> bool:
        raw_clean = raw.strip()
        corrected_clean = corrected.strip()
        if not raw_clean or not corrected_clean:
            return False

        # Check existing
        for r in self.rules:
            if r["raw"].lower() == raw_clean.lower():
                r["corrected"] = corrected_clean
                r["domain"] = domain
                self.save()
                return True

        self.rules.append({
            "raw": raw_clean,
            "corrected": corrected_clean,
            "domain": domain
        })
        self.save()
        return True

    def delete_rule(self, index: int) -> bool:
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
            self.save()
            return True
        return False

    def list_rules(self) -> List[Dict[str, Any]]:
        return self.rules

    def get_terms_for_prompt(self) -> List[str]:
        """Returns unique corrected terms to bias Whisper initial prompt."""
        terms = set()
        for r in self.rules:
            terms.add(r["corrected"])
        return sorted(list(terms))

    def apply_corrections(self, text: str) -> str:
        """Apply regex word-boundary replacements."""
        if not text:
            return text
        result = text
        for r in self.rules:
            raw = r["raw"]
            corrected = r["corrected"]
            # Case-insensitive word boundary replacement
            pattern = re.compile(rf"\b{re.escape(raw)}\b", re.IGNORECASE)
            result = pattern.sub(corrected, result)
        return result
