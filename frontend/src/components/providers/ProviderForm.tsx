import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { useCreateProvider, useUpdateProvider } from '../../hooks/useProviders';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
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

  const createProvider = useCreateProvider();
  const updateProvider = useUpdateProvider();
  const isEditing = !!provider;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    try {
      if (isEditing) {
        const update: Record<string, unknown> = {};
        if (name !== provider.name) update.name = name;
        if (baseUrl !== provider.base_url) update.base_url = baseUrl;
        if (apiKey) update.api_key = apiKey;
        if (isActive !== provider.is_active) update.is_active = isActive;
        await updateProvider.mutateAsync({ id: provider.id, data: update });
        toast.success('Provider updated');
      } else {
        await createProvider.mutateAsync({ name, base_url: baseUrl, api_key: apiKey });
        toast.success('Provider created');
      }
      onClose();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        toast.error(axiosErr.response?.data?.detail ?? 'Error saving provider');
      } else {
        toast.error('Error saving provider');
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="provider-name">Name</Label>
        <Input
          id="provider-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="e.g., OpenAI, Anthropic"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="provider-url">Base URL</Label>
        <Input
          id="provider-url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          required
          placeholder="https://api.openai.com/v1"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="provider-key">
          API Key {isEditing && <span className="text-muted-foreground font-normal">(leave blank to keep current)</span>}
        </Label>
        <Input
          id="provider-key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          required={!isEditing}
          type="password"
          placeholder={isEditing ? '••••••••' : 'sk-...'}
        />
      </div>

      {isEditing && (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="provider-active"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 rounded border-input"
          />
          <Label htmlFor="provider-active" className="font-normal">Active</Label>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={createProvider.isPending || updateProvider.isPending}>
          {(createProvider.isPending || updateProvider.isPending) ? 'Saving...' : 'Save'}
        </Button>
      </div>
    </form>
  );
}
