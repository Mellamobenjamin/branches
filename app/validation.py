"""Deterministic, read-only genealogy validation.

The validator reports imported assertions; it never edits or chooses facts.  It
currently works against ``GedcomRepository`` so it can protect the existing app,
and its finding shape is intended to survive the move to staged database imports.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import json
import re


SEVERITY_ORDER = {"fatal": 0, "error": 1, "warning": 2, "notice": 3}
RULESET_VERSION = "2026.08.30.2"
RULES = {
    "maximum_lifespan_error": 150,
    "maximum_lifespan_warning": 105,
    "minimum_parent_age": 12,
    "maximum_mother_age": 55,
    "maximum_father_age": 80,
    "minimum_marriage_age": 14,
    "posthumous_father_allowance_years": 1,
}


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    severity: str
    message: str
    people: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    values: dict = field(default_factory=dict)
    rule_version: str = RULESET_VERSION

    def to_dict(self):
        return asdict(self)


@dataclass
class ValidationReport:
    people_count: int
    family_count: int
    findings: list[ValidationFinding]
    metrics: dict = field(default_factory=dict)

    @property
    def counts(self):
        counts = Counter(finding.severity for finding in self.findings)
        return {severity: counts.get(severity, 0) for severity in SEVERITY_ORDER}

    @property
    def publishable(self):
        return not any(f.severity in ("fatal", "error") for f in self.findings)

    def to_dict(self):
        return {
            "people": self.people_count,
            "families": self.family_count,
            "publishable": self.publishable,
            "counts": self.counts,
            "metrics": self.metrics,
            "ruleset_version": RULESET_VERSION,
            "thresholds": RULES,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_markdown(self, title="Family Validation Audit"):
        lines = [
            f"# {title}",
            "",
            f"**Dataset:** {self.people_count} people and {self.family_count} families  ",
            f"**Publication gate:** {'PASS' if self.publishable else 'BLOCKED'}  ",
            (
                "**Findings:** "
                + ", ".join(f"{count} {severity}" for severity, count in self.counts.items())
            ),
            "",
            "Validation is read-only. Findings describe imported assertions and do not alter them.",
            "",
        ]
        grouped = defaultdict(list)
        for finding in self.findings:
            grouped[finding.severity].append(finding)
        for severity in SEVERITY_ORDER:
            items = grouped.get(severity, [])
            if not items:
                continue
            lines.extend([f"## {severity.title()} ({len(items)})", ""])
            for finding in items:
                refs = []
                if finding.people:
                    refs.append("people: " + ", ".join(f"`{value}`" for value in finding.people))
                if finding.families:
                    refs.append("families: " + ", ".join(f"`{value}`" for value in finding.families))
                suffix = f" ({'; '.join(refs)})" if refs else ""
                lines.append(f"- **{finding.code}** — {finding.message}{suffix}")
            lines.append("")
        return "\n".join(lines)


def validate_repository(repo):
    """Return deterministic findings for a parsed GEDCOM repository."""
    people, families = repo.people, repo.families
    findings = []

    def add(code, severity, message, people_ids=(), family_ids=(), **values):
        findings.append(ValidationFinding(
            code=code, severity=severity, message=message,
            people=tuple(people_ids), families=tuple(family_ids), values=values,
        ))

    def person_name(person_id):
        person = people.get(person_id)
        return person.clean_name if person else f"missing person {person_id}"

    def years(person, kind):
        return [event.year for event in person.events if event.kind == kind and event.year]

    def first_year(person, kind):
        values = years(person, kind)
        return values[0] if values else None

    def first_date(person, kind):
        event = person.event(kind)
        return event.date_value if event else None

    # Vital chronology and competing values.
    lifespans = []
    for person in people.values():
        birth, death = first_year(person, "BIRT"), first_year(person, "DEAT")
        if birth and death:
            lifespan = death - birth
            lifespans.append(lifespan)
            birth_date, death_date = first_date(person, "BIRT"), first_date(person, "DEAT")
            definitely_reversed = (
                birth_date and death_date
                and birth_date.start_year is not None
                and death_date.end_year is not None
                and death_date.end_year < birth_date.start_year
            )
            minimum_lifespan = (
                death_date.start_year - birth_date.end_year
                if death_date.start_year is not None and birth_date.end_year is not None
                else None
            )
            if definitely_reversed:
                add("VITAL_ORDER", "error",
                    f"{person.clean_name} dies before their recorded birth ({birth}–{death}).",
                    (person.id,), lifespan=lifespan)
            elif minimum_lifespan is not None and minimum_lifespan >= RULES["maximum_lifespan_error"]:
                add("LIFESPAN_150", "error",
                    f"{person.clean_name} has a stated lifespan of {lifespan} years ({birth}–{death}).",
                    (person.id,), lifespan=lifespan)
            elif minimum_lifespan is not None and minimum_lifespan > RULES["maximum_lifespan_warning"]:
                add("LIFESPAN_OVER_105", "warning",
                    f"{person.clean_name} has a stated lifespan of {lifespan} years ({birth}–{death}).",
                    (person.id,), lifespan=lifespan)
        for kind in ("BIRT", "DEAT"):
            distinct = sorted(set(years(person, kind)))
            if len(distinct) > 1:
                vital_label = "birth" if kind == "BIRT" else "death"
                add("CONFLICTING_VITAL_YEARS", "warning",
                    f"{person.clean_name} has multiple {vital_label} years: {', '.join(map(str, distinct))}.",
                    (person.id,), event_kind=kind, years=distinct)

    parents = defaultdict(set)
    spouses = defaultdict(set)
    link_issues = set()

    for family in families.values():
        if family.husband and family.husband not in people:
            add("MISSING_PERSON_REFERENCE", "error",
                f"Family {family.id} references missing husband {family.husband}.",
                family_ids=(family.id,), missing_id=family.husband)
        if family.wife and family.wife not in people:
            add("MISSING_PERSON_REFERENCE", "error",
                f"Family {family.id} references missing wife {family.wife}.",
                family_ids=(family.id,), missing_id=family.wife)
        for child_id in family.children:
            if child_id not in people:
                add("MISSING_PERSON_REFERENCE", "error",
                    f"Family {family.id} references missing child {child_id}.",
                    family_ids=(family.id,), missing_id=child_id)

        if family.husband and family.wife:
            spouses[family.husband].add(family.wife)
            spouses[family.wife].add(family.husband)
            if family.husband == family.wife:
                add("SELF_SPOUSE", "error", f"Family {family.id} uses one person as both spouses.",
                    (family.husband,), (family.id,))

        for person_id, role, expected in (
            (family.husband, "husband", "M"), (family.wife, "wife", "F")
        ):
            person = people.get(person_id)
            if person and person.sex and person.sex != expected:
                add("SPOUSE_ROLE_SEX", "warning",
                    f"{person.clean_name} is the {role} in {family.id} but has SEX {person.sex}.",
                    (person.id,), (family.id,), role=role, sex=person.sex)
            if person and family.id not in person.spouse_families:
                link_issues.add(("FAMILY_MISSING_FAMS", family.id, person.id))

        marriage_events = [event for event in family.events
                           if event.kind == "MARR" and event.year]
        for marriage_event in marriage_events:
            marriage_year = marriage_event.year
            marriage_date = marriage_event.date_value
            for person_id, role in ((family.husband, "husband"), (family.wife, "wife")):
                person = people.get(person_id)
                if not person:
                    continue
                birth, death = first_year(person, "BIRT"), first_year(person, "DEAT")
                birth_date, death_date = first_date(person, "BIRT"), first_date(person, "DEAT")
                oldest_possible_age = (
                    marriage_date.end_year - birth_date.start_year
                    if birth_date and marriage_date.end_year is not None
                    and birth_date.start_year is not None else None
                )
                if oldest_possible_age is not None and oldest_possible_age < RULES["minimum_marriage_age"]:
                    add("MARRIAGE_UNDER_14", "warning",
                        f"{person.clean_name} is {marriage_year - birth} at a recorded marriage in {family.id}.",
                        (person.id,), (family.id,), marriage_year=marriage_year)
                definitely_after_death = (
                    death_date and marriage_date.start_year is not None
                    and death_date.end_year is not None
                    and marriage_date.start_year > death_date.end_year
                )
                if definitely_after_death:
                    add("MARRIAGE_AFTER_DEATH", "error",
                        f"{person.clean_name}'s marriage in {family.id} is {marriage_year - death} years after their recorded death.",
                        (person.id,), (family.id,), marriage_year=marriage_year, death_year=death)

        for child_id in family.children:
            if child_id in (family.husband, family.wife):
                add("SPOUSE_IS_CHILD", "error",
                    f"{person_name(child_id)} is both spouse and child in {family.id}.",
                    (child_id,), (family.id,))
            child = people.get(child_id)
            if child and family.id not in child.child_families:
                link_issues.add(("CHILD_FAMC_DIFFERS", family.id, child_id))
            for parent_id, role in ((family.husband, "father"), (family.wife, "mother")):
                if not parent_id:
                    continue
                parents[child_id].add(parent_id)
                parent = people.get(parent_id)
                if not parent or not child:
                    continue
                parent_birth = first_year(parent, "BIRT")
                child_birth = first_year(child, "BIRT")
                if parent_birth and child_birth:
                    age = child_birth - parent_birth
                    maximum = (RULES["maximum_father_age"] if role == "father"
                               else RULES["maximum_mother_age"])
                    parent_birth_date = first_date(parent, "BIRT")
                    child_birth_date = first_date(child, "BIRT")
                    oldest_possible_age = (
                        child_birth_date.end_year - parent_birth_date.start_year
                        if parent_birth_date and child_birth_date
                        and child_birth_date.end_year is not None
                        and parent_birth_date.start_year is not None else None
                    )
                    youngest_possible_age = (
                        child_birth_date.start_year - parent_birth_date.end_year
                        if parent_birth_date and child_birth_date
                        and child_birth_date.start_year is not None
                        and parent_birth_date.end_year is not None else None
                    )
                    definitely_too_young = (
                        oldest_possible_age is not None
                        and oldest_possible_age < RULES["minimum_parent_age"]
                    )
                    definitely_too_old = (
                        youngest_possible_age is not None and youngest_possible_age > maximum
                    )
                    if definitely_too_young or definitely_too_old:
                        add("IMPLAUSIBLE_PARENT_AGE", "error",
                            f"{parent.clean_name} is {age} at {child.clean_name}'s recorded birth.",
                            (parent.id, child.id), (family.id,), role=role, age=age)
                parent_death = first_year(parent, "DEAT")
                allowed_posthumous_years = (
                    RULES["posthumous_father_allowance_years"] if role == "father" else 0
                )
                parent_death_date = first_date(parent, "DEAT")
                child_birth_date = first_date(child, "BIRT")
                definitely_after_parent_death = (
                    parent_death_date and child_birth_date
                    and parent_death_date.end_year is not None
                    and child_birth_date.start_year is not None
                    and child_birth_date.start_year > parent_death_date.end_year + allowed_posthumous_years
                )
                if parent_death and child_birth and definitely_after_parent_death:
                    years_after = child_birth - parent_death
                    year_word = "year" if years_after == 1 else "years"
                    add("BIRTH_AFTER_PARENT_DEATH", "error",
                        f"{child.clean_name} is born {years_after} {year_word} after recorded {role} {parent.clean_name}'s death.",
                        (parent.id, child.id), (family.id,), role=role)

    for person in people.values():
        for family_id in person.spouse_families:
            family = families.get(family_id)
            if not family:
                add("MISSING_FAMILY_REFERENCE", "error",
                    f"{person.clean_name} references missing spouse family {family_id}.",
                    (person.id,), missing_id=family_id)
            elif person.id not in (family.husband, family.wife):
                link_issues.add(("FAMS_PERSON_NOT_SPOUSE", family_id, person.id))
        for family_id in person.child_families:
            family = families.get(family_id)
            if not family:
                add("MISSING_FAMILY_REFERENCE", "error",
                    f"{person.clean_name} references missing parent family {family_id}.",
                    (person.id,), missing_id=family_id)
            elif person.id not in family.children:
                link_issues.add(("FAMC_PERSON_NOT_CHILD", family_id, person.id))

    for code, family_id, person_id in sorted(link_issues):
        add(code, "warning",
            f"{person_name(person_id)} and family {family_id} do not have reciprocal GEDCOM links.",
            (person_id,), (family_id,))

    # Multiple parent-family assertions are preserved even while public traversal
    # continues to use one compatibility primary pending editorial review.
    for person_id, person in people.items():
        family_ids = person.child_families
        if len(family_ids) > 1:
            qualifiers = [{"family": link.family_id, "pedigree": link.pedigree,
                           "status": link.status} for link in person.parent_family_links]
            add("MULTIPLE_PARENT_FAMILIES", "warning",
                f"{person_name(person_id)} has multiple parent families: {', '.join(family_ids)}.",
                (person_id,), tuple(family_ids), qualifiers=qualifiers)

    # Pedigree traversal catches cycles and direct ancestor/spouse pairings.
    def is_ancestor(ancestor_id, person_id):
        stack = list(parents.get(person_id, ()))
        seen = set()
        while stack:
            current = stack.pop()
            if current == ancestor_id:
                return True
            if current not in seen:
                seen.add(current)
                stack.extend(parents.get(current, ()))
        return False

    for person_id in people:
        if is_ancestor(person_id, person_id):
            add("PEDIGREE_CYCLE", "error",
                f"{person_name(person_id)} participates in a parent-child cycle.", (person_id,))
    seen_pairs = set()
    for first_id, partners in spouses.items():
        for second_id in partners:
            pair = tuple(sorted((first_id, second_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if is_ancestor(first_id, second_id) or is_ancestor(second_id, first_id):
                add("ANCESTOR_SPOUSE", "error",
                    f"{person_name(first_id)} and {person_name(second_id)} are spouses and direct ancestors of one another.",
                    pair)

    # Duplicate candidates deliberately ignore punctuation in names.
    duplicate_groups = defaultdict(list)
    for person in people.values():
        identity_name = re.sub(r"[^a-z0-9]+", "", person.clean_name.casefold())
        duplicate_groups[(identity_name, first_year(person, "BIRT"), first_year(person, "DEAT"))].append(person)
    for (_, birth, death), group in duplicate_groups.items():
        if len(group) > 1 and (birth or death):
            add("PROBABLE_DUPLICATE_PERSON", "warning",
                f"Probable duplicate identity: {', '.join(p.clean_name for p in group)} ({birth or '?'}–{death or '?'}).",
                tuple(person.id for person in group), birth_year=birth, death_year=death)

    findings.sort(key=lambda item: (
        SEVERITY_ORDER[item.severity], item.code, item.people, item.families, item.message
    ))
    metrics = {
        "maximum_stated_lifespan": max(lifespans) if lifespans else None,
        "lifespans_150_or_more": sum(value >= 150 for value in lifespans),
        "pedigree_cycles": sum(f.code == "PEDIGREE_CYCLE" for f in findings),
        "probable_duplicate_groups": sum(f.code == "PROBABLE_DUPLICATE_PERSON" for f in findings),
    }
    return ValidationReport(len(people), len(families), findings, metrics)
