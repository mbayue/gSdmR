# Requirements Document

## Introduction

An AI API router system that acts as a proxy accepting OpenAI and Anthropic API format requests and routes them to multiple backend providers using priority-based fallback. The system includes a FastAPI backend for request routing and a React (Vite) dashboard for managing providers and models via CRUD operations. Authentication is enforced via API keys for router access and username/password login for the dashboard.

## Glossary

- **Router**: The FastAPI backend service that receives incoming API requests and forwards them to the appropriate backend provider.
- **Dashboard**: The React (Vite) web application that provides a UI for managing providers, models, and their configurations.
- **Provider**: A backend AI API endpoint (e.g., OpenAI-compatible service) identified by a name, base URL, and API key.
- **Model**: A named AI model identifier that maps to one or more providers with a defined priority order.
- **Priority**: A numeric ordering that determines which provider the Router attempts first for a given model; lower numbers indicate higher priority.
- **Fallback**: The mechanism by which the Router tries the next provider in priority order when the current provider fails.
- **API_Key**: A secret token required in the request header to authenticate calls to the Router.
- **User**: A person with dashboard login credentials who manages providers and models.
- **Request**: An incoming HTTP call to the Router in either OpenAI or Anthropic API format.
- **Provider_Failure**: A condition where a provider returns a non-2xx HTTP status or times out.

## Requirements

### Requirement 1: API Request Proxying

**User Story:** As a developer, I want to send requests in OpenAI or Anthropic API format to a single endpoint, so that I don't need to manage multiple provider integrations.

#### Acceptance Criteria

1. WHEN a Request is received at the chat completions endpoint in OpenAI format, THE Router SHALL forward the Request to the appropriate provider and return the provider response in OpenAI format.
2. WHEN a Request is received at the messages endpoint in Anthropic format, THE Router SHALL forward the Request to the appropriate provider and return the provider response in Anthropic format.
3. THE Router SHALL preserve all request parameters (model, messages, temperature, max_tokens, stream) when forwarding to the backend provider.
4. WHEN a streaming Request is received, THE Router SHALL stream the response back to the client as server-sent events.
5. WHEN a Request is received at the responses endpoint in OpenAI Responses API format (using `input` field and `model` field), THE Router SHALL forward the Request to the appropriate provider and return the provider response in OpenAI Responses API format (with `output` array).
6. THE Router SHALL preserve all Responses API parameters (input, model, temperature, max_output_tokens, top_p, instructions, tools, tool_choice, stream) when forwarding to the backend provider.

### Requirement 2: Priority-Based Routing

**User Story:** As a developer, I want requests to be routed to the highest-priority provider for a given model, so that I get the best available service with automatic failover.

#### Acceptance Criteria

1. WHEN a Request specifies a model, THE Router SHALL route the Request to the provider with the highest priority (lowest priority number) mapped to that model.
2. WHEN a Provider_Failure occurs, THE Router SHALL attempt the next provider in priority order for the same model.
3. IF all providers for a model fail, THEN THE Router SHALL return an error response with HTTP status 503 and a descriptive error message.
4. THE Router SHALL attempt each provider at most once per request before moving to the next in priority order.

### Requirement 3: Router Authentication

**User Story:** As a system administrator, I want the router to require API key authentication, so that only authorized clients can send requests.

#### Acceptance Criteria

1. THE Router SHALL require a valid API_Key in the Authorization header (Bearer token) or x-api-key header for all proxied requests.
2. IF a Request is received without a valid API_Key, THEN THE Router SHALL return HTTP status 401 with an error message indicating authentication failure.
3. THE Router SHALL validate the API_Key against configured keys before processing any request.

### Requirement 4: Provider Management (CRUD)

**User Story:** As an administrator, I want to add, view, edit, and delete providers through the dashboard, so that I can manage which backend services are available for routing.

#### Acceptance Criteria

1. THE Dashboard SHALL display a list of all configured providers with their name, base URL, and status.
2. WHEN a User submits the add provider form with a name, base URL, and API key, THE Dashboard SHALL create a new provider record.
3. WHEN a User edits a provider, THE Dashboard SHALL update the provider name, base URL, or API key as specified.
4. WHEN a User deletes a provider, THE Dashboard SHALL remove the provider record and all associated model mappings.
5. THE Dashboard SHALL validate that provider name and base URL are non-empty before submission.

### Requirement 5: Model Management (CRUD)

**User Story:** As an administrator, I want to add, view, edit, and delete models and their provider mappings through the dashboard, so that I can control routing behavior.

#### Acceptance Criteria

1. THE Dashboard SHALL display a list of all configured models with their mapped providers and priority order.
2. WHEN a User submits the add model form with a model name and at least one provider mapping with priority, THE Dashboard SHALL create a new model record.
3. WHEN a User edits a model, THE Dashboard SHALL allow updating the model name, adding or removing provider mappings, and reordering priorities.
4. WHEN a User deletes a model, THE Dashboard SHALL remove the model record and all its provider mappings.
5. THE Dashboard SHALL enforce that each model has at least one provider mapping with a unique priority value per provider.

### Requirement 6: Dashboard Authentication

**User Story:** As an administrator, I want the dashboard to require login credentials, so that only authorized users can manage the system configuration.

#### Acceptance Criteria

1. WHEN a User navigates to the Dashboard without an active session, THE Dashboard SHALL display a login form requesting username and password.
2. WHEN a User submits valid credentials, THE Dashboard SHALL create a session and redirect to the main management view.
3. IF a User submits invalid credentials, THEN THE Dashboard SHALL display an error message and remain on the login page.
4. WHEN a User clicks logout, THE Dashboard SHALL invalidate the session and redirect to the login page.
5. THE Dashboard SHALL protect all management routes so that unauthenticated requests are redirected to the login page.

### Requirement 7: Initial Provider Configuration

**User Story:** As a system administrator, I want the system to come pre-configured with initial providers, so that I can start routing requests immediately after setup.

#### Acceptance Criteria

1. THE Router SHALL include the following providers in the default configuration: "bluesminds" with base URL "https://api.bluesminds.com/v1/", "freemodel" with base URL "https://api.freemodel.dev/v1/", "forge-gateway" with base URL "https://forge-gateway-api.fly.dev/v1/", and "iamhc" with base URL "https://api.iamhc.cn/v1/".
2. THE Dashboard SHALL allow the User to modify or remove default providers after initial setup.

### Requirement 8: Provider API Management

**User Story:** As an administrator, I want to store and manage API keys for each provider, so that the router can authenticate with backend services.

#### Acceptance Criteria

1. THE Dashboard SHALL store an API key for each provider securely.
2. WHEN the Router forwards a Request to a provider, THE Router SHALL include the provider API key in the Authorization header of the outgoing request.
3. THE Dashboard SHALL mask the API key value in the UI, showing only the last four characters.

### Requirement 9: Error Handling and Timeouts

**User Story:** As a developer, I want the router to handle provider errors gracefully, so that transient failures don't interrupt my application.

#### Acceptance Criteria

1. WHEN a provider does not respond within 30 seconds, THE Router SHALL treat the request as a Provider_Failure and proceed to the next provider in priority order.
2. IF a provider returns an HTTP 429 (rate limited) status, THEN THE Router SHALL treat the response as a Provider_Failure and attempt the next provider.
3. IF a provider returns an HTTP 5xx status, THEN THE Router SHALL treat the response as a Provider_Failure and attempt the next provider.
4. WHEN the Router encounters a Provider_Failure, THE Router SHALL log the failure including the provider name, error type, and timestamp.
