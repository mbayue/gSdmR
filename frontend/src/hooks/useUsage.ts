import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

export interface UsageSummary {
  total_requests: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  avg_latency_ms: number
  successful: number
  failed: number
}

export interface UsageByModel {
  model: string
  requests: number
  tokens: number
  avg_latency_ms: number
}

export interface UsageByKey {
  key_id: number
  key_name: string
  requests: number
  tokens: number
}

export interface UsageRecent {
  model: string
  provider: string | null
  endpoint: string
  status: number
  latency_ms: number
  tokens: number
  time: string
}

export interface UsageStats {
  period_days: number
  summary: UsageSummary
  by_model: UsageByModel[]
  by_key: UsageByKey[]
  recent: UsageRecent[]
}

export function useUsageStats(days: number = 7) {
  return useQuery({
    queryKey: ['usage', days],
    queryFn: async () => {
      const res = await apiClient.get(`/api/usage?days=${days}`)
      return res.data as UsageStats
    },
    refetchInterval: 30000, // refresh every 30s
  })
}
