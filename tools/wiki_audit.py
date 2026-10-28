"""Re-diff the wiki numbers this project depends on.

The formula audit in ``docs/wiki_formula_verification.md`` was checked against
wiki.warframe.com by hand. A game update can change any of those pages, so this
tool re-reads the source pages, extracts the numbers that appear next to each
audited keyword, and compares them with the value the code currently uses.

It is deliberately a *reporting* tool: the wiki is the authority, the code is
not. A number that no longer matches the code is a finding to investigate, not
something this tool silently "fixes".

Typical use
-----------
Save the raw pages once, so later runs need no network::

    python tools/wiki_audit.py --pages wiki_pages --save-snapshot docs/wiki_numbers.json

After a game update, re-read the pages and diff against the snapshot::

    python tools/wiki_audit.py --pages wiki_pages --baseline docs/wiki_numbers.json

``--pages`` reuses a saved page when it exists and fetches only the missing
ones. Without ``--pages`` every page is fetched from the wiki (``?action=raw``
returns wikitext, which is far easier to search than rendered HTML).

Exit codes
----------
0  every audited number still matches the code
1  at least one number next to a keyword no longer matches the code
2  a page or keyword could not be read, so the audit is incomplete

A claim marked ``optional`` is one whose wiki evidence cannot be extracted
mechanically (the number is stated on a general page, away from the keyword).
When such a page or keyword cannot be read the claim is reported as
``unverified`` instead of ``unreadable`` and it does not change the exit code:
the code value is still checked, so drift is still exit 1.

The raw page text is not committed: it is large, it is not ours to
redistribute, and the snapshot of extracted numbers is what a diff needs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WIKI_RAW = "https://wiki.warframe.com/w/{page}?action=raw"
USER_AGENT = "WarframeDamageCalculator-wiki-audit/1.0 (+local audit tool)"

# How far around a keyword the numbers are collected. Wide enough to span a
# sentence or a formula block, narrow enough to skip the rest of the page.
WINDOW = 400

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_LINK = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]|\[\[([^\]]*)\]\]")
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Claim:
    """One audited number: a wiki keyword and the code value it justifies."""

    topic: str
    page: str
    keywords: tuple[str, ...]
    code: tuple[str, str]
    expected: float
    # Mapping key or call arguments when the code value lives behind one.
    key: Any = None
    args: tuple[Any, ...] = ()
    # The wiki usually writes fractions as percentages (0.3 -> "30%").
    percent: bool = False
    # Supporting evidence that cannot always be extracted by keyword: an
    # unreadable page is reported as "unverified" rather than failing the run.
    optional: bool = False
    note: str = ""

    def describe_code(self) -> str:
        target = f"{self.code[0]}.{self.code[1]}"
        if self.key is not None:
            target += f"[{self.key!r}]"
        if self.args:
            target += f"({', '.join(repr(arg) for arg in self.args)})"
        return target


CLAIMS: tuple[Claim, ...] = (
    Claim("Blast single-target", "Damage/Blast_Damage", ("single target damage",),
          ("modules.status_damage", "BLAST_SINGLE_COEF"), 0.30, percent=True,
          note="30% of modded base per stack after a 1.5 s fuse"),
    Claim("Blast radial", "Damage/Blast_Damage", ("aoe damage",),
          ("modules.status_damage", "BLAST_RADIAL_COEF"), 3.0, percent=True,
          note="300% per stack in a 5 m radius, no falloff"),
    Claim("Blast stack cap", "Damage/Blast_Damage", ("blast stacks",),
          ("modules.status_damage", "BLAST_MAX_STACKS"), 10,
          note="ten stacks detonate early"),
    # The four-stack cap is on the general Damage/Calculation page, not the
    # Blast page, and the page states it in prose rather than next to both
    # keywords, so it is checked by hand. The claim is ``optional``: an
    # unreadable page reports "unverified" and leaves the exit code alone,
    # while a drift in BLAST_MAX_STACKS_BOSS is still reported.
    Claim("Blast boss cap", "Damage/Calculation", ("blast", "eximus"),
          ("modules.status_damage", "BLAST_MAX_STACKS_BOSS"), 4,
          optional=True,
          note="bosses and some Eximus detonate at four stacks (hand-checked)"),
    Claim("Cold Freeze first stack", "Damage/Cold_Damage", ("critical damage",),
          ("modules.crit", "COLD_CRIT_DAMAGE_BY_STACK"), 0.10, key=1,
          note="+0.10x Critical Damage on the first Freeze stack"),
    Claim("Cold Frozen bonus", "Damage/Cold_Damage", ("critical damage",),
          ("modules.crit", "COLD_CRIT_DAMAGE_BY_STACK"), 1.00, key=10,
          note="+1.00x while Frozen at ten stacks"),
    Claim("Cold stack cap", "Damage/Cold_Damage", ("cold", "stacks"),
          ("modules.crit", "COLD_STACK_CAP"), 10),
    Claim("Cold Overguard cap", "Damage/Cold_Damage", ("overguard",),
          ("modules.crit", "COLD_STACK_CAP_OVERGUARD"), 4),
    Claim("Corrosive at ten stacks", "Damage/Corrosive_Damage", ("corrosive",),
          ("modules.akarius_sim", "corrosive_armor_factor"), 0.20, args=(10,),
          note="20% + 6% per stack, 80% strip at ten stacks"),
    Claim("Slash DoT coefficient", "Damage/Slash_Damage", ("slash",),
          ("modules.status_damage", "SLASH_COEFFICIENT"), 0.35,
          note="0.35 x modded base per tick"),
    Claim("Elemental DoT coefficient", "Damage/Heat_Damage", ("heat",),
          ("modules.status_damage", "ELEMENTAL_DOT_COEFFICIENT"), 0.5,
          note="heat/toxin/electricity/gas ticks use 0.5"),
    Claim("Status proc duration", "Damage/Heat_Damage", ("seconds",),
          ("modules.status_damage", "PROC_DURATION"), 6.0,
          note="heat/toxin/electricity/gas last six seconds"),
    Claim("Heat strip at two seconds", "Damage/Heat_Damage", ("armor",),
          ("modules.kuva_nukor_sim", "_heat_strip_fraction"), 0.5,
          args=(2.0, 0.5),
          note="15/30/40/50% strip every 0.5 s reaches 50% at 2 s"),
    Claim("Gas stack cap", "Damage/Gas_Damage", ("gas",),
          ("modules.status_damage", "GAS_MAX_STACKS"), 10),
    Claim("Magnetic at ten stacks", "Damage/Magnetic_Damage", ("magnetic",),
          ("modules.damage_routing", "status_vulnerability"), 4.25, args=(10,),
          note="2 + 0.25 x (stacks - 1), capped at ten"),
    Claim("Overguard Void bonus", "Overguard", ("void",),
          ("modules.damage_routing", "VOID_OVERGUARD_MULTIPLIER"), 1.5,
          note="Overguard is neutral except Void's +50%"),
    Claim("Armor cap", "Armor", ("armor",),
          ("modules.enemy_scaling", "ARMOR_CAP"), 2700),
    Claim("Overguard base", "Enemy_Level_Scaling", ("overguard",),
          ("modules.enemy_scaling", "OVERGUARD_BASE"), 12),
    Claim("Critical-damage code width", "Critical_Hit", ("4095",),
          ("modules.crit", "CRIT_CODE_MAX"), 4095,
          note="12-bit encoding: floor(x * 4095 / 32 + 0.5)"),
)


@dataclass
class ClaimResult:
    claim: Claim
    numbers: list[float] = field(default_factory=list)
    code_value: Any = None
    code_error: str | None = None
    wiki_error: str | None = None

    @property
    def code_ok(self) -> bool:
        return self.code_error is None and _values_match(self.code_value, self.claim.expected)

    @property
    def wiki_ok(self) -> bool:
        if self.wiki_error is not None:
            return False
        return any(_numbers_match(number, self.claim)
                   for number in self.numbers)

    @property
    def status(self) -> str:
        if self.code_error is not None:
            return "unreadable"
        # Checked before the wiki so that drift in the code is never hidden
        # behind an unreadable (or optional) page.
        if not self.code_ok:
            return "code-changed"
        if self.wiki_error is not None:
            return "unverified" if self.claim.optional else "unreadable"
        if not self.wiki_ok:
            return "wiki-changed"
        return "ok"


def _values_match(actual: Any, expected: Any) -> bool:
    try:
        if isinstance(expected, float) or isinstance(actual, float):
            return abs(float(actual) - float(expected)) < 1e-9
        return int(actual) == int(expected)
    except (TypeError, ValueError):
        return actual == expected


def _numbers_match(number: float, claim: Claim) -> bool:
    expected = claim.expected
    if _values_match(number, expected):
        return True
    return claim.percent and _values_match(number, expected * 100.0)


def plain(text: str) -> str:
    """Normalise wikitext enough to search it by phrase.

    Templates and links are reduced to their displayed text (``{{D|Blast}}``
    and ``[[Blast|blast]]`` both become ``blast``), quotes and tags are
    dropped, and whitespace is collapsed, so a keyword survives a re-format of
    the page.
    """
    text = text.replace("\\", "")
    for _ in range(5):
        collapsed = _TEMPLATE.sub(lambda match: _last_field(match.group(0)[2:-2]), text)
        collapsed = _LINK.sub(lambda match: match.group(1) or match.group(2) or "", collapsed)
        if collapsed == text:
            break
        text = collapsed
    text = _TAG.sub(" ", text)
    text = text.replace("'''", " ").replace("''", " ")
    text = text.replace("[[", " ").replace("]]", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _last_field(template: str) -> str:
    """``D|Blast`` -> ``Blast``; ``M|Firestorm|x`` keeps the first argument."""
    parts = [part for part in template.split("|") if part.strip()]
    if not parts:
        return ""
    return parts[1] if len(parts) > 1 else parts[0]


def _page_filename(page: str) -> str:
    return page.replace("/", "__") + ".wikitext"


def read_pages(pages_dir: Path | None,
               pages: Sequence[str], *, timeout: float = 30.0) -> dict[str, str]:
    """Return page text, from ``pages_dir`` when saved, else from the wiki."""
    pages_dir = pages_dir or ROOT / "wiki_pages"
    texts: dict[str, str] = {}
    for page in pages:
        saved = pages_dir / _page_filename(page)
        if saved.is_file():
            texts[page] = saved.read_text(encoding="utf-8")
            continue
        texts[page] = fetch_page(page, timeout=timeout)
        if not texts[page].startswith("!"):
            pages_dir.mkdir(parents=True, exist_ok=True)
            saved.write_text(texts[page], encoding="utf-8")
            print(f"saved {saved.relative_to(ROOT) if saved.is_relative_to(ROOT) else saved}",
                  file=sys.stderr)
    return texts


def fetch_page(page: str, *, timeout: float = 30.0) -> str:
    """Fetch one page as wikitext; failures are returned as ``!message``."""
    request = urllib.request.Request(WIKI_RAW.format(page=page),
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"!could not fetch {page}: {exc}"


def numbers_near(text: str, keywords: Iterable[str], *, window: int = WINDOW) -> list[float]:
    """Every number within ``window`` characters of a keyword occurrence."""
    keywords = tuple(keyword.lower() for keyword in keywords)
    spans: list[tuple[int, int]] = []
    for keyword in keywords:
        start = text.find(keyword)
        if start < 0:
            return []
        while start >= 0:
            spans.append((max(0, start - window), min(len(text), start + len(keyword) + window)))
            start = text.find(keyword, start + 1)
    numbers: set[float] = set()
    for start, end in spans:
        for match in _NUMBER.finditer(text, start, end):
            numbers.add(float(match.group(0)))
    return sorted(numbers)


def resolve(claim: Claim) -> Any:
    """Import and read the code value a claim is pinned to."""
    module_name, attribute = claim.code
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    module = __import__(module_name, fromlist=["_"])
    value = getattr(module, attribute)
    if claim.key is not None:
        value = value[claim.key]
    if claim.args:
        value = value(*claim.args)
    return value


def audit(claims: Iterable[Claim] = CLAIMS,
          pages: Mapping[str, str] | None = None) -> list[ClaimResult]:
    """Run every claim against the supplied page text (or the wiki)."""
    pages = pages if pages is not None else read_pages(None, sorted({c.page for c in claims}))
    results: list[ClaimResult] = []
    for claim in claims:
        result = ClaimResult(claim)
        try:
            result.code_value = resolve(claim)
        except Exception as exc:  # noqa: BLE001 - report, do not abort the audit
            result.code_error = f"{type(exc).__name__}: {exc}"
        text = pages.get(claim.page, "")
        if not isinstance(text, str) or not text.strip():
            result.wiki_error = "page not read"
        elif text.startswith("!"):
            result.wiki_error = text[1:]
        else:
            normalised = plain(text)
            missing = [k for k in claim.keywords if k.lower() not in normalised]
            if missing:
                result.wiki_error = f"keyword not found on the page: {', '.join(missing)}"
            else:
                result.numbers = numbers_near(normalised, claim.keywords)
        results.append(result)
    return results


def snapshot(results: Iterable[ClaimResult]) -> dict[str, list[float]]:
    return {f"{r.claim.page}::{r.claim.topic}": r.numbers for r in results}


def load_snapshot(path: Path) -> dict[str, list[float]]:
    return json.loads(path.read_text(encoding="utf-8"))


def diff(baseline: Mapping[str, Sequence[float]],
         current: Mapping[str, Sequence[float]]) -> dict[str, dict[str, list[float]]]:
    """Numbers added to and removed from each claim since the baseline."""
    changes: dict[str, dict[str, list[float]]] = {}
    for key, numbers in current.items():
        before = list(baseline.get(key, ()))
        added = [n for n in numbers if n not in before]
        removed = [n for n in before if n not in numbers]
        if added or removed:
            changes[key] = {"added": added, "removed": removed}
    for key, numbers in baseline.items():
        if key not in current:
            changes[key] = {"added": [], "removed": list(numbers)}
    return changes


def _format_numbers(values: Iterable[float]) -> str:
    return ", ".join(f"{value:g}" for value in values) or "-"


def report(results: Iterable[ClaimResult], changes: Mapping[str, Any] | None = None) -> str:
    lines: list[str] = []
    for result in results:
        claim = result.claim
        code = (result.code_error
                or f"{claim.describe_code()} = {result.code_value!r} "
                   f"(expected {claim.expected!r})")
        lines.append(f"[{result.status:>12}] {claim.page} :: {claim.topic}")
        lines.append(f"               code: {code}")
        if result.wiki_error:
            lines.append(f"               wiki: {result.wiki_error}")
        else:
            lines.append(f"               wiki numbers near {', '.join(claim.keywords)}: "
                         f"{_format_numbers(result.numbers)}")
        if claim.note:
            lines.append(f"               note: {claim.note}")
    if changes:
        lines.append("")
        lines.append("Changes since the saved snapshot:")
        for key, change in changes.items():
            lines.append(f"  {key}: +[{_format_numbers(change['added'])}] "
                         f"-[{_format_numbers(change['removed'])}]")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pages", type=Path, default=ROOT / "wiki_pages",
                        help="directory for raw page text (read when present, "
                             "filled from the wiki when missing)")
    parser.add_argument("--save-snapshot", type=Path, metavar="FILE",
                        help="write the extracted numbers for a later --baseline diff")
    parser.add_argument("--baseline", type=Path, metavar="FILE",
                        help="compare the extracted numbers with a saved snapshot")
    parser.add_argument("--json", action="store_true",
                        help="print one JSON object instead of the text report")
    parser.add_argument("--topic", action="append", metavar="TEXT",
                        help="only audit claims whose topic contains TEXT")
    args = parser.parse_args(argv)

    claims = [claim for claim in CLAIMS
              if not args.topic or any(word.lower() in claim.topic.lower()
                                       for word in args.topic)]
    if not claims:
        print("No claim matched --topic.", file=sys.stderr)
        return 2
    pages = read_pages(args.pages, sorted({claim.page for claim in claims}))
    results = audit(claims, pages)
    current = snapshot(results)
    changes = diff(load_snapshot(args.baseline), current) if args.baseline else None

    if args.json:
        print(json.dumps({
            "claims": [{"page": r.claim.page, "topic": r.claim.topic,
                        "status": r.status, "numbers": r.numbers,
                        "optional": r.claim.optional,
                        "code": r.claim.describe_code(), "code_value": r.code_value,
                        "expected": r.claim.expected, "note": r.claim.note,
                        "error": r.wiki_error or r.code_error}
                       for r in results],
            "changes": changes,
        }, indent=2, sort_keys=True))
    else:
        print(report(results, changes))

    if args.save_snapshot:
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")

    if any(result.status == "unreadable" for result in results):
        return 2
    if any(result.status == "code-changed" for result in results):
        return 1
    if any(result.status == "wiki-changed" for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
