# Apartment Portal — Marketing + BTL

Flask app for two teams:

- **Marketing** — manage the hub list, upload/assign apartments, manage the standee
  inventory, run reports.
- **BTL** — record one contact "collection" per assigned apartment (phone, designation,
  total units, available marketing campaigns) and track standee placement / collection.

## Run locally

```bash
python3 -m pip install -r requirements.txt
PORT=5055 python3 app.py        # http://127.0.0.1:5055
```

Local dev uses SQLite (`local_dev.db`, auto-created). On first run a marketing admin
is seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD` (default `admin` / `admin123`).

## Environment variables

| Var | Purpose |
|---|---|
| `FLASK_SECRET` | session signing key (any long random string) |
| `DATABASE_BACKEND` | `supabase` to use Supabase; unset ⇒ SQLite. Auto-on when `RENDER` is set. |
| `SUPABASE_URL` | `https://<ref>.supabase.co` (prod only) |
| `SUPABASE_KEY` | Supabase **service_role** key (prod only) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | seeded first admin, only when the `users` table is empty |

## Deploy (Render + Supabase)

1. **Supabase** — run `supabase_schema.sql` in the project's SQL editor before the
   first boot (the app queries `users` at startup).
2. **Render** — Web Service from this repo:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - Env vars: the table above (`DATABASE_BACKEND=supabase`, the two `SUPABASE_*`,
     `FLASK_SECRET`, `ADMIN_*`). `render.yaml` mirrors this.

### Known limitations

- **Uploads are ephemeral on Render.** Standee design / placement / damage photos are
  written to `static/uploads/` on the instance's local disk, which Render wipes on
  every deploy and restart. Durable storage needs Supabase Storage or S3/Cloudinary
  (a code change) or a Render persistent disk.
- The Supabase data layer (`db.SupabaseDatabase`) mirrors the SQLite one but has not
  been exercised against a live project — watch the first deploy's logs.
