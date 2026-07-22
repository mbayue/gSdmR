import { useState, type FormEvent } from 'react';
import { Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { useCreateModel, useUpdateModel } from '../../hooks/useModels';
import { useProviders, useProviderModels } from '../../hooks/useProviders';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import type { Model, ModelProviderMapping } from '../../types';

interface Props {
  model: Model | null;
  onClose: () => void;
}

function ProviderModelSelect({ providerId, value, onChange }: { providerId: number; value: string; onChange: (v: string) => void }) {
  const { data: models = [], isLoading } = useProviderModels(providerId);

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
      disabled={providerId <= 0}
    >
      <option value="">
        {providerId <= 0 ? 'Select provider first' : isLoading ? 'Loading...' : 'Select model...'}
      </option>
      {models.map((m: { id: string }) => (
        <option key={m.id} value={m.id}>{m.id}</option>
      ))}
    </select>
  );
}

function ProviderModelOptions({ providerId }: { providerId: number }) {
  const { data: models = [], isLoading } = useProviderModels(providerId);

  if (isLoading) return <SelectItem value="__loading" disabled>Loading...</SelectItem>;
  if (models.length === 0) return <SelectItem value="__empty" disabled>No models available</SelectItem>;

  return (
    <>
      {models.map((m: { id: string }) => (
        <SelectItem key={m.id} value={m.id}>{m.id}</SelectItem>
      ))}
    </>
  );
}

export default function ModelForm({ model, onClose }: Props) {
  const [name, setName] = useState(model?.name ?? '');
  const [loadBalance, setLoadBalance] = useState<string>(model?.load_balance ?? 'priority');
  const [mappings, setMappings] = useState<ModelProviderMapping[]>(
    model?.providers ?? [{ provider_id: 0, provider_model: '', priority: 1 }]
  );

  const { data: providers = [] } = useProviders();
  const createModel = useCreateModel();
  const updateModel = useUpdateModel();
  const isEditing = !!model;

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

    if (!name.trim()) {
      toast.error('Model name is required');
      return;
    }

    const validMappings = mappings.filter((m) => m.provider_id > 0 && m.provider_model.trim() !== '');
    if (validMappings.length === 0) {
      toast.error('At least one provider with a model selection is required');
      return;
    }

    const payload = {
      name,
      load_balance: loadBalance as 'priority' | 'round-robin' | 'weighted-random',
      providers: validMappings.map((m) => ({
        provider_id: m.provider_id,
        provider_model: m.provider_model,
        priority: m.priority,
      })),
    };

    try {
      if (isEditing) {
        await updateModel.mutateAsync({ id: model.id, data: payload });
        toast.success('Model updated');
      } else {
        await createModel.mutateAsync(payload);
        toast.success('Model created');
      }
      onClose();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        toast.error(axiosErr.response?.data?.detail ?? 'Error saving model');
      } else {
        toast.error('Error saving model');
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="model-name">Model Name (your custom alias)</Label>
        <Input
          id="model-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="e.g., my-gpt4, fast-claude"
        />
      </div>

      <div className="space-y-2">
        <Label>Load Balancing</Label>
        <Select value={loadBalance} onValueChange={setLoadBalance}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="priority">Priority (try highest first, fallback in order)</SelectItem>
            <SelectItem value="round-robin">Round Robin (rotate across providers)</SelectItem>
            <SelectItem value="weighted-random">Weighted Random (random based on priority weights)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <Label>Provider Routes</Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select provider and model to route to. Priority 1 = tried first.
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={addMapping}>
            <Plus className="h-3 w-3" />
            Add Route
          </Button>
        </div>

        <div className="space-y-2">
          {mappings.map((mapping, index) => (
            <div key={index} className="flex items-center gap-2">
              <Select
                value={mapping.provider_id > 0 ? String(mapping.provider_id) : ''}
                onValueChange={(val) => updateMappingProvider(index, Number(val))}
              >
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Provider..." />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={mapping.provider_model}
                onValueChange={(val) => updateMappingModel(index, val)}
                disabled={mapping.provider_id <= 0}
              >
                <SelectTrigger className="flex-1">
                  <SelectValue
                    placeholder={
                      mapping.provider_id <= 0
                        ? 'Select provider first'
                        : 'Select model...'
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  <ProviderModelOptions providerId={mapping.provider_id} />
                </SelectContent>
              </Select>
              </Select>

              <Input
                type="number"
                min={1}
                value={mapping.priority}
                onChange={(e) => updateMappingPriority(index, Number(e.target.value))}
                className="w-16"
                title="Priority"
              />

              {mappings.length > 1 && (
                <Button type="button" variant="ghost" size="icon" onClick={() => removeMapping(index)}>
                  <X className="h-4 w-4 text-destructive" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={createModel.isPending || updateModel.isPending}>
          {(createModel.isPending || updateModel.isPending) ? 'Saving...' : 'Save'}
        </Button>
      </div>
    </form>
  );
}
