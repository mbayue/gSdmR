import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Badge } from '../components/ui/badge';
import { Separator } from '../components/ui/separator';

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

function OverallBadge({ status }: { status: string }) {
  if (status === 'operational') {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-green-950/50 border border-green-800 px-4 py-2">
        <div className="size-3 rounded-full bg-green-500 animate-pulse" />
        <span className="text-green-400 font-medium">All Systems Operational</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded-lg bg-yellow-950/50 border border-yellow-800 px-4 py-2">
      <div className="size-3 rounded-full bg-yellow-500 animate-pulse" />
      <span className="text-yellow-400 font-medium">Degraded Performance</span>
    </div>
  );
}

function UptimeBar({ history }: { history: HealthCheck[] }) {
  // Show bars — each bar is one health check
  const bars = history.length > 0 ? history : Array(90).fill({ status: 'unknown' });

  return (
    <div className="flex gap-[1px] h-8 items-end">
      {bars.map((check, i) => {
        let color = 'bg-zinc-700'; // unknown/no data
        let height = '100%';

        if (check.status === 'healthy') {
          color = 'bg-green-500';
          // Height based on latency (lower = taller)
          const maxH = 100;
          const minH = 40;
          const latencyFactor = Math.min(check.latency_ms / 2000, 1);
          height = `${maxH - (latencyFactor * (maxH - minH))}%`;
        } else if (check.status === 'unhealthy') {
          color = 'bg-red-500';
          height = '100%';
        }

        return (
          <div
            key={i}
            className="flex-1 min-w-[2px] flex items-end group relative"
            style={{ height: '100%' }}
          >
            <div
              className={`w-full rounded-[1px] ${color} transition-all hover:opacity-80`}
              style={{ height }}
            />
            {check.time && (
              <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                <div className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs whitespace-nowrap">
                  <div>{check.status === 'healthy' ? '✓' : '✗'} {check.latency_ms}ms</div>
                  <div className="text-muted-foreground">{new Date(check.time + 'Z').toLocaleTimeString()}</div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProviderCard({ provider }: { provider: ProviderStatus }) {
  const statusColor = provider.status === 'healthy' ? 'text-green-400' : provider.status === 'unhealthy' ? 'text-red-400' : 'text-zinc-400';
  const statusLabel = provider.status === 'healthy' ? 'Operational' : provider.status === 'unhealthy' ? 'Down' : provider.status === 'disabled' ? 'Disabled' : 'Unknown';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium">{provider.name}</span>
          {provider.avg_latency_ms > 0 && (
            <Badge variant="secondary" className="text-xs font-normal">~{provider.avg_latency_ms}ms</Badge>
          )}
        </div>
        <span className={`text-sm font-medium ${statusColor}`}>{statusLabel}</span>
      </div>
      <UptimeBar history={provider.history} />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{provider.history.length > 0 ? new Date(provider.history[0].time + 'Z').toLocaleString() : ''}</span>
        <span>{provider.uptime_pct}% uptime</span>
        <span>{provider.last_check ? new Date(provider.last_check).toLocaleTimeString() : 'No checks yet'}</span>
      </div>
    </div>
  );
}

export default function StatusPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 15000,
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

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-6 py-12">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight mb-4">gSdm-R</h1>
          <OverallBadge status={data.status} />
        </div>

        {/* Stats bar */}
        <div className="flex justify-center gap-8 mb-8 text-sm text-muted-foreground">
          <span>Uptime: <strong className="text-foreground">{data.uptime}</strong></span>
          <span>Requests/h: <strong className="text-foreground">{data.stats.requests_last_hour}</strong></span>
          <span>Success: <strong className="text-foreground">{data.stats.success_rate_last_hour}%</strong></span>
          <span>Latency: <strong className="text-foreground">{data.stats.avg_latency_ms}ms</strong></span>
        </div>

        <Separator className="mb-8" />

        {/* Provider status cards */}
        <div className="space-y-6">
          {data.providers.map((p) => (
            <ProviderCard key={p.name} provider={p} />
          ))}
        </div>

        {data.providers.length === 0 && (
          <p className="text-center text-muted-foreground py-12">No providers configured yet.</p>
        )}

        {/* Footer */}
        <Separator className="mt-8 mb-4" />
        <p className="text-center text-xs text-muted-foreground">
          Last updated: {new Date(data.timestamp).toLocaleString()} · Auto-refreshes every 15s
        </p>
      </div>
    </div>
  );
}
