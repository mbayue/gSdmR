import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { RefreshCw, Server } from 'lucide-react';

interface HealthCheck {
  status: string;
  latency_ms: number;
  time: string;
}

interface ProviderStatus {
  name: string;
  status: string;
  uptime_pct: number;
  avg_latency_ms: number;
  last_check: string | null;
  history: HealthCheck[];
}

interface StatusData {
  status: string;
  uptime: string;
  uptime_seconds: number;
  providers: ProviderStatus[];
  stats: {
    requests_last_hour: number;
    success_rate_last_hour: number;
    avg_latency_ms: number;
  };
  timestamp: string;
}

const fetchStatus = async (): Promise<StatusData> => {
  const res = await axios.get('/api/status');
  return res.data;
};

type FilterType = 'none' | 'healthy' | 'unhealthy';
type SortType = 'name' | 'latency' | 'uptime';

function StatusBadge({ status }: { status: string }) {
  if (status === 'healthy' || status === 'active') {
    return <span className="inline-flex items-center rounded-full bg-green-500/20 px-2.5 py-0.5 text-xs font-medium text-green-400 border border-green-500/30">Healthy</span>;
  }
  if (status === 'unhealthy') {
    return <span className="inline-flex items-center rounded-full bg-red-500/20 px-2.5 py-0.5 text-xs font-medium text-red-400 border border-red-500/30">Unhealthy</span>;
  }
  if (status === 'disabled' || status === 'inactive') {
    return <span className="inline-flex items-center rounded-full bg-zinc-500/20 px-2.5 py-0.5 text-xs font-medium text-zinc-400 border border-zinc-500/30">Disabled</span>;
  }
  return <span className="inline-flex items-center rounded-full bg-zinc-500/20 px-2.5 py-0.5 text-xs font-medium text-zinc-400 border border-zinc-500/30">Unknown</span>;
}

function UptimeBar({ history, hoveredIndex, onHover }: { history: HealthCheck[]; hoveredIndex: number | null; onHover: (i: number | null) => void }) {
  const bars = history.length > 0 ? history : [];
  if (bars.length === 0) {
    return <div className="flex gap-[1px] h-7 items-end opacity-30">
      {Array(60).fill(0).map((_, i) => (
        <div key={i} className="flex-1 min-w-[2px] h-full bg-zinc-700 rounded-[1px]" />
      ))}
    </div>;
  }

  return (
    <div className="flex gap-[1px] h-7 items-end">
      {bars.map((check, i) => {
        const color = check.status === 'healthy' ? 'bg-green-500' : 'bg-red-500';
        return (
          <div
            key={i}
            className={`flex-1 min-w-[2px] h-full rounded-[1px] ${color} ${hoveredIndex === i ? 'opacity-70' : 'opacity-100'} transition-opacity cursor-pointer`}
            onMouseEnter={() => onHover(i)}
            onMouseLeave={() => onHover(null)}
          />
        );
      })}
    </div>
  );
}

function ProviderCard({ provider }: { provider: ProviderStatus }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const hoveredCheck = hoveredIndex !== null ? provider.history[hoveredIndex] : null;

  const firstTime = provider.history.length > 0 ? provider.history[0].time : null;
  const lastTime = provider.history.length > 0 ? provider.history[provider.history.length - 1].time : null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">{provider.name}</h3>
          <p className="text-xs text-muted-foreground">{provider.avg_latency_ms > 0 ? `~${provider.avg_latency_ms}ms` : 'router'}</p>
        </div>
        <StatusBadge status={provider.status} />
      </div>

      {/* Latency label */}
      <div className="flex justify-end">
        <span className="text-xs text-green-400">
          {hoveredCheck ? `${hoveredCheck.latency_ms}ms` : provider.avg_latency_ms > 0 ? `~${provider.avg_latency_ms}ms` : ''}
        </span>
      </div>

      {/* Uptime bars */}
      <div className="relative">
        <UptimeBar history={provider.history} hoveredIndex={hoveredIndex} onHover={setHoveredIndex} />

        {/* Tooltip */}
        {hoveredCheck && hoveredIndex !== null && (
          <div
            className="absolute z-20 bottom-full mb-2 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs shadow-lg pointer-events-none whitespace-nowrap"
            style={{
              left: `${(hoveredIndex / Math.max(provider.history.length - 1, 1)) * 100}%`,
              transform: 'translateX(-50%)',
            }}
          >
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">TIMESTAMP</span>
              <span>{new Date(hoveredCheck.time + 'Z').toLocaleString()}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">RESPONSE TIME</span>
              <span>{hoveredCheck.latency_ms}ms</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">STATUS</span>
              <span className={hoveredCheck.status === 'healthy' ? 'text-green-400' : 'text-red-400'}>
                {hoveredCheck.status === 'healthy' ? '✓ 200' : '✗ Failed'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Time range */}
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{firstTime ? formatTimeAgo(firstTime) : ''}</span>
        <span>{lastTime ? formatTimeAgo(lastTime) : 'just now'}</span>
      </div>
    </div>
  );
}

function formatTimeAgo(isoTime: string): string {
  const diff = Date.now() - new Date(isoTime + 'Z').getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hours ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

export default function StatusPage() {
  const [filter, setFilter] = useState<FilterType>('none');
  const [sort, setSort] = useState<SortType>('name');
  const [refreshInterval, setRefreshInterval] = useState(300000); // 5min default

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: refreshInterval,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading status...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-lg font-bold text-destructive">Service Unavailable</h2>
          <p className="text-sm text-muted-foreground mt-2">Unable to reach the API.</p>
        </div>
      </div>
    );
  }

  // Filter
  let providers = [...data.providers];
  if (filter === 'healthy') providers = providers.filter(p => p.status === 'healthy' || p.status === 'active');
  if (filter === 'unhealthy') providers = providers.filter(p => p.status === 'unhealthy' || p.status === 'disabled');

  // Sort
  if (sort === 'name') providers.sort((a, b) => a.name.localeCompare(b.name));
  if (sort === 'latency') providers.sort((a, b) => a.avg_latency_ms - b.avg_latency_ms);
  if (sort === 'uptime') providers.sort((a, b) => b.uptime_pct - a.uptime_pct);

  return (
    <div className="min-h-screen bg-background">
      {/* Sticky header matching main app */}
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Server className="size-5 text-blue-500" />
              <span className="text-lg font-bold tracking-tight">gSdm-R</span>
            </div>
            <span className="text-sm text-muted-foreground">Status</span>
          </div>
          <button onClick={() => refetch()} className="p-2 rounded-md hover:bg-zinc-800 transition-colors">
            <RefreshCw className="size-4 text-muted-foreground" />
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold tracking-tight">Health Dashboard</h2>
          <p className="text-sm text-muted-foreground">Monitor the health of your providers in real-time</p>
        </div>

        {/* Filter/Sort bar */}
        <div className="flex items-center justify-between mb-6 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
          <div className="flex items-center gap-4">
            <span className="text-xs text-muted-foreground">Filter by:</span>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterType)}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs"
            >
              <option value="none">None</option>
              <option value="healthy">Healthy</option>
              <option value="unhealthy">Failing</option>
            </select>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-muted-foreground">Sort by:</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortType)}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs"
            >
              <option value="name">Name</option>
              <option value="latency">Latency</option>
              <option value="uptime">Uptime</option>
            </select>
          </div>
        </div>

        {/* Provider grid */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {providers.map((p) => (
            <ProviderCard key={p.name} provider={p} />
          ))}
        </div>

        {providers.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">
            {filter !== 'none' ? 'No providers match the current filter.' : 'No providers configured yet.'}
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 pt-4 border-t border-zinc-800 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <RefreshCw className="size-3" />
            <select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs"
            >
              <option value={10000}>10s</option>
              <option value={30000}>30s</option>
              <option value={60000}>1m</option>
              <option value={120000}>2m</option>
              <option value={300000}>5m</option>
              <option value={600000}>10m</option>
            </select>
          </div>
          <span>Uptime: {data.uptime} · Last updated: {new Date(data.timestamp).toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
}
