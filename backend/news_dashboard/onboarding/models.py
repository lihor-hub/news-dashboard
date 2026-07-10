"""Request models for the onboarding feature module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingInterestsRequest(BaseModel):
    interests: list[str]
    enabled_source_slugs: list[str] = Field(default_factory=list)
    disabled_source_slugs: list[str] = Field(default_factory=list)
    completed: bool = True


class OnboardingRecommendationsRequest(BaseModel):
    interest_ids: list[str]


class OnboardingProfileRequest(BaseModel):
    interest_ids: list[str]
    enabled_slugs: list[str] = Field(default_factory=list)
