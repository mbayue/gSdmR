import { useState } from 'react';
import { Plus, Trash2, Copy, Check, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import {
  useApiKeys,
  useAvailableModels,
  useCreateApiKey,
  useUpdateApiKey,
  useToggleApiKey,
  useDeleteApiKey,
} from '../hooks/useApiKeys';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import type { ApiKey } from '../hooks/useApiKeys';

export default function ApiKeysPage() {
  const { data: keys = [], isLoading } = useApiKeys();
  const { data: models = [] } = useAvailableModels();
  const createApiKey = useCreateApiKey();
  const updateApiKey = useUpdateApiKey();
  const toggleApiKey = useToggleApiKey();
  const deleteApiKey = useDeleteApiKey();

  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<ApiKey | null>(null);
  const [newKeyName, setNewKeyName] = useState('');
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([]);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ApiKey | null>(null);

  const handleCreate = async () => {
    if (!newKeyName.trim()) {
      toast.error('Name is required');
      return;
    }
    try {
      const result = await createApiKey.mutateAsync({
        name: newKeyName,
        model_ids: selectedModelIds,
      });
      setCreatedKey(result.key_value);
      setNewKeyName('');
      setSelectedModelIds([]);
      toast.success('API key generated');
    } catch {
      toast.error('Error creating key');
    }
  };

  const handleCopy = async () => {
    if (!createdKey) return;
    await navigator.clipboard.writeText(createdKey);
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleToggle = (key: ApiKey) => {
    toggleApiKey.mutate(
      { id: key.id, is_active: !key.is_active },
      { onSuccess: () => toast.success(`Key "${key.name}" ${key.is_active ? 'disabled' : 'enabled'}`) }
    );
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteApiKey.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success(`Key "${deleteTarget.name}" deleted`);
        setDeleteTarget(null);
      },
      onError: () => toast.error('Failed to delete key'),
    });
  };

  const toggleModel = (modelId: number) => {
    setSelectedModelIds((prev) =>
      prev.includes(modelId) ? prev.filter((id) => id !== modelId) : [...prev, modelId]
    );
  };

  const handleOpenForm = () => {
    setShowForm(true);
    setEditTarget(null);
    setCreatedKey(null);
    setCopied(false);
    setNewKeyName('');
    setSelectedModelIds([]);
  };

  const handleEdit = (key: ApiKey) => {
    setEditTarget(key);
    setNewKeyName(key.name);
    setSelectedModelIds(key.allowed_models.map((m) => m.id));
    setCreatedKey(null);
    setShowForm(true);
  };

  const handleSaveEdit = async () => {
    if (!editTarget || !newKeyName.trim()) return;
    try {
      await updateApiKey.mutateAsync({
        id: editTarget.id,
        data: {
          name: newKeyName,
          model_ids: selectedModelIds,
        },
      });
      toast.success('API key updated');
      setShowForm(false);
      setEditTarget(null);
    } catch {
      toast.error('Failed to update key');
    }
  };

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">Loading API keys...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground">Manage keys for accessing the router proxy</p>
        </div>
        <Button onClick={handleOpenForm} size="sm">
          <Plus className="h-4 w-4" />
          Generate Key
        </Button>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Models</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-[100px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {keys.map((k) => (
              <TableRow key={k.id}>
                <TableCell className="font-medium">{k.name}</TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{k.key_preview}</TableCell>
                <TableCell>
                  {k.allowed_models.length === 0 ? (
                    <span className="text-xs text-muted-foreground">All models</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {k.allowed_models.map((m) => (
                        <Badge key={m.id} variant="secondary" className="text-xs font-normal">
                          {m.name}
                        </Badge>
                      ))}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleToggle(k)}
                    className="h-auto p-0"
                  >
                    <Badge variant={k.is_active ? 'default' : 'destructive'}>
                      {k.is_active ? 'Active' : 'Disabled'}
                    </Badge>
                  </Button>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(k)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(k)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {keys.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                  No API keys generated yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Generate/Edit Key Dialog */}
      <Dialog open={showForm} onOpenChange={(open) => { if (!open) { setShowForm(false); setEditTarget(null); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editTarget ? 'Edit API Key' : 'Generate API Key'}</DialogTitle>
            <DialogDescription>
              {editTarget ? 'Update the key name and model restrictions.' : 'Create a new key for authenticating with the router proxy.'}
            </DialogDescription>
          </DialogHeader>

          {createdKey && !editTarget && (
            <div className="rounded-md border border-green-800 bg-green-950/50 p-4 space-y-2">
              <p className="text-sm font-medium text-green-400">
                Key created! Copy it now — it won't be shown again.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded bg-background p-2 text-xs break-all font-mono">
                  {createdKey}
                </code>
                <Button variant="outline" size="icon" onClick={handleCopy}>
                  {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="key-name">Key Name</Label>
              <Input
                id="key-name"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="e.g., Production, Testing, User-A"
              />
            </div>

            <div className="space-y-2">
              <Label>
                Model Restrictions{' '}
                <span className="text-muted-foreground font-normal">(none = all models allowed)</span>
              </Label>
              <div className="flex flex-wrap gap-2">
                {models.map((m) => (
                  <label
                    key={m.id}
                    className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm cursor-pointer transition-colors ${
                      selectedModelIds.includes(m.id)
                        ? 'bg-blue-500/10 border-blue-500/50 text-blue-400'
                        : 'border-border hover:bg-secondary'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedModelIds.includes(m.id)}
                      onChange={() => toggleModel(m.id)}
                      className="sr-only"
                    />
                    {m.name}
                  </label>
                ))}
                {models.length === 0 && (
                  <span className="text-sm text-muted-foreground">No models configured yet</span>
                )}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowForm(false); setEditTarget(null); }}>Close</Button>
            {editTarget ? (
              <Button onClick={handleSaveEdit} disabled={updateApiKey.isPending || !newKeyName.trim()}>
                {updateApiKey.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
            ) : (
              <Button onClick={handleCreate} disabled={createApiKey.isPending}>
                {createApiKey.isPending ? 'Generating...' : 'Generate Key'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.name}&quot;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
