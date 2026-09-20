# Voice Agent Operations Dashboard

Responsive React dashboard for call activity, qualification results, transcripts, and Frappe CRM synchronization.

## Development

```bash
npm install
npm run dev
```

The development server runs at `http://localhost:5173` and proxies `/api` and `/health` to `http://localhost:8000`.

Set `VITE_API_BASE_URL` only when the API is hosted on a different origin. When `API_AUTH_TOKEN` is enabled on the backend, use the key button in the dashboard to store the bearer token in session storage.

## Production

```bash
npm run lint
npm run build
```

The included Dockerfile builds the static application and serves it through Nginx, proxying API requests to the `voice-agent` Compose service.
