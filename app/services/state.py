from __future__ import annotations

from pathlib import Path

from app.schemas.review import KnowledgeBaseState


class StateStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> KnowledgeBaseState | None:
        if not self.path.exists():
            return None
        return KnowledgeBaseState.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, state: KnowledgeBaseState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
