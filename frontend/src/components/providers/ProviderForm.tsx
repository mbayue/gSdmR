import { useState, FormEvent } from 'react';
import apiClient from '../../api/client';
import type { Provider } from '../../types';

interface Props {
  provider: Provider | null;
  onClose: () => void;
}

export default function ProviderForm({ provider, onClose }: Props) {
  const [name, setName] = useState(provider?.name ?? '');
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? '');
  const [apiKey, setApiKey] = useState('');
  const [isActive, setIsActive] = useState(provider?.is_active ?? true);
  const [error, setError] = useState('');

  const isEditing = !!provider;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      if (isEditing) {
        const update: Record<string, unknown> = {};
        if (name !== provider.name) update.name = name;
        if (baseUrl !== provider.base_url) update.base_url = baseUrl;
        if (apiKey) update.api_key = apiKey;
        if (isActive !== provider.is_active) update.is_active = isActive;
        await apiClient.put(`/api/providers/${provider.id}`, update);
      } else {
        await apiClient.post('/api/providers', { name, base_url: baseUrl, api_key: apiKey });
      }
      onClose();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail ?? 'Error saving provider');
      } else {
        setError('Error saving provider');
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ padding: 16, marginBottom: 16, border: '1px solid #ddd', borderRadius: 8 }}>
      <h3>{isEditing ? 'Edit Provider' : 'Add Provider'}</h3>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} required style={{ width: '100%', padding: 8, boxSizing: 'border-box' }} />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>Base URL</label>
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required style={{ width: '100%', padding: 8, boxSizing: 'border-box' }} />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>API Key {isEditing && '(leave blank to keep current)'}</label>
        <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} required={!isEditing} type="password" style={{ width: '100%', padding: 8, boxSizing: 'border-box' }} />
      </div>

      {isEditing && (
        <div style={{ marginBottom: 12 }}>
          <label>
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            {' '}Active
          </label>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" style={{ padding: '8px 16px', cursor: 'pointer' }}>Save</button>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', cursor: 'pointer' }}>Cancel</button>
      </div>
    </form>
  );
}
