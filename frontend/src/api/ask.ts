import type { AgentActionPlanResponse, AgentActionRun, AskResponse } from '../types';
import { requestJson } from './core';

export async function askAI(
  query: string,
  includeAll = false,
  sessionId?: string
): Promise<AskResponse> {
  return requestJson<AskResponse>('/api/ask', {
    method: 'POST',
    body: JSON.stringify({ query, include_all: includeAll, session_id: sessionId }),
  });
}

export async function planAgentActions(query: string): Promise<AgentActionPlanResponse> {
  return requestJson<AgentActionPlanResponse>('/api/agent/actions/plan', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export async function approveAgentActionRun(runId: number): Promise<AgentActionRun> {
  return requestJson<AgentActionRun>(`/api/agent/actions/${runId}/approve`, { method: 'POST' });
}

export async function cancelAgentActionRun(runId: number): Promise<AgentActionRun> {
  return requestJson<AgentActionRun>(`/api/agent/actions/${runId}/cancel`, { method: 'POST' });
}

export async function submitFeedback(
  traceId: string,
  helpful: boolean,
  comment?: string
): Promise<{ recorded: boolean }> {
  return requestJson<{ recorded: boolean }>('/api/feedback', {
    method: 'POST',
    body: JSON.stringify({ trace_id: traceId, helpful, comment }),
  });
}
