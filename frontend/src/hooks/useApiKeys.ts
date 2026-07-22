import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { Model } from '../types'

export interface ApiKey {
  id: number
  name: string
  key_preview: string
  key_value?: string
  is_active: boolean
  allowed_models: { id: number; name: string }[]
  created_at: string
}

export interface ApiKeyCreate {
  name: string
  model_ids: number[]
}

export const apiKeyKeys = {
  all: ['api-keys'] as const,
  list: () => [...apiKeyKeys.all, 'list'] as const,
}

export function useApiKeys() {
  return useQuery({
    queryKey: apiKeyKeys.list(),
    queryFn: async () => {
      const res = await apiClient.get('/api/keys')
      return res.data as ApiKey[]
    },
  })
}

export function useAvailableModels() {
  return useQuery({
    queryKey: ['models', 'list'],
    queryFn: async () => {
      const res = await apiClient.get('/api/models')
      return res.data as Model[]
    },
  })
}

export function useCreateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: ApiKeyCreate) => {
      const res = await apiClient.post('/api/keys', data)
      return res.data as ApiKey & { key_value: string }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.list() }),
  })
}

export function useToggleApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiClient.put(`/api/keys/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.list() }),
  })
}

export interface ApiKeyUpdate {
  name?: string
  model_ids?: number[]
  rate_limit?: number
}

export function useUpdateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ApiKeyUpdate }) =>
      apiClient.put(`/api/keys/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.list() }),
  })
}

export function useDeleteApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/keys/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.list() }),
  })
}
