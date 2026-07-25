import { useState } from 'react';
import { Play, RotateCw, Ban, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useProviders, useProviderModels } from '../hooks/useProviders';
import { useModels } from '../hooks/useModels';
import { useDisabledModels, useTestModel, useRouteTest, useDeactivateModel, useActivateModel } from '../hooks/usePlayground';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import type { PlaygroundTestResult } from '../types';

type TabMode = 'direct' | 'route';

export default function PlaygroundPage() {
  const [activeTab, setActiveTab] = useState<TabMode>('direct');
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Playground</h1>
        <p className="text-sm text-muted-foreground">Test models directly against providers or through routing</p>
      </div>
      <div className="flex gap-1 rounded-lg bg-secondary/50 p-1 w-fit">
        <button onClick={() => setActiveTab('direct')} className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${activeTab === 'direct' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Direct Test</button>
        <button onClick={() => setActiveTab('route')} className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${activeTab === 'route' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Route Test</button>
      </div>
      {activeTab === 'direct' ? <DirectTestPanel /> : <RouteTestPanel />}
    </div>
  );
}

function DirectTestPanel() {
  const { data: providers = [], isLoading: loadingProviders } = useProviders();
  const { data: disabledModels = [] } = useDisabledModels();
  const [selectedProvider, setSelectedProvider] = useState<number | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [result, setResult] = useState<PlaygroundTestResult | null>(null);
  const testModel = useTestModel();
  const deactivateModel = useDeactivateModel();
  const activateModel = useActivateModel();

  const isDisabled = (pid: number, m: string) => disabledModels.some((d) => d.provider_id === pid && d.model_name === m);

  const handleTest = () => {
    if (!selectedProvider || !selectedModel) return;
    setResult(null);
    testModel.mutate({ provider_id: selectedProvider, model_name: selectedModel }, {
      onSuccess: (data) => setResult(data),
      onError: () => toast.error('Test request failed'),
    });
  };

  const handleDeactivate = () => {
    if (!selectedProvider || !selectedModel) return;
    deactivateModel.mutate({ provider_id: selectedProvider, model_name: selectedModel }, {
      onSuccess: () => toast.success('Model deactivated'),
    });
  };

  const handleActivate = () => {
    if (!selectedProvider || !selectedModel) return;
    activateModel.mutate({ provider_id: selectedProvider, model_name: selectedModel }, {
      onSuccess: () => toast.success('Model re-activated'),
    });
  };

  if (loadingProviders) return <div className="text-muted-foreground text-sm">Loading providers...</div>;

  return (
    <div className="space-y-4">
      {/* Test button */}
      <div className="flex items-center justify-end gap-2 h-9">
        {selectedProvider && selectedModel && <span className="text-xs text-muted-foreground">Testing <span className="font-mono">{selectedModel}</span></span>}
        <Button onClick={handleTest} disabled={!selectedProvider || !selectedModel || testModel.isPending} size="sm">
          {testModel.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          Test
        </Button>
      </div>

      {/* Result card */}
      <Card className="min-h-[160px]">
        {result ? (
          <>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {result.success ? <CheckCircle2 className="size-4 text-green-500" /> : <XCircle className="size-4 text-red-500" />}
                  <CardTitle className="text-sm font-medium">{result.success ? 'Success' : 'Failed'}</CardTitle>
                  <Badge variant={result.success ? 'default' : 'destructive'} className="text-xs">{result.latency_ms}ms</Badge>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={handleTest} disabled={testModel.isPending}>
                    <RotateCw className={`size-3 ${testModel.isPending ? 'animate-spin' : ''}`} />Retry
                  </Button>
                  {!result.success && selectedProvider && selectedModel && !isDisabled(selectedProvider, selectedModel) && (
                    <Button variant="ghost" size="sm" onClick={handleDeactivate} className="text-red-400 hover:text-red-300"><Ban className="size-3" />Deactivate</Button>
                  )}
                  {result.success && selectedProvider && selectedModel && isDisabled(selectedProvider, selectedModel) && (
                    <Button variant="ghost" size="sm" onClick={handleActivate} className="text-green-400 hover:text-green-300"><CheckCircle2 className="size-3" />Activate</Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 min-h-[80px]">
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>Provider: <span className="text-foreground">{result.provider_name}</span></span>
                <span>Model: <span className="font-mono text-foreground">{result.model_name}</span></span>
              </div>
              <div className="rounded bg-secondary/50 p-3 text-sm font-mono whitespace-pre-wrap min-h-[44px]">
                {result.response_text && result.response_text}
                {result.error && <span className="text-red-400">{result.error}</span>}
                {!result.response_text && !result.error && <span className="text-muted-foreground">No response</span>}
              </div>
            </CardContent>
          </>
        ) : (
          <CardContent className="h-[160px] flex items-center justify-center text-sm text-muted-foreground p-0">
            Select a model and click Test to see results here
          </CardContent>
        )}
      </Card>

      {/* Provider sections */}
      {providers.map((p) => (
        <ProviderSection key={p.id} providerId={p.id} providerName={p.name} isDisabledFn={isDisabled} selectedProvider={selectedProvider} selectedModel={selectedModel} onSelect={(m) => { setSelectedProvider(p.id); setSelectedModel(m); setResult(null); }} />
      ))}
    </div>
  );
}

function ProviderSection({ providerId, providerName, isDisabledFn, selectedProvider, selectedModel, onSelect }: {
  providerId: number; providerName: string; isDisabledFn: (pid: number, m: string) => boolean;
  selectedProvider: number | null; selectedModel: string | null; onSelect: (m: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { data: models = [], isLoading, isError, refetch } = useProviderModels(expanded ? providerId : 0);

  return (
    <div className="rounded-lg border">
      <button onClick={() => setExpanded(!expanded)} className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-secondary/30 transition-colors">
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          <span className="font-medium text-sm">{providerName}</span>
          {expanded && !isLoading && !isError && <Badge variant="secondary" className="text-xs">{models.length} models</Badge>}
        </div>
      </button>
      {expanded && (
        <div className="border-t px-4 py-3">
          {isLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-3 animate-spin" />Loading models...</div>}
          {isError && <div className="flex items-center gap-2"><span className="text-sm text-red-400">Failed to load models</span><Button variant="ghost" size="sm" onClick={() => refetch()}><RefreshCw className="size-3" />Retry</Button></div>}
          {!isLoading && !isError && models.length === 0 && <span className="text-sm text-muted-foreground">No models available</span>}
          {!isLoading && !isError && models.length > 0 && (
            <div className="grid grid-cols-1 gap-1 max-h-60 overflow-y-auto">
              {models.map((item: { id: string } | string) => {
                const model = typeof item === 'string' ? item : item.id;
                const disabled = isDisabledFn(providerId, model);
                const isSelected = selectedProvider === providerId && selectedModel === model;
                return (
                  <button key={model} onClick={() => onSelect(model)} className={`flex items-center gap-2 rounded px-3 py-1.5 text-left text-sm transition-colors ${isSelected ? 'bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/30' : disabled ? 'text-muted-foreground/50 hover:bg-secondary/30' : 'text-foreground hover:bg-secondary/50'}`}>
                    <div className={`size-2 rounded-full ${isSelected ? 'bg-blue-500' : 'bg-transparent border border-muted-foreground/30'}`} />
                    <span className={`font-mono text-xs ${disabled ? 'line-through' : ''}`}>{model}</span>
                    {disabled && <Badge variant="outline" className="text-[10px] px-1 py-0 text-muted-foreground">Deactivated</Badge>}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RouteTestPanel() {
  const { data: models = [], isLoading } = useModels();
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [result, setResult] = useState<PlaygroundTestResult | null>(null);
  const routeTest = useRouteTest();

  const handleTest = () => {
    if (!selectedModel) return;
    setResult(null);
    routeTest.mutate({ model_name: selectedModel }, {
      onSuccess: (data) => setResult(data),
      onError: () => toast.error('Route test failed'),
    });
  };

  if (isLoading) return <div className="text-muted-foreground text-sm">Loading models...</div>;

  return (
    <div className="space-y-4">
      {/* Test button */}
      <div className="flex items-center justify-end gap-2 h-9">
        <Select value={selectedModel} onValueChange={(v) => { setSelectedModel(v); setResult(null); }}>
          <SelectTrigger className="w-72"><SelectValue placeholder="Select a model alias..." /></SelectTrigger>
          <SelectContent>
            {models.map((m) => <SelectItem key={m.id} value={m.name}>{m.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button onClick={handleTest} disabled={!selectedModel || routeTest.isPending} size="sm">
          {routeTest.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          Test
        </Button>
      </div>

      {/* Result card */}
      <Card className="min-h-[160px]">
        {result ? (
          <>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {result.success ? <CheckCircle2 className="size-4 text-green-500" /> : <XCircle className="size-4 text-red-500" />}
                  <CardTitle className="text-sm font-medium">{result.success ? 'Success' : 'Failed'}</CardTitle>
                  <Badge variant={result.success ? 'default' : 'destructive'} className="text-xs">{result.latency_ms}ms</Badge>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={handleTest} disabled={routeTest.isPending}>
                    <RotateCw className={`size-3 ${routeTest.isPending ? 'animate-spin' : ''}`} />Retry
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 min-h-[80px]">
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>Provider: <span className="text-foreground">{result.provider_name}</span></span>
                <span>Model: <span className="font-mono text-foreground">{result.model_name}</span></span>
              </div>
              <div className="rounded bg-secondary/50 p-3 text-sm font-mono whitespace-pre-wrap min-h-[44px]">
                {result.response_text && result.response_text}
                {result.error && <span className="text-red-400">{result.error}</span>}
                {!result.response_text && !result.error && <span className="text-muted-foreground">No response</span>}
              </div>
            </CardContent>
          </>
        ) : (
          <CardContent className="h-[160px] flex items-center justify-center text-sm text-muted-foreground p-0">
            Select a model and click Test to see results here
          </CardContent>
        )}
      </Card>
    </div>
  );
}

