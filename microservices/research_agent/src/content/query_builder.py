class ContentSearchQuery:
    """بناء استعلام SQL للبحث في المحتوى."""

    def __init__(self) -> None:
        self.select_clause = (
            "SELECT i.id, i.title, i.type, i.level, i.subject, i.branch, "
            "i.set_name, i.year, i.lang, i.md_content "
        )
        self.from_clause = (
            "FROM content_items i LEFT JOIN content_search cs ON i.id = cs.content_id"
        )
        self.where_clauses: list[str] = ["1=1"]
        self.order_clause = "ORDER BY i.year DESC NULLS LAST, i.id ASC"
        self.limit_clause = ""
        self.params: dict[str, object] = {}
        self._search_terms: list[str] = []

    def add_text_search(self, q: str | None) -> "ContentSearchQuery":
        if not q:
            return self
        terms = [term for term in q.split() if term.strip()]
        self._search_terms = terms
        term_clauses: list[str] = []
        for index, term in enumerate(terms):
            title_key = f"tq_{index}"
            body_key = f"bq_{index}"
            term_clauses.append(f"(i.title LIKE :{title_key} OR cs.plain_text LIKE :{body_key})")
            like_value = f"%{term}%"
            self.params[title_key] = like_value
            self.params[body_key] = like_value

        if term_clauses:
            self.where_clauses.append(" AND ".join(term_clauses))
        return self

    def add_id_filter(self, content_ids: list[str] | None) -> "ContentSearchQuery":
        if not content_ids:
            return self
        placeholders: list[str] = []
        for index, content_id in enumerate(content_ids):
            key = f"cid_{index}"
            placeholders.append(f":{key}")
            self.params[key] = content_id
        self.where_clauses.append(f"i.id IN ({', '.join(placeholders)})")
        return self

    def add_filter(self, field: str, value: object) -> "ContentSearchQuery":
        if value is not None:
            key = field.rsplit(".", maxsplit=1)[-1]  # Simple key generation
            # Avoid collision if field is used multiple times (unlikely here but safe practice)
            if key in self.params:
                key = f"{key}_{len(self.params)}"

            self.where_clauses.append(f"{field} = :{key}")
            self.params[key] = value
        return self

    def set_limit(self, limit: int) -> "ContentSearchQuery":
        self.limit_clause = "LIMIT :limit"
        self.params["limit"] = limit
        return self

    def set_order_by_vector_ids(self, content_ids: list[str]) -> "ContentSearchQuery":
        if not content_ids:
            return self
        rank_clauses: list[str] = []
        for index, content_id in enumerate(content_ids):
            rank_key = f"rank_id_{index}"
            rank_clauses.append(f"WHEN :{rank_key} THEN {index}")
            self.params[rank_key] = content_id
        self.order_clause = (
            f"ORDER BY CASE i.id {' '.join(rank_clauses)} ELSE {len(content_ids)} END, i.id ASC"
        )
        return self

    def set_order_by_text_relevance(self) -> "ContentSearchQuery":
        if not self._search_terms:
            return self

        title_relevance_terms: list[str] = []
        body_relevance_terms: list[str] = []
        for index, _ in enumerate(self._search_terms):
            title_key = f"tq_{index}"
            body_key = f"bq_{index}"
            title_relevance_terms.append(f"CASE WHEN i.title LIKE :{title_key} THEN 1 ELSE 0 END")
            body_relevance_terms.append(
                f"CASE WHEN cs.plain_text LIKE :{body_key} THEN 1 ELSE 0 END"
            )

        title_score = " + ".join(title_relevance_terms) if title_relevance_terms else "0"
        body_score = " + ".join(body_relevance_terms) if body_relevance_terms else "0"
        self.order_clause = f"ORDER BY ({title_score} + {body_score}) DESC, i.id ASC"
        return self

    def build(self) -> tuple[str, dict[str, object]]:
        where_str = " AND ".join(self.where_clauses)
        query = f"{self.select_clause} {self.from_clause} WHERE {where_str} {self.order_clause} {self.limit_clause}"
        return query, self.params
