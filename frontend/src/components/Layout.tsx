import { NavLink, Outlet } from 'react-router-dom';
import { Download, Upload, LogOut, Server } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../hooks/useAuth';
import { Button } from './ui/button';
import { Separator } from './ui/separator';
import apiClient from '../api/client';
import { cn } from '@/lib/utils';

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
      toast.success('Configuration exported');
    } catch {
      toast.error('Export failed');
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
        toast.success(
          `Imported: ${res.data.imported.providers} providers, ${res.data.imported.models} models, ${res.data.imported.api_keys} keys`
        );
        window.location.reload();
      } catch {
        toast.error('Import failed');
      }
    };
    input.click();
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5 text-blue-500" />
              <span className="text-lg font-bold tracking-tight">gSdm-R</span>
            </div>
            <Separator orientation="vertical" className="h-6" />
            <nav className="flex items-center gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  )
                }
              >
                Providers
              </NavLink>
              <NavLink
                to="/models"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  )
                }
              >
                Models
              </NavLink>
              <NavLink
                to="/keys"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  )
                }
              >
                API Keys
              </NavLink>
              <NavLink
                to="/usage"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  )
                }
              >
                Usage
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4" />
              Export
            </Button>
            <Button variant="ghost" size="sm" onClick={handleImport}>
              <Upload className="h-4 w-4" />
              Import
            </Button>
            <Separator orientation="vertical" className="h-6" />
            <span className="text-sm text-muted-foreground">{username}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
