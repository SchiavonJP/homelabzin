# Upstream

Xereta adapts the FastAPI/React application architecture and password/JWT helpers
from https://github.com/fastapi/full-stack-fastapi-template at
`aabb90126964a164e02aff39e7c385bb0598236d` (MIT; see LICENSE).

The application keeps the template's FastAPI, SQLModel, PostgreSQL, React,
TypeScript, Vite, Tailwind, TanStack Query and generated-client approach. The
generic Items/admin/signup/email screens are replaced by the knowledge workflow.
It uses existing homelab PostgreSQL and ingress rather than provisioning their
template equivalents. Hindsight remains a separate service.
