export interface Provider {
  id: number;
  name: string;
  base_url: string;
  api_key_masked: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderCreate {
  name: string;
  base_url: string;
  api_key: string;
}

export interface ProviderUpdate {
  name?: string;
  base_url?: string;
  api_key?: string;
  is_active?: boolean;
}

export interface ModelProviderMapping {
  provider_id: number;
  provider_name?: string;
  provider_model: string;
  priority: number;
}

export interface Model {
  id: number;
  name: string;
  load_balance: 'priority' | 'round-robin' | 'weighted-random';
  providers: ModelProviderMapping[];
  created_at: string;
  updated_at: string;
}

export interface ModelCreate {
  name: string;
  providers: ModelProviderMapping[];
  load_balance?: 'priority' | 'round-robin' | 'weighted-random';
}

export interface ModelUpdate {
  name?: string;
  providers?: ModelProviderMapping[];
  load_balance?: 'priority' | 'round-robin' | 'weighted-random';
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface PlaygroundTestResult {
  success: boolean;
  latency_ms: number;
  response_text: string | null;
  error: string | null;
  provider_name: string;
  model_name: string;
}

export interface DisabledProviderModel {
  id: number;
  provider_id: number;
  provider_name: string;
  model_name: string;
  created_at: string;
}
