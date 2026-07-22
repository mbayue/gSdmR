import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useUsageStats } from '../hooks/useUsage';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

export default function UsagePage() {
  const [days, setDays] = useState(7);
  const { data, isLoading } = useUsageStats(days);

  if (isLoading || !data) {
    return <div className="text-muted-foreground text-sm">Loading usage data...</div>;
  }

  const { summary, by_model, by_key, recent } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Usage</h1>
          <p className="text-sm text-muted-foreground">API request metrics and token consumption</p>
        </div>
        <div className="flex gap-1">
          {[1, 7, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                days === d ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary/50'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Requests</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.total_requests.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {summary.successful} ok / {summary.failed} failed
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.total_tokens.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {summary.total_prompt_tokens.toLocaleString()} in / {summary.total_completion_tokens.toLocaleString()} out
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Avg Latency</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{summary.avg_latency_ms}ms</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Success Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summary.total_requests > 0
                ? Math.round((summary.successful / summary.total_requests) * 100)
                : 0}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Requests by Model */}
        {by_model.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Requests by Model</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={by_model}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="model" tick={{ fill: '#888', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#888', fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: '#1c1c1c', border: '1px solid #333' }} />
                  <Bar dataKey="requests" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Tokens by Model (Pie) */}
        {by_model.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Token Distribution</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-center">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={by_model}
                    dataKey="tokens"
                    nameKey="model"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name }) => name as string}
                    labelLine={false}
                  >
                    {by_model.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1c1c1c', border: '1px solid #333' }} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>

      {/* By Key Table */}
      {by_key.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Usage by API Key</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Requests</TableHead>
                  <TableHead>Tokens</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {by_key.map((k) => (
                  <TableRow key={k.key_id}>
                    <TableCell className="font-medium">{k.key_name}</TableCell>
                    <TableCell>{k.requests.toLocaleString()}</TableCell>
                    <TableCell>{k.tokens.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Recent Requests */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Recent Requests</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Endpoint</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Tokens</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(r.time + 'Z').toLocaleTimeString()}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.model}</TableCell>
                  <TableCell className="text-xs">{r.endpoint}</TableCell>
                  <TableCell>
                    <Badge variant={r.status < 300 ? 'default' : 'destructive'} className="text-xs">
                      {r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">{r.latency_ms}ms</TableCell>
                  <TableCell className="text-xs">{r.tokens}</TableCell>
                </TableRow>
              ))}
              {recent.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="h-16 text-center text-muted-foreground">
                    No requests recorded yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
