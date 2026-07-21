import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../api/client';

export default function Layout() {
  const { username, logout } = useAuth();

  const handleExport = async () => {
    try {
      const res = await apiClient.get('/api/backup/export');
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gsdm-r-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Export failed');
    }
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await apiClient.post('/api/backup/import', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        alert(`Import successful: ${res.data.imported.providers} providers, ${res.data.imported.models} models, ${res.data.imported.api_keys} keys`);
        window.location.reload();
      } catch {
        alert('Import failed');
      }
    };
    input.click();
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: 20 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #ddd', paddingBottom: 12, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <h1 style={{ fontSize: 18, margin: 0 }}>gSdm-R</h1>
          <nav style={{ display: 'flex', gap: 16 }}>
            <NavLink to="/" style={({ isActive }) => ({ fontWeight: isActive ? 'bold' : 'normal' })}>
              Providers
            </NavLink>
            <NavLink to="/models" style={({ isActive }) => ({ fontWeight: isActive ? 'bold' : 'normal' })}>
              Models
            </NavLink>
            <NavLink to="/keys" style={({ isActive }) => ({ fontWeight: isActive ? 'bold' : 'normal' })}>
              API Keys
            </NavLink>
          </nav>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={handleExport} style={{ cursor: 'pointer', padding: '4px 12px', fontSize: 12 }}>Export</button>
          <button onClick={handleImport} style={{ cursor: 'pointer', padding: '4px 12px', fontSize: 12 }}>Import</button>
          <span style={{ fontSize: 14, color: '#666' }}>{username}</span>
          <button onClick={logout} style={{ cursor: 'pointer', padding: '4px 12px' }}>Logout</button>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
