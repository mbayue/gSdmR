import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { Provider, ProviderCreate, ProviderUpdate } from '../types'

export const providerKeys = {
  all: ['providers'] as const,
  list: () => [...providerKeys.all, 'list'] as const,
  models: (id: number) => [...providerKeys.all, id, 'models'] as const,
}

export function useProviders() {
  return useQuery({
    queryKey: providerKeys.list(),
    queryFn: async () => {
      const res = await apiClient.get('/api/providers')
      return res.data as Provider[]
    },
  })
}

export function useProviderModels(providerId: number) {
  return useQuery({
    queryKey: providerKeys.models(providerId),
    queryFn: async () => {
      const res = await apiClient.get(`/api/providers/${providerId}/models`)
      return Array.isArray(res.data) ? res.data : res.data.models ?? []
    },
    enabled: providerId > 0,
  })
}

export function useCreateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProviderCreate) => apiClient.post('/api/providers', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: providerKeys.list() }),
  })
}

export function useUpdateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ProviderUpdate }) => apiClient.put(`/api/providers/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: providerKeys.list() }),
  })
}

export function useDeleteProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/providers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: providerKeys.list() }),
  })
}
