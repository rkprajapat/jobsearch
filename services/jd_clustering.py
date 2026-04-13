from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import spacy
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_distances

from configs import PROJECT_DATA_DIR
from models.opportunity import Opportunity, load_opportunities

_CLUSTERS_FILE = PROJECT_DATA_DIR.joinpath("clusters.json")


@dataclass(slots=True)
class _PreparedOpportunity:
    opportunity: Opportunity
    processed_text: str
    keyword_lemmas: list[str]


@dataclass(slots=True)
class _SentenceKeywordMatch:
    sentence: str
    keyword_count: int


_ClusterIndices = dict[int, list[int]]


class JDClusteringService:
    def __init__(
        self,
        write_versioned_output: bool = True,
        explicit_stopwords: Sequence[str] | None = None,
        min_cluster_size: int | None = None,
    ) -> None:
        if min_cluster_size is not None and min_cluster_size <= 0:
            raise ValueError("min_cluster_size must be greater than 0")

        self.write_versioned_output = write_versioned_output
        self.min_cluster_size = min_cluster_size
        self._nlp = self._load_nlp()
        self._dynamic_stopwords: set[str] = set()
        self._explicit_stopwords = self._normalize_stopword_terms(
            explicit_stopwords or []
        )
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
            print(
                "en_core_web_sm is not available. Falling back to spaCy blank English model."
            )
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
                if (
                    i + phrase_len <= len(tokens)
                    and tuple(tokens[i : i + phrase_len]) == phrase_tokens
                ):
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
            filtered_tokens = [
                token
                for token in item.processed_text.split()
                if token not in blocked_terms
            ]
            if blocked_terms is self._explicit_stopwords_unigrams:
                filtered_tokens = self._remove_phrase_stopwords(filtered_tokens)

            if not filtered_tokens:
                continue

            filtered_keywords = [
                lemma for lemma in item.keyword_lemmas if lemma not in blocked_terms
            ]
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

            processed_text, keyword_lemmas = self._extract_processed_and_keywords(
                raw_jd
            )
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

        explicit_filtered = self._filter_prepared(
            prepared, self._explicit_stopwords_unigrams
        )
        if not explicit_filtered:
            return []

        self._dynamic_stopwords = self._detect_dynamic_stopwords(explicit_filtered)
        if not self._dynamic_stopwords:
            return explicit_filtered

        return self._filter_prepared(explicit_filtered, self._dynamic_stopwords)

    def _detect_dynamic_stopwords(
        self, prepared: list[_PreparedOpportunity]
    ) -> set[str]:
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

    def _extract_ranked_keywords(
        self, cluster_items: list[_PreparedOpportunity]
    ) -> list[str]:
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

    def _split_sentences(self, text: str) -> list[str]:
        if not text:
            return []

        # Try spaCy sentence segmentation first.
        base_sentences: list[str] = []
        try:
            doc = self._nlp(text)
            base_sentences = [
                sent.text.strip()
                for sent in doc.sents
                if sent.text and sent.text.strip()
            ]
        except Exception:
            base_sentences = []

        if not base_sentences:
            base_sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

        refined_sentences: list[str] = []

        def split_overlong(sentence_text: str) -> list[str]:
            compact = " ".join(sentence_text.split())
            if not compact:
                return []

            if len(compact) <= 220 and len(compact.split()) <= 36:
                return [compact]

            primary_parts = [
                " ".join(part.split())
                for part in re.split(r"(?<=[,;:])\s+", compact)
                if part and part.strip()
            ]

            # If punctuation split is still too coarse, chunk by word count.
            output: list[str] = []
            for part in primary_parts or [compact]:
                words = part.split()
                if len(words) <= 36:
                    output.append(part)
                    continue

                chunk_size = 28
                for idx in range(0, len(words), chunk_size):
                    chunk = " ".join(words[idx : idx + chunk_size]).strip()
                    if chunk:
                        output.append(chunk)

            return output

        for sentence in base_sentences:
            if not sentence or not sentence.strip():
                continue

            normalized = " ".join(sentence.split())
            # Some scraped JDs are giant run-on blocks. Break those using heading/list transitions.
            if len(normalized) > 280 or len(normalized.split()) > 45:
                chunks = re.split(
                    r"(?:\n+|[•●▪◦]+\s*|\s+[\-–—]\s+|\s*;\s+|(?<=[a-z0-9\)])\s+(?=[A-Z][A-Za-z]{2,}\s+[A-Z][A-Za-z]{2,}))",
                    normalized,
                )
                for chunk in chunks:
                    chunk_normalized = " ".join(chunk.split())
                    if chunk_normalized:
                        refined_sentences.extend(split_overlong(chunk_normalized))
            else:
                refined_sentences.extend(split_overlong(normalized))

        return refined_sentences

    def _build_keyword_terms(
        self, keywords: list[str]
    ) -> tuple[set[str], set[tuple[str, ...]]]:
        unigram_terms: set[str] = set()
        phrase_terms: set[tuple[str, ...]] = set()
        for keyword in keywords:
            cleaned = " ".join(str(keyword).strip().lower().split())
            if not cleaned:
                continue
            tokens = tuple(cleaned.split())
            if len(tokens) == 1:
                unigram_terms.add(tokens[0])
            else:
                phrase_terms.add(tokens)

        return unigram_terms, phrase_terms

    def _keyword_matches_for_sentence(
        self,
        sentence: str,
        unigram_terms: set[str],
        phrase_terms: set[tuple[str, ...]],
    ) -> int:
        doc = self._nlp(sentence)
        tokens: list[str] = []
        for token in doc:
            normalized = self._normalize_lemma(token)
            if normalized:
                tokens.append(normalized)

        if not tokens:
            return 0

        matched: set[str] = set()

        for token in tokens:
            if token in unigram_terms:
                matched.add(token)

        if phrase_terms:
            token_count = len(tokens)
            for phrase in phrase_terms:
                phrase_len = len(phrase)
                for idx in range(0, token_count - phrase_len + 1):
                    if tuple(tokens[idx : idx + phrase_len]) == phrase:
                        matched.add(" ".join(phrase))
                        break

        return len(matched)

    def _extract_keyword_sentences(
        self,
        cluster_items: list[_PreparedOpportunity],
        keywords: list[str],
        limit: int = 20,
    ) -> list[str]:
        if not cluster_items or not keywords:
            return []

        unigram_terms, phrase_terms = self._build_keyword_terms(keywords)
        if not unigram_terms and not phrase_terms:
            return []

        sentence_best_matches: dict[str, _SentenceKeywordMatch] = {}
        for item in cluster_items:
            jd_text = (item.opportunity.job_description or "").strip()
            if not jd_text:
                continue

            for sentence in self._split_sentences(jd_text):
                keyword_count = self._keyword_matches_for_sentence(
                    sentence,
                    unigram_terms,
                    phrase_terms,
                )
                if keyword_count <= 0:
                    continue

                normalized_sentence = " ".join(sentence.split())
                match = _SentenceKeywordMatch(
                    sentence=normalized_sentence,
                    keyword_count=keyword_count,
                )
                existing = sentence_best_matches.get(normalized_sentence)
                if not existing or match.keyword_count > existing.keyword_count:
                    sentence_best_matches[normalized_sentence] = match

        ranked_matches = sorted(
            sentence_best_matches.values(),
            key=lambda value: (value.keyword_count, len(value.sentence)),
            reverse=True,
        )

        return [match.sentence for match in ranked_matches[:limit]]

    def _resolve_min_cluster_size(self, sample_count: int) -> int:
        if sample_count <= 1:
            return 1

        if self.min_cluster_size is not None:
            return min(sample_count, max(2, self.min_cluster_size))

        # Adaptive default: at least 3 members, about 5% of samples on larger datasets.
        return min(sample_count, max(3, math.ceil(sample_count * 0.05)))

    def _build_threshold_candidates(
        self, merge_distances: list[float], max_candidates: int = 30
    ) -> list[float]:
        if not merge_distances:
            return []

        if len(merge_distances) <= max_candidates:
            return merge_distances

        step = max(1, len(merge_distances) // max_candidates)
        return merge_distances[::step][:max_candidates]

    def _fit_labels_for_threshold(self, dense_matrix, threshold: float):
        return AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=threshold,
            metric="cosine",
            linkage="average",
        ).fit_predict(dense_matrix)

    def _score_natural_candidate(
        self,
        labels_array,
        tfidf_matrix,
        sample_count: int,
        min_cluster_size: int,
    ) -> tuple[float, int] | None:
        discovered_k = len(set(labels_array))
        if discovered_k < 2 or discovered_k >= sample_count:
            return None

        cluster_sizes = list(Counter(labels_array).values())
        if all(size < min_cluster_size for size in cluster_sizes):
            return None

        silhouette = silhouette_score(tfidf_matrix, labels_array, metric="cosine")
        largest_share = max(cluster_sizes) / sample_count
        tiny_share = (
            sum(size for size in cluster_sizes if size < min_cluster_size)
            / sample_count
        )

        # Penalize dominant and tiny-fragment-heavy solutions for tighter cluster focus.
        score = silhouette - (0.35 * largest_share) - (0.20 * tiny_share)
        return score, discovered_k

    def _find_natural_labels(
        self,
        tfidf_matrix,
        dense_matrix,
        sample_count: int,
        min_cluster_size: int,
    ) -> tuple[list[int], int, float | None]:
        if sample_count <= 2:
            return [0] * sample_count, 1, None

        base_model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=0.0,
            metric="cosine",
            linkage="average",
            compute_distances=True,
        ).fit(dense_matrix)

        merge_distances = sorted(
            {float(distance) for distance in base_model.distances_ if distance > 0}
        )
        if not merge_distances:
            return [0] * sample_count, 1, None

        candidate_thresholds = self._build_threshold_candidates(merge_distances)

        best_labels: list[int] = [0] * sample_count
        best_k = 1
        best_threshold: float | None = None
        best_score = float("-inf")

        for threshold in candidate_thresholds:
            labels_array = self._fit_labels_for_threshold(dense_matrix, threshold)

            score_and_k = self._score_natural_candidate(
                labels_array=labels_array,
                tfidf_matrix=tfidf_matrix,
                sample_count=sample_count,
                min_cluster_size=min_cluster_size,
            )
            if score_and_k is None:
                continue

            score, discovered_k = score_and_k
            if score > best_score:
                best_score = score
                best_labels = [int(label) for label in labels_array]
                best_k = discovered_k
                best_threshold = threshold

        return best_labels, best_k, best_threshold

    def _split_clusters_by_size(
        self,
        clusters: _ClusterIndices,
        min_cluster_size: int,
    ) -> tuple[list[int], list[int]]:
        major_cluster_ids: list[int] = []
        tiny_cluster_ids: list[int] = []
        for cluster_id, members in clusters.items():
            if len(members) >= min_cluster_size:
                major_cluster_ids.append(cluster_id)
            else:
                tiny_cluster_ids.append(cluster_id)

        return major_cluster_ids, tiny_cluster_ids

    def _build_cluster_centroids(
        self,
        clusters: _ClusterIndices,
        dense_matrix,
        allowed_cluster_ids: set[int],
    ) -> dict[int, Any]:
        return {
            cluster_id: dense_matrix[members].mean(axis=0)
            for cluster_id, members in clusters.items()
            if cluster_id in allowed_cluster_ids
        }

    def _nearest_cluster_id(
        self,
        sample_vector,
        major_cluster_ids: list[int],
        major_centroids: dict[int, Any],
    ) -> int:
        centroid_vectors = [
            major_centroids[cluster_id] for cluster_id in major_cluster_ids
        ]
        distances = cosine_distances([sample_vector], centroid_vectors)[0]
        nearest_idx = min(range(len(distances)), key=lambda idx: distances[idx])
        return major_cluster_ids[nearest_idx]

    def _reassign_tiny_clusters(
        self,
        labels: list[int],
        dense_matrix,
        min_cluster_size: int,
    ) -> tuple[list[int], int]:
        if not labels:
            return labels, 0

        clusters = self._group_cluster_indices(labels)
        major_cluster_ids, tiny_cluster_ids = self._split_clusters_by_size(
            clusters, min_cluster_size
        )
        if not tiny_cluster_ids or not major_cluster_ids:
            return labels, 0

        major_centroids = self._build_cluster_centroids(
            clusters=clusters,
            dense_matrix=dense_matrix,
            allowed_cluster_ids=set(major_cluster_ids),
        )

        reassigned_labels = list(labels)
        reassigned_count = 0
        for tiny_cluster_id in tiny_cluster_ids:
            for sample_idx in clusters[tiny_cluster_id]:
                sample_vector = dense_matrix[sample_idx]
                reassigned_labels[sample_idx] = self._nearest_cluster_id(
                    sample_vector=sample_vector,
                    major_cluster_ids=major_cluster_ids,
                    major_centroids=major_centroids,
                )
                reassigned_count += 1

        return reassigned_labels, reassigned_count

    def _group_cluster_indices(self, labels) -> _ClusterIndices:
        clusters: _ClusterIndices = {}
        for idx, cluster_id in enumerate(labels):
            clusters.setdefault(int(cluster_id), []).append(idx)
        return clusters

    def _serialize_opportunity(self, opportunity: Opportunity) -> dict[str, str | None]:
        return {
            "id": str(opportunity.id),
            "designation": opportunity.designation,
            "company_name": opportunity.company_name,
            "url": opportunity.source_url,
        }

    def _build_cluster_record(
        self, cluster_id: int, cluster_items: list[_PreparedOpportunity]
    ) -> dict:
        opportunities = [item.opportunity for item in cluster_items]
        keywords = self._extract_ranked_keywords(cluster_items)
        return {
            "cluster_id": cluster_id,
            "total_opportunities": len(opportunities),
            "keywords": keywords,
            "keyword_sentences": self._extract_keyword_sentences(
                cluster_items, keywords
            ),
            "opportunities": [
                self._serialize_opportunity(opportunity)
                for opportunity in opportunities
            ],
        }

    def _build_cluster_payload(
        self,
        prepared: list[_PreparedOpportunity],
        clusters: _ClusterIndices,
    ) -> list[dict]:
        cluster_ids = sorted(
            clusters,
            key=lambda cluster_id: len(clusters[cluster_id]),
            reverse=True,
        )

        payload: list[dict] = []
        for cluster_id in cluster_ids:
            cluster_items = [prepared[i] for i in clusters[cluster_id]]
            payload.append(self._build_cluster_record(cluster_id, cluster_items))

        return payload

    def _build_cluster_result(
        self,
        prepared: list[_PreparedOpportunity],
        clusters: _ClusterIndices,
        natural_discovered_k: int,
        selected_distance_threshold: float | None,
        min_cluster_size: int,
        reassigned_opportunities: int,
    ) -> dict:
        discovered_k = len(clusters)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "discovered_k": discovered_k,
            "natural_discovered_k": natural_discovered_k,
            "selected_distance_threshold": selected_distance_threshold,
            "min_cluster_size": min_cluster_size,
            "reassigned_opportunities": reassigned_opportunities,
            "dynamic_stopwords": sorted(self._dynamic_stopwords),
            "explicit_stopwords": sorted(self._explicit_stopwords),
            "clusters": self._build_cluster_payload(prepared, clusters),
        }

    def cluster(self) -> dict:
        prepared = self._prepare_opportunities()
        if not prepared:
            raise ValueError(
                "No opportunities with usable job descriptions were found."
            )

        processed_corpus = [item.processed_text for item in prepared]
        tfidf_matrix = TfidfVectorizer(ngram_range=(1, 3), max_df=0.9).fit_transform(
            processed_corpus
        )
        dense_matrix = tfidf_matrix.toarray()
        sample_count = len(prepared)
        min_cluster_size = self._resolve_min_cluster_size(sample_count)
        labels, natural_discovered_k, selected_distance_threshold = (
            self._find_natural_labels(
                tfidf_matrix,
                dense_matrix,
                sample_count,
                min_cluster_size,
            )
        )
        labels, reassigned_opportunities = self._reassign_tiny_clusters(
            labels,
            dense_matrix,
            min_cluster_size,
        )
        clusters = self._group_cluster_indices(labels)

        return self._build_cluster_result(
            prepared=prepared,
            clusters=clusters,
            natural_discovered_k=natural_discovered_k,
            selected_distance_threshold=selected_distance_threshold,
            min_cluster_size=min_cluster_size,
            reassigned_opportunities=reassigned_opportunities,
        )

    def save_clusters(self, cluster_result: dict) -> dict[str, str]:
        PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CLUSTERS_FILE, "w", encoding="utf-8") as file:
            json.dump(cluster_result, file, indent=4)

        saved_files: dict[str, str] = {"latest": str(_CLUSTERS_FILE)}
        if self.write_versioned_output:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            versioned_path = PROJECT_DATA_DIR.joinpath(f"clusters_{timestamp}.json")
            with open(versioned_path, "w", encoding="utf-8") as file:
                json.dump(cluster_result, file, indent=4)
            saved_files["versioned"] = str(versioned_path)

        return saved_files

    def run_and_save(self) -> dict[str, str]:
        return self.save_clusters(self.cluster())
