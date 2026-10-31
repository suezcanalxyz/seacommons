# SPDX-License-Identifier: AGPL-3.0-or-later
"""Static safety contract for the operator-run Oracle PostgreSQL audit.

Does not connect to Oracle, execute SQL, or certify production LIVE/PLAY.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/research/maritime-attack-postgres-readonly-audit-2026-10-31.sql"
MODELS = ROOT / "apps/api/core/db/models.py"


class PostgresAuditSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = AUDIT.read_text(encoding="utf-8")
        cls.models = MODELS.read_text(encoding="utf-8")

    def test_all_executable_statements_are_read_only(self):
        executable = "\n".join(
            line for line in self.sql.splitlines()
            if not line.lstrip().startswith("--")
        )
        statements = [part.strip() for part in executable.split(";") if part.strip()]
        self.assertGreaterEqual(len(statements), 10)
        self.assertEqual(statements[0].upper(), "BEGIN READ ONLY")
        self.assertEqual(statements[-1].upper(), "ROLLBACK")
        for statement in statements[1:-1]:
            self.assertRegex(statement, r"^(?:SELECT|SET LOCAL)\b")
        self.assertIn("SET LOCAL statement_timeout = '5000ms'", executable)
        self.assertIn("SET LOCAL lock_timeout = '1000ms'", executable)

    def test_rolling_window_is_not_pinned_to_october(self):
        self.assertIn("interval '72 hours'", self.sql)
        self.assertIn("interval '5 minutes'", self.sql)
        self.assertNotIn("timestamp_utc < '2026-11-02'", self.sql)
        self.assertIn("2026-10-01", self.sql)
        self.assertIn("2026-11-01", self.sql)

    def test_live_and_play_checks_do_not_promote_anything(self):
        for name in ("intel_events", "vessel_tracks", "alert_events",
                     "anomaly_events", "humanitarian_incidents", "forensic_events",
                     "maritime_episodes", "source_observations", "lineage_edges"):
            with self.subTest(table=name):
                self.assertRegex(self.sql, rf"\b(?:FROM|JOIN) {name}\b")
                self.assertIn(f'__tablename__ = "{name}"', self.models)
        for field in ("live_case_key", "live_entered_at",
                      "last_qualified_observation_at", "live_expires_at",
                      "operational_tier", "verification_status"):
            self.assertIn(field, self.sql)
            self.assertRegex(self.models, rf"\b{field}\s*= Column\(")
        # The normalized predicate is stricter than the old literal:
        # padded/mixed-case HUMANITARIAN must never enter attack audits.
        self.assertGreaterEqual(self.sql.count("lower(btrim(maritime_domain))"), 4)
        self.assertIn("lower(btrim(service)) <> 'humanitarian'", self.sql)
        self.assertNotIn("maritime_domain IS DISTINCT FROM 'humanitarian'", self.sql)
        self.assertIn("636019532", self.sql)

    def test_avoid_unbounded_forensic_or_humanitarian_payloads(self):
        self.assertNotRegex(self.sql, r"(?i)SELECT\s+\*")
        self.assertNotRegex(self.sql, r"(?i)\bsensor_data\b")
        self.assertNotRegex(self.sql, r"(?i)\bwaveform_miniseed_b64\b")
        self.assertIn("ARRAY[]::text[]", self.sql)
        self.assertIn("LIMIT 100", self.sql)


if __name__ == "__main__":
    unittest.main()
