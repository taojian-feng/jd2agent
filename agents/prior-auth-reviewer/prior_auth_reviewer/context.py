"""Context engineering: mask identifiers, split notes into citable sentences, keep only what the criteria need.

Minimum necessary in practice: identifiers are masked before anything is indexed, and sentences that no criterion
(or red flag) retrieves are dropped before the model sees the case. Every kept sentence keeps its original id
(N1, N2, ...), so citations stay stable and can be checked against the full note.
"""
import re
from dataclasses import dataclass

from prior_auth_reviewer.retrieval import Chunk, Index, PolicyDoc

MASKS = [
    (re.compile(r"\bM-\d{4}\b"), "[MEMBER]"),
    (re.compile(r"\bDOB:? \d{4}-\d{2}-\d{2}\b"), "DOB [DATE]"),
    (re.compile(r"(Ordering clinician: )[A-Z][a-z]+ [A-Z][a-z]+(, [A-Z]{2})?"), r"\1[CLINICIAN]"),
]


def mask(text: str) -> tuple[str, int]:
    n = 0
    for pat, rep in MASKS:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def sentences(notes: str) -> list[tuple[str, str]]:
    """[(id, sentence)] with ids N1..Nn in note order."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", " ".join(notes.split())) if p.strip()]
    return [(f"N{i}", s) for i, s in enumerate(parts, 1)]


@dataclass
class CaseContext:
    kept: list[tuple[str, str]]          # (sentence id, masked text) shown to the model
    dropped: list[str]                   # ids not shown
    masked_identifiers: int
    per_criterion: dict[str, list[str]]  # criterion id -> retrieved sentence ids (most relevant first)

    omitted: dict[str, str] | None = None   # sentence id -> why it is not shown

    def text(self) -> str:
        lines = [f"{sid}: {s}" for sid, s in self.kept]
        if self.omitted:
            groups: dict[str, list[str]] = {}
            for sid, why in self.omitted.items():
                groups.setdefault(why, []).append(sid)
            lines.append("Not shown: " + "; ".join(f"{', '.join(ids)} ({why})" for why, ids in groups.items())
                         + ". Every other sentence of the note is shown above.")
        return "\n".join(lines)

    def ids(self) -> set[str]:
        return {sid for sid, _ in self.kept}


def criterion_queries(policy: PolicyDoc) -> dict[str, str]:
    q = {c.id.split("#")[1]: f"{c.title} {c.text}" for c in policy.criteria()}
    rf = policy.chunk(f"{policy.policy_id}#RF")
    if rf:
        q["RF"] = f"{rf.title} {rf.text}"
    return q


def assemble(notes: str, policy: PolicyDoc, per_criterion_k: int = 3, max_sentences: int = 12) -> CaseContext:
    masked, n_masked = mask(notes)
    sents = sentences(masked)
    index = Index([Chunk(id=sid, policy_id="notes", title="", text=s, kind="sentence") for sid, s in sents])
    per: dict[str, list[str]] = {}
    for cid, query in criterion_queries(policy).items():
        per[cid] = [h.chunk.id for h in index.search(query, k=per_criterion_k, stage="hybrid")]
    # keep sentences by best rank across criteria until the budget is reached
    best: dict[str, int] = {}
    for ids in per.values():
        for rank, sid in enumerate(ids):
            best[sid] = min(best.get(sid, 99), rank)
    keep = set(sorted(best, key=lambda s: (best[s], int(s[1:])))[:max_sentences])
    kept = [(sid, s) for sid, s in sents if sid in keep]
    omitted = {sid: "identifier line only" if _identifier_only(s) else "no criterion or red flag retrieved it"
               for sid, s in sents if sid not in keep}
    return CaseContext(kept=kept, dropped=[sid for sid, _ in sents if sid not in keep],
                       masked_identifiers=n_masked, per_criterion=per, omitted=omitted)


def _identifier_only(sentence: str) -> bool:
    rest = re.sub(r"\[(MEMBER|DATE|CLINICIAN)\]|Member|DOB|Ordering clinician:|[.,:\s]", "", sentence)
    return rest == ""


def gold_retention(ctx: CaseContext, gold: dict[str, list[str]]) -> tuple[int, int]:
    """(gold phrases found in kept sentences, gold phrases total). Used to measure context recall."""
    text = " ".join(s for _, s in ctx.kept).lower()
    phrases = [p for ps in gold.values() for p in ps]
    return sum(p.lower() in text for p in phrases), len(phrases)
