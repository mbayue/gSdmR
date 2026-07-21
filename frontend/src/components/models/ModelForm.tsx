import { useState, useEffect, FormEvent } from 'react';
import apiClient from '../../api/client';
import type { Model, Provider, ModelProviderMapping } from '../../types';

interface Props {
  model: Model | null;
  onClose: () => void;
}

interface AvailableModel {
  id: string;
}

export default function ModelForm({ model, onClose }: Props) {
  const [name, setName] = useState(model?.name ?? '');
  const [mappings, setMappings] = useState<ModelProviderMapping[]>(
    model?.providers ?? [{ provider_id: 0, provider_model: '', priority: 1 }]
  );
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerModels, setProviderModels] = useState<Record<number, AvailableModel[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<number, boolean>>({});
  const [error, setError] = useState('');

  const isEditing = !!model;

  useEffect(() => {
    apiClient.get('/api/providers').then((res) => setProviders(res.data));
  }, []);

  const fetchModelsForProvider = async (providerId: number) => {
    if (providerId <= 0 || providerModels[providerId]) return;
    setLoadingModels((prev) => ({ ...prev, [providerId]: true }));
    try {
      const res = await apiClient.get(`/api/providers/${providerId}/models`);
      const data = res.data;
      const models = Array.isArray(data) ? data : data.models ?? [];
      setProviderModels((prev) => ({ ...prev, [providerId]: models }));
    } catch {
      setProviderModels((prev) => ({ ...prev, [providerId]: [] }));
    } finally {
      setLoadingModels((prev) => ({ ...prev, [providerId]: false }));
    }
  };

  // Fetch models for pre-selected providers on mount
  useEffect(() => {
    for (const m of mappings) {
      if (m.provider_id > 0) fetchModelsForProvider(m.provider_id);
    }
  }, []);

  const addMapping = () => {
    const nextPriority = mappings.length > 0 ? Math.max(...mappings.map((m) => m.priority)) + 1 : 1;
    setMappings([...mappings, { provider_id: 0, provider_model: '', priority: nextPriority }]);
  };

  const removeMapping = (index: number) => {
    setMappings(mappings.filter((_, i) => i !== index));
  };

  const updateMappingProvider = (index: number, providerId: number) => {
    const updated = [...mappings];
    updated[index] = { ...updated[index], provider_id: providerId, provider_model: '' };
    setMappings(updated);
    if (providerId > 0) fetchModelsForProvider(providerId);
  };

  const updateMappingModel = (index: number, providerModel: string) => {
    const updated = [...mappings];
    updated[index] = { ...updated[index], provider_model: providerModel };
    setMappings(updated);
  };

  const updateMappingPriority = (index: number, priority: number) => {
    const updated = [...mappings];
    updated[index] = { ...updated[index], priority };
    setMappings(updated);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Model name is required');
      return;
    }

    const validMappings = mappings.filter((m) => m.provider_id > 0 && m.provider_model.trim() !== '');
    if (validMappings.length === 0) {
      setError('At least one provider with a model selection is required');
      return;
    }

    try {
      if (isEditing) {
        await apiClient.put(`/api/models/${model.id}`, {
          name,
          providers: validMappings.map((m) => ({
            provider_id: m.provider_id,
            provider_model: m.provider_model,
            priority: m.priority,
          })),
        });
      } else {
        await apiClient.post('/api/models', {
          name,
          providers: validMappings.map((m) => ({
            provider_id: m.provider_id,
            provider_model: m.provider_model,
            priority: m.priority,
          })),
        });
      }
      onClose();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail ?? 'Error saving model');
      } else {
        setError('Error saving model');
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ padding: 16, marginBottom: 16, border: '1px solid #ddd', borderRadius: 8 }}>
      <h3>{isEditing ? 'Edit Model' : 'Add Model'}</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {/* Model Name on top */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>Model Name (your custom alias)</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="e.g., my-gpt4, fast-claude, etc."
          style={{ width: '100%', padding: 8, boxSizing: 'border-box' }}
        />
      </div>

      {/* Provider + Model mappings */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>Provider Routes</label>
        <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
          Select which provider and model to route to. Priority 1 = tried first.
        </div>
        {mappings.map((mapping, index) => (
          <div key={index} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            {/* Provider select */}
            <select
              value={mapping.provider_id}
              onChange={(e) => updateMappingProvider(index, Number(e.target.value))}
              style={{ flex: 1, padding: 8 }}
            >
              <option value={0}>Provider...</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>

            {/* Model select */}
            <select
              value={mapping.provider_model}
              onChange={(e) => updateMappingModel(index, e.target.value)}
              style={{ flex: 1, padding: 8 }}
              disabled={mapping.provider_id <= 0}
            >
              <option value="">
                {mapping.provider_id <= 0
                  ? 'Select provider first'
                  : loadingModels[mapping.provider_id]
                    ? 'Loading...'
                    : 'Select model...'}
              </option>
              {(providerModels[mapping.provider_id] ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.id}</option>
              ))}
            </select>

            {/* Priority */}
            <input
              type="number"
              min={1}
              value={mapping.priority}
              onChange={(e) => updateMappingPriority(index, Number(e.target.value))}
              style={{ width: 60, padding: 8 }}
              title="Priority"
            />

            {mappings.length > 1 && (
              <button type="button" onClick={() => removeMapping(index)} style={{ cursor: 'pointer', color: 'red' }}>✗</button>
            )}
          </div>
        ))}
        <button type="button" onClick={addMapping} style={{ cursor: 'pointer', fontSize: 13 }}>
          + Add Route
        </button>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" style={{ padding: '8px 16px', cursor: 'pointer' }}>Save</button>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', cursor: 'pointer' }}>Cancel</button>
      </div>
    </form>
  );
}
