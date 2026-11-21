# API reference

The running server's `/docs` and `/openapi.json` are the authoritative schemas. Prefix application endpoints with `/api/v1`; list endpoints return JSON arrays. Authenticate with `Authorization: Bearer <access_token>`, or with the HttpOnly `atlas_session` cookie set by login/register/demo/verify-email. Cookie-authenticated POST/PUT/PATCH/DELETE requests must send `X-CSRF-Token` (the `csrf_token` returned in the auth response, or by `GET /auth/me` when cookie-authenticated); Bearer requests need no CSRF header. Hosted cookies are `SameSite=None; Secure`, which cross-domain frontends may lose to ITP/third-party-cookie blocking; prefer one parent domain.

| Method/path | Purpose |
|---|---|
| POST `/auth/register`, `/auth/login`, `/auth/demo` | Create/login a workspace account or enter configured read-only demo. Responses carry `access_token`, `csrf_token` and the session cookie. With email verification required, register returns 202 `{"verification_required": true}` (no session) and login of an unverified user returns 403 `email_not_verified` |
| POST `/auth/verify-email` | Body `{token}`. Marks the email verified and responds like login; invalid or expired (24h) token returns 400 |
| POST `/auth/resend-verification` | Body `{email}`. Always 202 (no account enumeration); sends only for existing unverified users |
| GET `/auth/me` | Current principal |
| POST `/auth/logout` | Revoke all tokens issued to the caller (token version bump) and clear the session cookie |
| POST `/auth/change-password` | Body `current_password`, `new_password` (min 12). Revokes old tokens, clears the cookie and returns a fresh bearer token |
| DELETE `/admin/members/{user_id}` | Admin removes a workspace member; the last admin cannot be removed (409). Their tokens stop working in that workspace |
| GET `/organizations`, `/workspaces` | Authorized organization/workspace context |
| GET/POST `/collections` | List/create collections |
| GET/POST `/documents` | List or upload multipart file and access scope |
| GET/DELETE `/documents/{id}` | Read metadata or request deletion |
| GET `/documents/{id}/source` | Authorized original source |
| POST `/documents/{id}/reindex` | Queue new ingestion attempt |
| GET `/ingestion-jobs` | Inspect persisted processing state |
| POST `/ingestion-jobs/run` | Admin bounded worker invocation |
| POST `/ingestion-jobs/{job_id}/retry` | Requeue a failed job in the current workspace as an admin |
| GET `/documents/{doc_id}/permission-options` | List workspace members, groups, and collections available to a document editor |
| PATCH `/documents/{doc_id}/permissions` | Update the document’s visibility, allowed members and groups, and collection |
| GET/POST `/chat/sessions` | List/create conversations |
| GET/DELETE `/chat/sessions/{id}` | Read/delete owned conversation |
| POST `/chat`, `/chat/stream` | Grounded answer or SSE status/result/error/done stream |
| POST `/search`, `/search/debug` | Ranked authorized evidence and diagnostics |
| GET `/evaluations`, `/analytics`, `/admin`, `/settings`, `/health` | Actual reports, telemetry and operational state |
| POST `/feedback` | Create or update your rating of an assistant answer in your conversation |

Search body: `{"query":"How does leave approval work?","strategy":"hybrid","top_k":5,"rerank":true}`. Chat body uses `question` and optional `session_id` with the same retrieval controls. Errors use an HTTP error status and `detail`; consumers must not display an error as a completed answer. The streaming endpoint reports progress and a final answer, not necessarily individual model tokens; any failure emits `error` then `done`, and `: keep-alive` comment lines are sent every `SSE_HEARTBEAT_SECONDS` (15) while the answer is generated.

Search responses and chat `metrics` include `stale_index_chunks`: readable chunks excluded because they were indexed under a different embedding signature than the running pipeline. A non-zero value with empty results means documents need reindexing, not that nothing matched. Uploads return 413 above `MAX_UPLOAD_BYTES` and 403 once the workspace reaches `MAX_WORKSPACE_DOCUMENTS` / `MAX_WORKSPACE_BYTES`. Auth endpoints are limited to 20 POSTs per minute per client IP (429 with `Retry-After`); `/auth/demo` also caps new demo accounts at `DEMO_ACCOUNTS_PER_HOUR`.
