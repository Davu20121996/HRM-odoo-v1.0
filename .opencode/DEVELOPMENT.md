# Odoo HRM Development Quick Reference

## Common Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# Restart Odoo (after code changes)
docker compose restart odoo

# View logs
docker compose logs -f odoo

# Upgrade module (recompile assets, reload views)
docker compose exec odoo odoo -u hrm_theme --stop-after-init -d hrm-odoo --db_host=db --db_user=odoo --db_password=odoo

# Access container shell
docker compose exec odoo bash

# Access PostgreSQL
docker compose exec db psql -U odoo -d hrm-odoo
```

## Development Workflow

### SCSS Changes (in `addons/hrm_theme/static/src/scss/`)
1. Edit `.scss` files
2. Run upgrade command OR just restart + hard refresh browser (`Ctrl+Shift+R`)
3. Assets auto-compile in dev mode

### Python Changes (models, views, controllers)
1. Edit `.py` / `.xml` files
2. Run upgrade command

### JavaScript/OWL Changes (in `addons/hrm_theme/static/src/js/`, `static/src/xml/`)
1. Edit `.js` / `.xml` files
2. Run upgrade command (required for JS bundle rebuild)
3. Hard refresh browser

## Key Files

| Type | Location |
|------|----------|
| Main module | `addons/hrm_theme/__manifest__.py` |
| Models | `addons/hrm_theme/models/` |
| Views | `addons/hrm_theme/views/` |
| SCSS | `addons/hrm_theme/static/src/scss/` |
| JS Components | `addons/hrm_theme/static/src/js/` |
| OWL Templates | `addons/hrm_theme/static/src/xml/` |
| Dashboard | `addons/hrm_theme/static/src/js/dashboard/hr_dashboard.js` |
| Card List Widget | `addons/hrm_theme/static/src/js/fields/hrm_card_list.js` |

## Common Issues

### "Missing kanban-box template" Error
- Don't use inline `<kanban>` views in form views
- Use custom widget `hrm_card_list` instead
- Or define separate kanban views with unique `t-name`

### Assets Not Updating
- Hard refresh: `Ctrl+Shift+R` (Windows) / `Cmd+Shift+R` (Mac)
- Or enable Developer Mode in Odoo Settings

### RPC_ERROR on Module Upgrade
- Check `docker compose logs odoo` for details
- Common: duplicate view records in DB
- Fix: Delete duplicate `ir_ui_view` records via SQL

## Database Access

```bash
# List databases
docker compose exec db psql -U odoo -l

# Query example
docker compose exec db psql -U odoo -d hrm-odoo -c "SELECT * FROM smb_employee LIMIT 5;"
```

## Login Credentials
- URL: http://localhost:8069
- Email: thienthanma521@gmail.com
- Password: admin
- Master Password: admin (for db management)