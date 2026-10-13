# InternPilot dashboard

Next.js app over the same database as the worker. Locally it reads `../internpilot.db` (no config); on Vercel set
`DATABASE_URL` (Supabase transaction pooler), `DASHBOARD_PASSWORD` and `DASHBOARD_SECRET` (see `.env.example`).

```bash
npm install && npm run dev      # http://localhost:3000
```
Buttons queue rows in the `tasks` table; the worker on your Mac runs them within seconds.
