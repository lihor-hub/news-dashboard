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


class LessonCreateRequest(BaseModel):
    url: str


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
