import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { PlaygroundTestResult, DisabledProviderModel } from '../types'

export const playgroundKeys = {
  all: ['playground'] as const,
  disabledModels: () => [...playgroundKeys.all, 'disabled-models'] as const,
}

export function useDisabledModels() {
  return useQuery({
    queryKey: playgroundKeys.disabledModels(),
    queryFn: async () => {
      const res = await apiClient.get('/api/playground/disabled-models')
      return res.data as DisabledProviderModel[]
    },
  })
}

export function useTestModel() {
  return useMutation({
    mutationFn: async (data: { provider_id: number; model_name: string }) => {
      const res = await apiClient.post('/api/playground/test', data)
      return res.data as PlaygroundTestResult
    },
  })
}

export function useRouteTest() {
  return useMutation({
    mutationFn: async (data: { model_name: string }) => {
      const res = await apiClient.post('/api/playground/route-test', data)
      return res.data as PlaygroundTestResult
    },
  })
}

export function useDeactivateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: { provider_id: number; model_name: string }) => {
      const res = await apiClient.post('/api/playground/disabled-models', data)
      return res.data as DisabledProviderModel
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: playgroundKeys.disabledModels() }),
  })
}

export function useActivateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: { provider_id: number; model_name: string }) => {
      await apiClient.delete('/api/playground/disabled-models', { data })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: playgroundKeys.disabledModels() }),
  })
}
