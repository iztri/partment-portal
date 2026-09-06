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
   first boot (the app queries `users` at startup). It drops and recreates every
   table. To add the newer bits to an **existing** database without wiping it:
   ```sql
   alter table users add column if not exists is_admin boolean not null default false;
   alter table apartments add column if not exists apartment_code text not null default '';
   create table if not exists user_permissions (
       id bigint generated always as identity primary key,
       username text not null, feature text not null,
       level text not null default 'edit' check (level in ('none','read','edit')),
       unique (username, feature));
   create table if not exists hubs (
       hub_id bigint primary key, hub_name text not null unique,
       created_at text not null default '');
   alter table standee_assignments add column if not exists quantity_missing integer not null default 0;
   alter table standee_assignments add column if not exists redeployed_to bigint;
   update users set is_admin = true where username = 'gowtham';
   ```
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
