import { useState, useEffect } from 'react';
import apiClient from '../api/client';
import type { Model } from '../types';
import ModelForm from '../components/models/ModelForm';

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [showForm, setShowForm] = useState(false);

  const fetchModels = async () => {
    const res = await apiClient.get('/api/models');
    setModels(res.data);
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this model?')) return;
    await apiClient.delete(`/api/models/${id}`);
    fetchModels();
  };

  const handleEdit = (model: Model) => {
    setEditingModel(model);
    setShowForm(true);
  };

  const handleAdd = () => {
    setEditingModel(null);
    setShowForm(true);
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingModel(null);
    fetchModels();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Models</h2>
        <button onClick={handleAdd} style={{ padding: '8px 16px', cursor: 'pointer' }}>
          Add Model
        </button>
      </div>

      {showForm && (
        <ModelForm model={editingModel} onClose={handleFormClose} />
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
            <th style={{ padding: 8 }}>Model Name</th>
            <th style={{ padding: 8 }}>Providers (priority order)</th>
            <th style={{ padding: 8 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.id} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: 8, fontFamily: 'monospace' }}>{m.name}</td>
              <td style={{ padding: 8 }}>
                {m.providers.map((p, i) => (
                  <span key={i} style={{ marginRight: 8, padding: '2px 6px', background: '#f0f0f0', borderRadius: 4, fontSize: 13 }}>
                    {p.priority}. {p.provider_name} → {p.provider_model}
                  </span>
                ))}
              </td>
              <td style={{ padding: 8 }}>
                <button onClick={() => handleEdit(m)} style={{ marginRight: 8, cursor: 'pointer' }}>Edit</button>
                <button onClick={() => handleDelete(m.id)} style={{ cursor: 'pointer', color: 'red' }}>Delete</button>
              </td>
            </tr>
          ))}
          {models.length === 0 && (
            <tr>
              <td colSpan={3} style={{ padding: 16, textAlign: 'center', color: '#888' }}>
                No models configured yet. Add a model to start routing.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
