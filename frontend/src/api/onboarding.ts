import type {
  OnboardingInterest,
  OnboardingSourceRecommendation,
  OnboardingStatus,
  SaveOnboardingInterestsRequest,
} from '../types';
import { requestJson } from './core';

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  return requestJson<OnboardingStatus>('/api/onboarding/status');
}

export async function fetchOnboardingInterests(): Promise<OnboardingInterest[]> {
  return requestJson<OnboardingInterest[]>('/api/onboarding/interests');
}

export async function fetchOnboardingSourceRecommendations(
  interestIds: string[]
): Promise<OnboardingSourceRecommendation[]> {
  return requestJson<OnboardingSourceRecommendation[]>('/api/onboarding/recommendations', {
    method: 'POST',
    body: JSON.stringify({ interest_ids: interestIds }),
  });
}

export async function saveOnboardingInterests(
  payload: SaveOnboardingInterestsRequest
): Promise<void> {
  await requestJson('/api/onboarding/interests', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
