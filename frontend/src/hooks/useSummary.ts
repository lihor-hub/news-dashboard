import { useQuery } from '@tanstack/react-query';
import { fetchSummary } from '../api';

export function useSummary() {
  return useQuery({
    queryKey: ['summary'],
    queryFn: fetchSummary,
    refetchInterval: 60_000,
  });
}
