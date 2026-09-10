"""bm25.py — Fast, zero-dependency BM25 Okapi lexical search engine for KAVACH.

Implements standard BM25 Okapi (k1=1.5, b=0.75) with inverted indexing and
vectorized scoring, persisting to JSON alongside FAISS in the Knowledge Vault.
"""

import json
import math
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}


def tokenize(text: str) -> List[str]:
    """Extracts lowercase alphanumeric tokens, filtering single characters and standard stopwords."""
    words = re.findall(r"[a-zA-Z0-9_\-]+", (text or "").lower())
    return [w for w in words if len(w) > 1 and w not in STOPWORDS]


class BM25Index:
    """Inverted index with BM25 Okapi scoring."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size: int = 0
        self.avgdl: float = 0.0
        self.doc_lengths: List[int] = []
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        # term -> list of [doc_id, term_frequency]
        self.inverted_index: Dict[str, List[List[int]]] = {}

    def build(self, documents: List[str]) -> "BM25Index":
        """Builds the inverted index and IDF weights from a list of document chunk texts."""
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            self.avgdl = 0.0
            self.doc_lengths = []
            self.doc_freqs = {}
            self.idf = {}
            self.inverted_index = {}
            return self

        self.doc_lengths = []
        self.doc_freqs = {}
        self.inverted_index = {}
        total_len = 0

        for doc_id, doc_text in enumerate(documents):
            tokens = tokenize(doc_text)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            # Count term frequencies in this document
            tf_map: Dict[str, int] = {}
            for t in tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            for t, tf in tf_map.items():
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1
                if t not in self.inverted_index:
                    self.inverted_index[t] = []
                self.inverted_index[t].append([doc_id, tf])

        self.avgdl = total_len / self.corpus_size if self.corpus_size > 0 else 0.0

        # Compute Robertson-Spärck Jones IDF
        self.idf = {}
        for term, df in self.doc_freqs.items():
            val = (self.corpus_size - df + 0.5) / (df + 0.5)
            self.idf[term] = math.log(1.0 + max(val, 1e-4))

        return self

    def score(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """Scores all indexed documents against query and returns top_k as [(doc_id, score), ...]."""
        if self.corpus_size == 0 or self.avgdl == 0:
            return []

        tokens = tokenize(query)
        if not tokens:
            return []

        scores: Dict[int, float] = {}

        for t in tokens:
            if t not in self.inverted_index:
                continue

            idf = self.idf.get(t, 0.0)
            postings = self.inverted_index[t]

            for doc_id, tf in postings:
                doc_len = self.doc_lengths[doc_id]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
                if denom > 0:
                    term_score = idf * ((tf * (self.k1 + 1.0)) / denom)
                    scores[doc_id] = scores.get(doc_id, 0.0) + term_score

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def save(self, path: Path) -> None:
        """Serializes the index state to JSON."""
        data = {
            "k1": self.k1,
            "b": self.b,
            "corpus_size": self.corpus_size,
            "avgdl": self.avgdl,
            "doc_lengths": self.doc_lengths,
            "doc_freqs": self.doc_freqs,
            "idf": self.idf,
            "inverted_index": self.inverted_index,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: Path) -> Optional["BM25Index"]:
        """Deserializes index from JSON if present."""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            idx = cls(k1=data.get("k1", 1.5), b=data.get("b", 0.75))
            idx.corpus_size = data.get("corpus_size", 0)
            idx.avgdl = data.get("avgdl", 0.0)
            idx.doc_lengths = data.get("doc_lengths", [])
            idx.doc_freqs = data.get("doc_freqs", {})
            idx.idf = data.get("idf", {})
            idx.inverted_index = data.get("inverted_index", {})
            return idx
        except Exception:
            return None
