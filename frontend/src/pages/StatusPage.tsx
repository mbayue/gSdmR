import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Separator } from '../components/ui/separator';

interface ProviderStatus {
  name: string;
  status: string;
  last_check: string | null;
}

interface StatusData {
  status: string;
  uptime: string;
  uptime_seconds: number;
  providers: ProviderStatus[];
  stats: {
    models_configured: number;
    active_api_keys: number;
    requests_last_hour: number;
    success_rate_last_hour: number;
    avg_latency_ms: number;
  };
  timestamp: string;
}

// Use raw axios (no JWT interceptor) since this is public
const fetchStatus = async (): Promise<StatusData> => {
  const res = await axios.get('/status');
  return res.data;
};

function StatusBadge({ status }: { status: string }) {
  if (status === 'operational') return <Badge className="bg-green-600 text-white">Operational</Badge>;
  if (status === 'degraded') return <Badge className="bg-yellow-600 text-white">Degraded</Badge>;
  if (status === 'healthy') return <Badge className="bg-green-600 text-white">Healthy</Badge>;
  if (status === 'unhealthy') return <Badge variant="destructive">Unhealthy</Badge>;
  if (status === 'disabled') return <Badge variant="secondary">Disabled</Badge>;
  if (status === 'active') return <Badge className="bg-green-600 text-white">Active</Badge>;
  if (status === 'inactive') return <Badge variant="secondary">Inactive</Badge>;
  return <Badge variant="secondary">{status}</Badge>;
}

export default function StatusPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
    refetchInterval: 15000, // refresh every 15s
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
        <Card className="w-96">
          <CardContent className="pt-6 text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-lg font-bold text-destructive">Service Unavailable</h2>
            <p className="text-sm text-muted-foreground mt-2">Unable to reach the API. Please try again later.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-6 py-12">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight mb-2">gSdm-R Status</h1>
          <div className="flex items-center justify-center gap-3">
            <StatusBadge status={data.status} />
            <span className="text-sm text-muted-foreground">Uptime: {data.uptime}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4 mb-8">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">Requests (1h)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{data.stats.requests_last_hour}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">Success Rate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{data.stats.success_rate_last_hour}%</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">Avg Latency</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{data.stats.avg_latency_ms}ms</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">Models</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-xl font-bold">{data.stats.models_configured}</div>
            </CardContent>
          </Card>
        </div>

        {/* Providers */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Provider Status</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Check</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.providers.map((p) => (
                  <TableRow key={p.name}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell><StatusBadge status={p.status} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {p.last_check ? new Date(p.last_check).toLocaleTimeString() : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Footer */}
        <Separator className="mb-4" />
        <p className="text-center text-xs text-muted-foreground">
          Last updated: {new Date(data.timestamp).toLocaleString()} · Auto-refreshes every 15s
        </p>
      </div>
    </div>
  );
}
