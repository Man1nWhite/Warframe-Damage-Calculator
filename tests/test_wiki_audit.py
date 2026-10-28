"""The wiki audit must work offline and report exactly what changed."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import wiki_audit

# Abridged from the live Damage/Blast_Damage page: the sentences the Blast
# claims are anchored to, with their wiki markup intact.
BLAST_WIKITEXT = """
'''Single Target Damage''': '''1.5s''' after inflicting blast status on an enemy, the blast stack will detonate, dealing '''30%''' weapon base damage to the target. However, reaching '''10''' blast stacks will cause all stacks to detonate early, dealing '''10''' hits of '''30%''' base damage to the target at once, for a total of '''300%''' base damage.

'''AoE Damage''': Upon reaching '''10''' blast stacks OR the target dying, all current stacks will be detonated early and cause a single '''5m''' AoE explosion, dealing '''300%''' weapon base damage '''per stack''' (max '''3000%''') to surrounding enemies. The initial target of the blast procs is '''not''' dealt this AoE damage.

Each blast stack has its own '''1.5s''' fuse time. {{D|Blast}} damage is reduced against {{D|Corpus Amalgam}}.
"""

COLD_WIKITEXT = """
Freeze lasts for '''6''' seconds and stacks up to '''10''' times. Each stack grants
'''+0.1x''' Critical Damage, rising by '''+0.05x''' per additional stack to a maximum
of '''+0.5x''' at nine stacks, and '''+1.0x''' while the target is Frozen. Bosses and
enemies with active Overguard cap the bonus at '''4''' stacks.
"""


def _renumbered_page(value: int) -> str:
    """The Blast excerpt with every 300% mentioning the AoE window changed."""
    return (BLAST_WIKITEXT
            .replace("total of '''300%''' base damage", f"total of '''{value}%''' base damage")
            .replace("dealing '''300%''' weapon base damage '''per stack'''",
                     f"dealing '''{value}%''' weapon base damage '''per stack'''"))


def claim(topic: str, **overrides) -> wiki_audit.Claim:
    base = wiki_audit.Claim(
        topic=topic,
        page="Damage/Blast_Damage",
        keywords=("aoe damage",),
        code=("modules.status_damage", "BLAST_RADIAL_COEF"),
        expected=3.0,
        percent=True,
    )
    return wiki_audit.Claim(**{**base.__dict__, **overrides})


class PlainTextTests(unittest.TestCase):
    def test_templates_and_links_reduce_to_their_displayed_text(self) -> None:
        text = wiki_audit.plain(
            "{{Infobox|Box title = Blast}} Deals '''30%''' to [[Blast|the target]] "
            "and [[Heat]] stacks.\n== Notes ==")
        self.assertIn("deals 30% to the target", text)
        self.assertIn("and heat stacks", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("'''", text)
        self.assertNotIn("\n", text)

    def test_numbers_near_a_keyword_are_collected_within_the_window(self) -> None:
        text = wiki_audit.plain("aoe explosion for 300% within 5m " + "x " * 400 + "999")
        numbers = wiki_audit.numbers_near(text, ("aoe",), window=40)
        self.assertIn(300.0, numbers)
        self.assertIn(5.0, numbers)
        self.assertNotIn(999.0, numbers)

    def test_a_missing_keyword_yields_no_numbers(self) -> None:
        self.assertEqual(wiki_audit.numbers_near("nothing here", ("blast",)), [])


class AuditTests(unittest.TestCase):
    def test_a_matching_page_is_reported_ok(self) -> None:
        results = wiki_audit.audit(
            [claim("radial")], {"Damage/Blast_Damage": BLAST_WIKITEXT})
        self.assertEqual([r.status for r in results], ["ok"])
        self.assertIn(300.0, results[0].numbers)

    def test_a_changed_wiki_number_is_flagged_for_review(self) -> None:
        # Both mentions of 300% have to move: the single-target sentence sits
        # inside the AoE keyword's window.
        results = wiki_audit.audit([claim("radial")],
                                   {"Damage/Blast_Damage": _renumbered_page(250)})
        self.assertEqual(results[0].status, "wiki-changed")
        self.assertNotIn(300.0, results[0].numbers)

    def test_code_drift_is_reported_against_the_expected_value(self) -> None:
        results = wiki_audit.audit(
            [claim("radial", expected=3.5)], {"Damage/Blast_Damage": BLAST_WIKITEXT})
        self.assertEqual(results[0].status, "code-changed")
        self.assertFalse(results[0].code_ok)

    def test_a_missing_keyword_makes_the_claim_unreadable(self) -> None:
        results = wiki_audit.audit(
            [claim("radial", keywords=("status damage",))],
            {"Damage/Blast_Damage": BLAST_WIKITEXT})
        self.assertEqual(results[0].status, "unreadable")
        self.assertIn("keyword not found", results[0].wiki_error or "")

    def test_an_unfetched_page_is_reported_instead_of_crashing(self) -> None:
        results = wiki_audit.audit([claim("radial")],
                                   {"Damage/Blast_Damage": "!could not fetch"})
        self.assertEqual(results[0].status, "unreadable")
        self.assertIn("could not fetch", results[0].wiki_error or "")

    def test_a_broken_code_probe_is_reported_instead_of_crashing(self) -> None:
        probe = claim("radial",
                      code=("modules.status_damage", "NOT_A_CONSTANT"))
        results = wiki_audit.audit([probe], {"Damage/Blast_Damage": BLAST_WIKITEXT})
        self.assertEqual(results[0].status, "unreadable")
        self.assertIn("AttributeError", results[0].code_error or "")

    def test_an_optional_claim_is_unverified_not_unreadable(self) -> None:
        # The Blast boss cap is stated in prose on a general page, so an
        # unreadable page must not turn the whole audit into a failure.
        results = wiki_audit.audit([claim("boss cap", optional=True)],
                                   {"Damage/Blast_Damage": "!offline"})
        self.assertEqual(results[0].status, "unverified")
        self.assertIn("offline", results[0].wiki_error or "")

    def test_an_optional_claim_still_reports_code_drift(self) -> None:
        results = wiki_audit.audit(
            [claim("boss cap", optional=True, expected=5)],
            {"Damage/Blast_Damage": "!offline"})
        self.assertEqual(results[0].status, "code-changed")

    def test_a_required_claim_stays_unreadable(self) -> None:
        results = wiki_audit.audit([claim("radial")],
                                   {"Damage/Blast_Damage": "!offline"})
        self.assertEqual(results[0].status, "unreadable")

    def test_cold_claims_read_the_freeze_page(self) -> None:
        claims = [c for c in wiki_audit.CLAIMS if c.page == "Damage/Cold_Damage"]
        self.assertTrue(claims)
        results = wiki_audit.audit(claims, {"Damage/Cold_Damage": COLD_WIKITEXT})
        statuses = {r.claim.topic: r.status for r in results}
        self.assertEqual(statuses["Cold Freeze first stack"], "ok")
        self.assertEqual(statuses["Cold Frozen bonus"], "ok")
        self.assertEqual(statuses["Cold Overguard cap"], "ok")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_and_diff(self) -> None:
        results = wiki_audit.audit([claim("radial")],
                                   {"Damage/Blast_Damage": BLAST_WIKITEXT})
        current = wiki_audit.snapshot(results)
        self.assertEqual(list(current), ["Damage/Blast_Damage::radial"])
        changes = wiki_audit.diff(current, current)
        self.assertEqual(changes, {})

    def test_diff_reports_added_and_removed_numbers(self) -> None:
        changes = wiki_audit.diff({"p::t": [1.0, 2.0], "gone::t": [7.0]},
                                  {"p::t": [2.0, 3.0]})
        self.assertEqual(changes["p::t"], {"added": [3.0], "removed": [1.0]})
        self.assertEqual(changes["gone::t"], {"added": [], "removed": [7.0]})


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pages = Path(self.temp.name)
        (self.pages / "Damage__Blast_Damage.wikitext").write_text(BLAST_WIKITEXT,
                                                                 encoding="utf-8")

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = wiki_audit.main(["--pages", str(self.pages), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_saved_pages_are_audited_without_network_access(self) -> None:
        with patch.object(wiki_audit, "fetch_page") as fetch:
            code, output, _ = self.run_main("--topic", "Blast radial", "--json")
        fetch.assert_not_called()
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual([c["status"] for c in payload["claims"]], ["ok"])

    def test_a_rotated_page_changes_the_exit_code(self) -> None:
        page = self.pages / "Damage__Blast_Damage.wikitext"
        page.write_text(_renumbered_page(250), encoding="utf-8")
        code, output, _ = self.run_main("--topic", "Blast radial")
        self.assertEqual(code, 1)
        self.assertIn("wiki-changed", output)

    def test_an_unreadable_page_reports_the_incomplete_audit(self) -> None:
        with patch.object(wiki_audit, "fetch_page", return_value="!offline"):
            code, output, err = self.run_main("--topic", "Cold Freeze first stack")
        self.assertEqual(code, 2)
        self.assertIn("offline", output.lower() + err.lower())

    def test_the_blast_topic_survives_an_unreadable_supporting_page(self) -> None:
        # Only the Blast page is saved; Damage/Calculation is not available.
        # The three readable claims must still decide the exit code.
        with patch.object(wiki_audit, "fetch_page", return_value="!offline"):
            code, output, _ = self.run_main("--topic", "Blast")
        self.assertEqual(code, 0)
        self.assertIn("[  unverified] Damage/Calculation :: Blast boss cap", output)
        self.assertIn("[          ok] Damage/Blast_Damage :: Blast radial", output)

    def test_the_json_report_marks_the_optional_claim(self) -> None:
        # A run that only reaches the optional claim still exits 0, and the
        # machine-readable payload says why the claim was not verified.
        with patch.object(wiki_audit, "fetch_page", return_value="!offline"):
            code, output, _ = self.run_main("--topic", "Blast boss cap", "--json")
        self.assertEqual(code, 0)
        entry, = json.loads(output)["claims"]
        self.assertEqual(entry["topic"], "Blast boss cap")
        self.assertEqual(entry["status"], "unverified")
        self.assertTrue(entry["optional"])

    def test_save_snapshot_writes_the_extracted_numbers(self) -> None:
        target = Path(self.temp.name) / "snapshot.json"
        code, _, _ = self.run_main("--topic", "Blast radial", "--save-snapshot", str(target))
        self.assertEqual(code, 0)
        numbers = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn(300.0, numbers["Damage/Blast_Damage::Blast radial"])

    def test_baseline_diff_is_printed(self) -> None:
        baseline = Path(self.temp.name) / "baseline.json"
        baseline.write_text(json.dumps({"Damage/Blast_Damage::Blast radial": [250.0]}),
                            encoding="utf-8")
        code, output, _ = self.run_main("--topic", "Blast radial", "--baseline", str(baseline))
        self.assertEqual(code, 0)
        self.assertIn("Changes since the saved snapshot", output)
        self.assertIn("+[1.5, 5, 10, 30, 300, 3000]", output)
        self.assertIn("-[250]", output)

    def test_an_unknown_topic_is_an_error(self) -> None:
        code, _, err = self.run_main("--topic", "no such claim")
        self.assertEqual(code, 2)
        self.assertIn("No claim matched", err)


class RegistryTests(unittest.TestCase):
    def test_every_claim_resolves_to_a_number(self) -> None:
        for entry in wiki_audit.CLAIMS:
            with self.subTest(topic=entry.topic):
                value = wiki_audit.resolve(entry)
                self.assertIsInstance(value, (int, float))

    def test_only_the_hand_checked_claim_is_optional(self) -> None:
        optional = [entry.topic for entry in wiki_audit.CLAIMS if entry.optional]
        self.assertEqual(optional, ["Blast boss cap"])
        cap = next(e for e in wiki_audit.CLAIMS if e.topic == "Blast boss cap")
        self.assertEqual(cap.page, "Damage/Calculation")
        self.assertEqual(wiki_audit.resolve(cap), 4)

    def test_topics_are_unique(self) -> None:
        topics = [entry.topic for entry in wiki_audit.CLAIMS]
        self.assertEqual(len(topics), len(set(topics)))

    def test_report_renders_every_result(self) -> None:
        results = wiki_audit.audit([claim("radial")],
                                   {"Damage/Blast_Damage": BLAST_WIKITEXT})
        text = wiki_audit.report(results, {"a::b": {"added": [1.0], "removed": []}})
        self.assertIn("Damage/Blast_Damage :: radial", text)
        self.assertIn("expected 3.0", text)
        self.assertIn("a::b", text)


if __name__ == "__main__":
    unittest.main()
