"""Retrieval: ingestion -> structure-aware chunks -> BM25 + dense -> hybrid (reciprocal rank fusion) -> rerank.

No external services: BM25 is implemented here, and the default dense embedder is a hashed character n-gram TF-IDF
vector (a dependency-free stand-in). Swap in a real embedding model through the Embedder protocol; the retrieval
evaluation (evaluate_retrieval) then shows whether it helps, stage by stage.
"""
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

STOP = set("""a an and are as at be by does for from has have how in is it its many of on or that the this to was
were what when which with without before after than any all must not only per""".split())


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if t in STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # light plural stemming: weeks -> week, flags -> flag
        out.append(t)
    return out


# ------------------------------------------------------------------ ingestion and chunking
@dataclass
class Chunk:
    id: str                 # e.g. "MP-117#C2"
    policy_id: str
    title: str              # section or clause title
    text: str
    kind: str               # scope | definitions | criterion | red_flag | exclusions | documentation | other
    meta: dict = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return f"{self.meta.get('policy_title', '')}. {self.title}. {self.text}"


@dataclass
class PolicyDoc:
    policy_id: str
    title: str
    codes: list[str]
    body_region: str
    chunks: list[Chunk]

    def criteria(self) -> list[Chunk]:
        return [c for c in self.chunks if c.kind == "criterion"]

    def chunk(self, chunk_id: str) -> Chunk | None:
        return next((c for c in self.chunks if c.id == chunk_id), None)

    def waives(self) -> list[str]:
        """Criterion ids a red flag waives, read from the red-flag clause title, e.g. 'waive C1 and C2'."""
        rf = self.chunk(f"{self.policy_id}#RF")
        return re.findall(r"\b([A-Z]\d)\b", rf.title) if rf else []


def parse_policy(markdown: str) -> PolicyDoc:
    """Chunk a policy by its structure: one chunk per '##' section, and one per '###' clause inside it."""
    head = re.search(r"^# ([A-Z]+-\d+): (.+)$", markdown, re.M)
    if not head:
        raise ValueError("policy must start with '# <ID>: <title>'")
    pid, title = head.group(1), head.group(2).strip()
    codes = re.findall(r"\b\d{5}\b", (re.search(r"^Procedure codes: (.+)$", markdown, re.M) or [""])[0])
    region = (re.search(r"^Body region: (.+)$", markdown, re.M) or ["", ""])[1].strip()
    meta = {"policy_title": title, "codes": codes, "body_region": region}
    chunks: list[Chunk] = []
    for sec in re.split(r"^## ", markdown, flags=re.M)[1:]:
        sec_title, _, body = sec.partition("\n")
        sec_title = sec_title.strip()
        kind = {"scope": "scope", "definitions": "definitions", "coverage criteria": "criteria",
                "red flags": "red_flags", "exclusions": "exclusions",
                "documentation required": "documentation"}.get(sec_title.lower(), "other")
        clauses = re.split(r"^### ", body, flags=re.M)
        intro = clauses[0].strip()
        if kind in ("criteria", "red_flags"):
            for cl in clauses[1:]:
                cl_title, _, cl_body = cl.partition("\n")
                m = re.match(r"([A-Z]+\d*)\. (.+)", cl_title.strip())
                cid = m.group(1) if m else cl_title.strip()
                chunks.append(Chunk(id=f"{pid}#{cid}", policy_id=pid, title=cl_title.strip(),
                                    text=" ".join(cl_body.split()),
                                    kind="criterion" if kind == "criteria" else "red_flag", meta=dict(meta)))
            if intro:
                chunks.append(Chunk(id=f"{pid}#{kind}", policy_id=pid, title=sec_title, text=" ".join(intro.split()),
                                    kind="other", meta=dict(meta)))
        else:
            chunks.append(Chunk(id=f"{pid}#{kind if kind != 'other' else sec_title.lower()}", policy_id=pid,
                                title=sec_title, text=" ".join(body.split()), kind=kind, meta=dict(meta)))
    return PolicyDoc(policy_id=pid, title=title, codes=codes, body_region=region, chunks=chunks)


# ------------------------------------------------------------------ retrievers
class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.toks = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.toks)) / max(1, len(self.toks))
        df = Counter(t for doc in self.toks for t in set(doc))
        n = len(self.toks)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for doc in self.toks:
            tf, s = Counter(doc), 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.avg))
            out.append(s)
        return out


class Embedder(Protocol):
    def fit(self, docs: list[str]) -> None: ...
    def embed(self, text: str) -> dict[int, float]: ...


class HashingEmbedder:
    """Character 3-5 gram + word features hashed into a sparse vector, TF-IDF weighted, L2-normalized.
    Captures morphology and partial matches ('radiculopathy' ~ 'radicular') that BM25 misses."""

    def __init__(self, dims: int = 4096):
        self.dims, self.idf = dims, {}

    def _feats(self, text: str) -> list[int]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = [f"w:{w}" for w in words if w not in STOP]
        for w in words:
            p = f" {w} "
            feats += [p[i:i + n] for n in (3, 4, 5) for i in range(max(0, len(p) - n + 1))]
        return [int(hashlib.md5(f.encode()).hexdigest()[:8], 16) % self.dims for f in feats]

    def fit(self, docs: list[str]) -> None:
        df = Counter(h for d in docs for h in set(self._feats(d)))
        n = len(docs)
        self.idf = {h: math.log((1 + n) / (1 + c)) + 1 for h, c in df.items()}

    def embed(self, text: str) -> dict[int, float]:
        tf = Counter(self._feats(text))
        v = {h: c * self.idf.get(h, 1.0) for h, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {h: x / norm for h, x in v.items()}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(h, 0.0) for h, x in a.items())


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    out: dict[int, float] = {}
    for ranking in rankings:
        for r, i in enumerate(ranking):
            out[i] = out.get(i, 0.0) + 1.0 / (k + r + 1)
    return out


def _order(scores: list[float] | dict[int, float]) -> list[int]:
    items = scores.items() if isinstance(scores, dict) else enumerate(scores)
    return [i for i, s in sorted(items, key=lambda x: -x[1]) if s > 0]


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Index:
    """Hybrid index over chunks (policy clauses, or note sentences). stage: bm25 | dense | hybrid | rerank."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None):
        self.chunks = chunks
        texts = [c.search_text for c in chunks]
        self.bm25 = BM25(texts)
        self.embedder = embedder or HashingEmbedder()
        self.embedder.fit(texts)
        self.vecs = [self.embedder.embed(t) for t in texts]

    def search(self, query: str, k: int = 5, stage: str = "rerank") -> list[Hit]:
        bm = self.bm25.scores(query)
        qv = self.embedder.embed(query)
        dense = [cosine(qv, v) for v in self.vecs]
        if stage == "bm25":
            scores = {i: s for i, s in enumerate(bm)}
        elif stage == "dense":
            scores = {i: s for i, s in enumerate(dense)}
        else:
            scores = rrf([_order(bm), _order(dense)])
            if stage == "rerank":
                scores = {i: s * rerank_boost(query, self.chunks[i]) for i, s in scores.items()}
        ranked = sorted(((i, s) for i, s in scores.items() if s > 0), key=lambda x: -x[1])[:k]
        return [Hit(self.chunks[i], s) for i, s in ranked]


BODY_TERMS = {"lumbar": "lumbar", "low back": "lumbar", "lower back": "lumbar", "back pain": "lumbar",
              "cervical": "cervical", "neck": "cervical", "knee": "knee", "meniscus": "knee", "shoulder": "shoulder",
              "rotator": "shoulder", "physical therapy visits": "rehabilitation"}
MODALITY = {"mri": "mri", "magnetic resonance": "mri", "ct ": "ct", "computed tomography": "ct"}


def rerank_boost(query: str, chunk: Chunk) -> float:
    """Metadata-aware reranking: an exact procedure code, the body region and the imaging modality named in the
    query are matched against the chunk's policy metadata (the way a production retriever uses filters)."""
    q = f" {query.lower()} "
    boost = 1.0
    if any(code in q for code in chunk.meta.get("codes", [])):
        boost *= 3.0
    region = (chunk.meta.get("body_region", "") + " " + chunk.meta.get("policy_title", "")).lower()
    want = {v for k, v in BODY_TERMS.items() if k in q}
    if want:
        boost *= 1.6 if any(w in region for w in want) else 0.6
    title = chunk.meta.get("policy_title", "").lower()
    mods = {v for k, v in MODALITY.items() if k in q}
    if mods:
        boost *= 1.3 if any((m == "mri" and "mri" in title) or (m == "ct" and title.startswith("ct")) for m in mods) else 0.8
    return boost


# ------------------------------------------------------------------ policy library
class PolicyLibrary:
    def __init__(self, docs: list[PolicyDoc], embedder: Embedder | None = None):
        self.docs = {d.policy_id: d for d in docs}
        self.index = Index([c for d in docs for c in d.chunks], embedder)

    def search_clauses(self, query: str, k: int = 5, stage: str = "rerank") -> list[Hit]:
        return self.index.search(query, k, stage)

    def search_policies(self, query: str, k: int = 3, stage: str = "rerank") -> list[tuple[str, float]]:
        """Policies ranked by their best-matching chunk."""
        best: dict[str, float] = {}
        for h in self.index.search(query, k=len(self.index.chunks), stage=stage):
            best[h.chunk.policy_id] = max(best.get(h.chunk.policy_id, 0.0), h.score)
        return sorted(best.items(), key=lambda x: -x[1])[:k]


def evaluate_retrieval(lib: PolicyLibrary, queries: list[dict], stages=("bm25", "dense", "hybrid", "rerank")) -> dict:
    """Recall@1, recall@3 and MRR per stage, for policy routing and clause lookup separately."""
    out = {}
    for stage in stages:
        per_kind: dict[str, list[int | None]] = {"policy": [], "clause": []}
        for q in queries:
            if q["kind"] == "policy":
                ranked = [p for p, _ in lib.search_policies(q["q"], k=10, stage=stage)]
            else:
                ranked = [h.chunk.id for h in lib.search_clauses(q["q"], k=10, stage=stage)]
            per_kind[q["kind"]].append(ranked.index(q["expect"]) + 1 if q["expect"] in ranked else None)
        out[stage] = {kind: {"n": len(r), "recall@1": round(sum(1 for x in r if x == 1) / len(r), 3),
                             "recall@3": round(sum(1 for x in r if x and x <= 3) / len(r), 3),
                             "mrr": round(sum(1 / x for x in r if x) / len(r), 3)}
                      for kind, r in per_kind.items() if r}
    return out
