import { useState, useEffect } from 'react';
import apiClient from '../api/client';
import type { Model } from '../types';

interface ApiKey {
  id: number;
  name: string;
  key_preview: string;
  key_value?: string; // only on create
  is_active: boolean;
  allowed_models: { id: number; name: string }[];
  created_at: string;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([]);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [error, setError] = useState('');

  const fetchKeys = async () => {
    const res = await apiClient.get('/api/keys');
    setKeys(res.data);
  };

  const fetchModels = async () => {
    const res = await apiClient.get('/api/models');
    setModels(res.data);
  };

  useEffect(() => {
    fetchKeys();
    fetchModels();
  }, []);

  const handleCreate = async () => {
    setError('');
    if (!newKeyName.trim()) {
      setError('Name is required');
      return;
    }
    try {
      const res = await apiClient.post('/api/keys', {
        name: newKeyName,
        model_ids: selectedModelIds,
      });
      setCreatedKey(res.data.key_value);
      setNewKeyName('');
      setSelectedModelIds([]);
      fetchKeys();
    } catch {
      setError('Error creating key');
    }
  };

  const handleToggle = async (key: ApiKey) => {
    await apiClient.put(`/api/keys/${key.id}`, { is_active: !key.is_active });
    fetchKeys();
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this API key?')) return;
    await apiClient.delete(`/api/keys/${id}`);
    fetchKeys();
  };

  const toggleModel = (modelId: number) => {
    setSelectedModelIds((prev) =>
      prev.includes(modelId) ? prev.filter((id) => id !== modelId) : [...prev, modelId]
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>API Keys</h2>
        <button onClick={() => { setShowForm(!showForm); setCreatedKey(null); }} style={{ padding: '8px 16px', cursor: 'pointer' }}>
          {showForm ? 'Close' : 'Generate New Key'}
        </button>
      </div>

      {showForm && (
        <div style={{ padding: 16, marginBottom: 16, border: '1px solid #ddd', borderRadius: 8 }}>
          <h3>Generate API Key</h3>
          {error && <p style={{ color: 'red' }}>{error}</p>}

          {createdKey && (
            <div style={{ padding: 12, marginBottom: 12, background: '#e8f5e9', borderRadius: 4, border: '1px solid #a5d6a7' }}>
              <p style={{ margin: 0, fontWeight: 'bold' }}>Key created! Copy it now — it won't be shown again:</p>
              <code style={{ display: 'block', marginTop: 8, padding: 8, background: '#fff', borderRadius: 4, wordBreak: 'break-all' }}>
                {createdKey}
              </code>
            </div>
          )}

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Key Name</label>
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="e.g., Production, Testing, User-A"
              style={{ width: '100%', padding: 8, boxSizing: 'border-box' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>
              Model Restrictions <span style={{ color: '#888', fontSize: 12 }}>(none selected = all models allowed)</span>
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {models.map((m) => (
                <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', background: selectedModelIds.includes(m.id) ? '#e3f2fd' : '#f5f5f5', borderRadius: 4, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={selectedModelIds.includes(m.id)}
                    onChange={() => toggleModel(m.id)}
                  />
                  {m.name}
                </label>
              ))}
              {models.length === 0 && <span style={{ color: '#888' }}>No models configured yet</span>}
            </div>
          </div>

          <button onClick={handleCreate} style={{ padding: '8px 16px', cursor: 'pointer' }}>
            Generate Key
          </button>
        </div>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
            <th style={{ padding: 8 }}>Name</th>
            <th style={{ padding: 8 }}>Key</th>
            <th style={{ padding: 8 }}>Models</th>
            <th style={{ padding: 8 }}>Active</th>
            <th style={{ padding: 8 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: 8 }}>{k.name}</td>
              <td style={{ padding: 8, fontFamily: 'monospace', fontSize: 12 }}>{k.key_preview}</td>
              <td style={{ padding: 8, fontSize: 13 }}>
                {k.allowed_models.length === 0
                  ? <span style={{ color: '#888' }}>All</span>
                  : k.allowed_models.map((m) => m.name).join(', ')}
              </td>
              <td style={{ padding: 8 }}>
                <button onClick={() => handleToggle(k)} style={{ cursor: 'pointer', color: k.is_active ? 'green' : 'red' }}>
                  {k.is_active ? '✓ Active' : '✗ Disabled'}
                </button>
              </td>
              <td style={{ padding: 8 }}>
                <button onClick={() => handleDelete(k.id)} style={{ cursor: 'pointer', color: 'red' }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
