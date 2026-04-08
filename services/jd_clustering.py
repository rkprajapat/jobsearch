from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import json
import re
from typing import Sequence

from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
import spacy

from models.opportunity import Opportunity, load_opportunities

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"
_CLUSTERS_FILE = _PROJECT_DATA / "clusters.json"


@dataclass(slots=True)
class _PreparedOpportunity:
    opportunity: Opportunity
    processed_text: str
    keyword_lemmas: list[str]


class JDClusteringService:
    def __init__(
        self,
        k: int,
        write_versioned_output: bool = True,
        explicit_stopwords: Sequence[str] | None = None,
    ) -> None:
        if k <= 0:
            raise ValueError("k must be greater than 0")

        self.k = k
        self.write_versioned_output = write_versioned_output
        self._nlp = self._load_nlp()
        self._dynamic_stopwords: set[str] = set()
        self._explicit_stopwords = self._normalize_stopword_terms(explicit_stopwords or [])
        self._explicit_stopwords_unigrams = {
            term for term in self._explicit_stopwords if " " not in term
        }
        self._explicit_stopword_phrase_tokens = [
            tuple(term.split())
            for term in sorted(
                (term for term in self._explicit_stopwords if " " in term),
                key=len,
                reverse=True,
            )
        ]

    def _load_nlp(self):
        try:
            return spacy.load("en_core_web_sm")
        except Exception:
            print("en_core_web_sm is not available. Falling back to spaCy blank English model.")
            return spacy.blank("en")

    def _normalize_lemma(self, token) -> str | None:
        if token.is_space or token.is_punct or token.is_stop or token.like_num:
            return None

        normalized = (token.lemma_ or token.text).strip().lower()
        if not normalized or normalized == "-pron-":
            normalized = token.text.strip().lower()

        if not normalized or len(normalized) < 3:
            return None

        if normalized == "datum":
            normalized = "data"

        if not re.match(r"^[a-z][a-z\-]*$", normalized):
            return None

        return normalized

    def _extract_processed_and_keywords(self, text: str) -> tuple[str, list[str]]:
        doc = self._nlp(text)
        tokens: list[str] = []
        keyword_lemmas: list[str] = []

        for token in doc:
            normalized = self._normalize_lemma(token)
            if not normalized:
                continue

            tokens.append(normalized)
            if not token.pos_ or token.pos_ in {"NOUN", "PROPN"}:
                keyword_lemmas.append(normalized)

        return " ".join(tokens), keyword_lemmas

    def _normalize_stopword_terms(self, terms: Sequence[str]) -> set[str]:
        normalized_terms: set[str] = set()
        for term in terms:
            cleaned = re.sub(r"\s+", " ", str(term).strip().lower())
            if cleaned:
                normalized_terms.add(cleaned)
        return normalized_terms

    def _remove_phrase_stopwords(self, tokens: list[str]) -> list[str]:
        if not tokens or not self._explicit_stopword_phrase_tokens:
            return tokens

        result: list[str] = []
        i = 0
        while i < len(tokens):
            matched = False
            for phrase_tokens in self._explicit_stopword_phrase_tokens:
                phrase_len = len(phrase_tokens)
                if i + phrase_len <= len(tokens) and tuple(tokens[i : i + phrase_len]) == phrase_tokens:
                    i += phrase_len
                    matched = True
                    break

            if not matched:
                result.append(tokens[i])
                i += 1

        return result

    def _filter_prepared(
        self,
        prepared: list[_PreparedOpportunity],
        blocked_terms: set[str],
    ) -> list[_PreparedOpportunity]:
        filtered: list[_PreparedOpportunity] = []
        for item in prepared:
            filtered_tokens = [token for token in item.processed_text.split() if token not in blocked_terms]
            if blocked_terms is self._explicit_stopwords_unigrams:
                filtered_tokens = self._remove_phrase_stopwords(filtered_tokens)

            if not filtered_tokens:
                continue

            filtered_keywords = [lemma for lemma in item.keyword_lemmas if lemma not in blocked_terms]
            filtered.append(
                _PreparedOpportunity(
                    opportunity=item.opportunity,
                    processed_text=" ".join(filtered_tokens),
                    keyword_lemmas=filtered_keywords,
                )
            )
        return filtered

    def _prepare_opportunities(self) -> list[_PreparedOpportunity]:
        prepared: list[_PreparedOpportunity] = []
        for opportunity in load_opportunities():
            raw_jd = (opportunity.job_description or "").strip()
            if not raw_jd:
                continue

            processed_text, keyword_lemmas = self._extract_processed_and_keywords(raw_jd)
            if not processed_text:
                continue

            prepared.append(
                _PreparedOpportunity(
                    opportunity=opportunity,
                    processed_text=processed_text,
                    keyword_lemmas=keyword_lemmas,
                )
            )

        if not prepared:
            return []

        explicit_filtered = self._filter_prepared(prepared, self._explicit_stopwords_unigrams)
        if not explicit_filtered:
            return []

        self._dynamic_stopwords = self._detect_dynamic_stopwords(explicit_filtered)
        if not self._dynamic_stopwords:
            return explicit_filtered

        return self._filter_prepared(explicit_filtered, self._dynamic_stopwords)

    def _detect_dynamic_stopwords(self, prepared: list[_PreparedOpportunity]) -> set[str]:
        if not prepared:
            return set()

        doc_frequency: Counter[str] = Counter()
        total_frequency: Counter[str] = Counter()
        for item in prepared:
            doc_frequency.update(set(item.keyword_lemmas))
            total_frequency.update(item.keyword_lemmas)

        if not doc_frequency:
            return set()

        total_docs = len(prepared)
        doc_ratio_threshold = 0.6 if total_docs >= 10 else 0.75
        min_doc_count = max(2, math.ceil(total_docs * doc_ratio_threshold))
        return {
            term
            for term, df in doc_frequency.items()
            if df >= min_doc_count and total_frequency[term] >= min_doc_count
        }

    def _build_ngram_terms(self, tokens: list[str], max_n: int = 3) -> list[str]:
        if not tokens:
            return []

        terms: list[str] = []
        upper_n = min(max_n, len(tokens))
        for n in range(1, upper_n + 1):
            for i in range(0, len(tokens) - n + 1):
                terms.append(" ".join(tokens[i : i + n]))
        return terms

    def _extract_ranked_keywords(self, cluster_items: list[_PreparedOpportunity]) -> list[str]:
        if not cluster_items:
            return []

        counts: Counter[str] = Counter()
        doc_frequency: Counter[str] = Counter()
        for item in cluster_items:
            terms = self._build_ngram_terms(item.keyword_lemmas, max_n=3)
            counts.update(terms)
            doc_frequency.update(set(terms))

        scored_terms: list[tuple[str, float, int, int]] = []
        for term, tf in counts.items():
            n = term.count(" ") + 1
            df = doc_frequency.get(term, 1)
            length_boost = 1.0 + (n - 1) * 0.2
            score = (tf * length_boost) + (0.15 * df)
            scored_terms.append((term, score, tf, df))

        scored_terms.sort(key=lambda x: (x[1], x[2], x[3], len(x[0])), reverse=True)
        blocked_terms = self._dynamic_stopwords | self._explicit_stopwords
        return [term for term, _, _, _ in scored_terms if term not in blocked_terms]

    def _extract_summary(self, keywords: list[str]) -> str:
        if not keywords:
            return "No keywords available."

        summary_keyword_count = min(15, len(keywords))
        if summary_keyword_count < 10:
            summary_keyword_count = len(keywords)
        return ", ".join(keywords[:summary_keyword_count])

    def _find_best_cluster_count(self, tfidf_matrix, sample_count: int) -> int:
        if sample_count <= 2:
            return 1

        max_candidate_k = min(self.k, sample_count - 1)
        if max_candidate_k < 2:
            return 1

        dense_matrix = tfidf_matrix.toarray()
        best_k = 2
        best_score = float("-inf")
        for candidate_k in range(2, max_candidate_k + 1):
            labels = AgglomerativeClustering(
                n_clusters=candidate_k,
                metric="cosine",
                linkage="average",
            ).fit_predict(dense_matrix)

            if len(set(labels)) < 2:
                continue

            score = silhouette_score(tfidf_matrix, labels, metric="cosine")
            if score > best_score:
                best_score = score
                best_k = candidate_k

        return best_k

    def _fit_labels(self, tfidf_matrix, sample_count: int, effective_k: int):
        if effective_k == 1:
            return [0] * sample_count
        return AgglomerativeClustering(
            n_clusters=effective_k,
            metric="cosine",
            linkage="average",
        ).fit_predict(tfidf_matrix.toarray())

    def _group_cluster_indices(self, labels) -> dict[int, list[int]]:
        clusters: dict[int, list[int]] = {}
        for idx, cluster_id in enumerate(labels):
            clusters.setdefault(int(cluster_id), []).append(idx)
        return clusters

    def _build_cluster_payload(
        self,
        prepared: list[_PreparedOpportunity],
        clusters: dict[int, list[int]],
    ) -> list[dict]:
        sorted_cluster_ids = sorted(
            clusters,
            key=lambda cluster_id: len(clusters[cluster_id]),
            reverse=True,
        )
        strong_cluster_ids = sorted_cluster_ids[: min(self.k, len(sorted_cluster_ids))]

        payload: list[dict] = []
        for cluster_id in strong_cluster_ids:
            cluster_items = [prepared[i] for i in clusters[cluster_id]]
            opportunities = [item.opportunity for item in cluster_items]
            keywords = self._extract_ranked_keywords(cluster_items)

            payload.append(
                {
                    "cluster_id": cluster_id,
                    "total_opportunities": len(opportunities),
                    "summary_keywords": self._extract_summary(keywords),
                    "keywords": keywords,
                    "opportunities": [
                        {
                            "id": str(opportunity.id),
                            "designation": opportunity.designation,
                        }
                        for opportunity in opportunities
                    ],
                }
            )

        return payload

    def cluster(self) -> dict:
        prepared = self._prepare_opportunities()
        if not prepared:
            raise ValueError("No opportunities with usable job descriptions were found.")

        processed_corpus = [item.processed_text for item in prepared]
        tfidf_matrix = TfidfVectorizer(ngram_range=(1, 3), max_df=0.9).fit_transform(processed_corpus)
        sample_count = len(prepared)
        effective_k = self._find_best_cluster_count(tfidf_matrix, sample_count)
        labels = self._fit_labels(tfidf_matrix, sample_count, effective_k)
        clusters = self._group_cluster_indices(labels)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_k": self.k,
            "effective_k": effective_k,
            "dynamic_stopwords": sorted(self._dynamic_stopwords),
            "explicit_stopwords": sorted(self._explicit_stopwords),
            "clusters": self._build_cluster_payload(prepared, clusters),
        }

    def save_clusters(self, cluster_result: dict) -> dict[str, str]:
        _PROJECT_DATA.mkdir(parents=True, exist_ok=True)
        with open(_CLUSTERS_FILE, "w", encoding="utf-8") as file:
            json.dump(cluster_result, file, indent=4)

        saved_files: dict[str, str] = {"latest": str(_CLUSTERS_FILE)}
        if self.write_versioned_output:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            versioned_path = _PROJECT_DATA / f"clusters_{timestamp}.json"
            with open(versioned_path, "w", encoding="utf-8") as file:
                json.dump(cluster_result, file, indent=4)
            saved_files["versioned"] = str(versioned_path)

        return saved_files

    def run_and_save(self) -> dict[str, str]:
        return self.save_clusters(self.cluster())