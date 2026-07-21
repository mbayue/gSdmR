import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { Model, ModelCreate, ModelUpdate } from '../types'

export const modelKeys = {
  all: ['models'] as const,
  list: () => [...modelKeys.all, 'list'] as const,
}

export function useModels() {
  return useQuery({
    queryKey: modelKeys.list(),
    queryFn: async () => {
      const res = await apiClient.get('/api/models')
      return res.data as Model[]
    },
  })
}

export function useCreateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ModelCreate) => apiClient.post('/api/models', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.list() }),
  })
}

export function useUpdateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ModelUpdate }) => apiClient.put(`/api/models/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.list() }),
  })
}

export function useDeleteModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/models/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.list() }),
  })
}
