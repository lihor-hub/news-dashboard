"""Request models for Learn from Link lessons."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GistText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=280)]
QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
]

MAX_LESSON_CHAT_HISTORY_ITEMS = 50

LessonDepth = Literal["tiny", "normal", "deep", "expert"]
LessonPersona = Literal["developer", "product_builder", "new_to_ai", "preparing_talk"]


class LessonCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    depth: LessonDepth = "normal"
    persona: LessonPersona = "developer"


class LessonRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depth: LessonDepth = "normal"
    persona: LessonPersona = "developer"


class LessonChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: QuestionText


class LessonQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: QuestionText
    history: list[LessonChatMessage] = Field(
        default_factory=list, max_length=MAX_LESSON_CHAT_HISTORY_ITEMS
    )


class LessonCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: NonEmptyText
    snippet: NonEmptyText
    source: NonEmptyText


class LessonGraphEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonEmptyText
    name: NonEmptyText
    type: Literal["concept", "person", "org", "product", "place"]


class LessonGraphRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: NonEmptyText
    target: NonEmptyText
    relationship_type: NonEmptyText
    label: NonEmptyText
    confidence: float = Field(ge=0.0, le=1.0)


class LessonGraphContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    entities: list[LessonGraphEntity] = Field(default_factory=list)
    relationships: list[LessonGraphRelationship] = Field(default_factory=list)
    related_article_ids: list[int] = Field(default_factory=list)
    related_briefing_ids: list[int] = Field(default_factory=list)


class ReadWorthiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["skip", "skim", "read", "study"]
    rationale: NonEmptyText


class LessonDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gist: GistText
    explanation: NonEmptyText
    key_claims: list[NonEmptyText] = Field(min_length=1)
    prerequisite_concepts: list[NonEmptyText] = Field(min_length=1)
    why_it_matters: NonEmptyText
    read_worthiness: ReadWorthiness
    who_should_read: list[NonEmptyText] = Field(min_length=1)
    questions_to_keep_in_mind: list[NonEmptyText] = Field(min_length=1)
    citations: list[LessonCitation] = Field(min_length=1)
    graph_context: LessonGraphContext | None = None


class ComprehensionQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyText
    expected_answer: NonEmptyText


class Flashcard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: NonEmptyText
    claim: NonEmptyText


class QuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyText
    options: list[NonEmptyText] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: NonEmptyText


class StudyArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comprehension_questions: list[ComprehensionQuestion] = Field(min_length=1)
    flashcards: list[Flashcard] = Field(min_length=1)
    quiz: list[QuizQuestion] = Field(min_length=1)


class PersonalRelevance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: NonEmptyText
    signals: list[NonEmptyText] = Field(default_factory=list)


class Slide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonEmptyText
    bullets: list[NonEmptyText] = Field(min_length=1, max_length=6)


class SlideDeck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slides: list[Slide] = Field(min_length=6, max_length=10)


class InfographicSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: NonEmptyText
    body: NonEmptyText


class InfographicArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonEmptyText
    subtitle: NonEmptyText
    sections: list[InfographicSection] = Field(min_length=3, max_length=6)
    footer: NonEmptyText


class RelevanceFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    helpful: bool


class LessonSuggestionDismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: int


class LessonTrailItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: Literal["lesson", "article"]
    id: int
    title: NonEmptyText
    url: str | None = None
    source_name: str | None = None
    explanation: NonEmptyText
    matched_signals: list[NonEmptyText] = Field(default_factory=list)


class LessonTrailGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Literal["prerequisite", "easier", "adjacent", "deeper"]
    label: NonEmptyText
    items: list[LessonTrailItem] = Field(default_factory=list)


class LessonTrailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: int
    groups: list[LessonTrailGroup]
    empty_message: str | None = None
