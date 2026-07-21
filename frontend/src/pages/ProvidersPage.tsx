import { useState, useEffect } from 'react';
import apiClient from '../api/client';
import type { Provider } from '../types';
import ProviderForm from '../components/providers/ProviderForm';

export default function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [showForm, setShowForm] = useState(false);

  const fetchProviders = async () => {
    const res = await apiClient.get('/api/providers');
    setProviders(res.data);
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this provider?')) return;
    await apiClient.delete(`/api/providers/${id}`);
    fetchProviders();
  };

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider);
    setShowForm(true);
  };

  const handleAdd = () => {
    setEditingProvider(null);
    setShowForm(true);
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingProvider(null);
    fetchProviders();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Providers</h2>
        <button onClick={handleAdd} style={{ padding: '8px 16px', cursor: 'pointer' }}>
          Add Provider
        </button>
      </div>

      {showForm && (
        <ProviderForm provider={editingProvider} onClose={handleFormClose} />
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
            <th style={{ padding: 8 }}>Name</th>
            <th style={{ padding: 8 }}>Base URL</th>
            <th style={{ padding: 8 }}>API Key</th>
            <th style={{ padding: 8 }}>Active</th>
            <th style={{ padding: 8 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: 8 }}>{p.name}</td>
              <td style={{ padding: 8, fontSize: 13 }}>{p.base_url}</td>
              <td style={{ padding: 8, fontFamily: 'monospace', fontSize: 12 }}>{p.api_key_masked}</td>
              <td style={{ padding: 8 }}>{p.is_active ? '✓' : '✗'}</td>
              <td style={{ padding: 8 }}>
                <button onClick={() => handleEdit(p)} style={{ marginRight: 8, cursor: 'pointer' }}>Edit</button>
                <button onClick={() => handleDelete(p.id)} style={{ cursor: 'pointer', color: 'red' }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
