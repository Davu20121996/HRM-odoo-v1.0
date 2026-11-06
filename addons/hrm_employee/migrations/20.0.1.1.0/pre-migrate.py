"""MIGRATION MAU: them cot phone cho hrm.person + backfill du lieu cu.

Khi nao can thu muc migrations/ thay vi chi -u don gian?
- Them field don gian (Char, Float...)  -> KHONG can migration, ORM tu ADD COLUMN.
- Can backfill / doi du lieu cu / doi constraint / tach-gop bang
  -> CAN migration, chay tu dong khi -u + tang version trong __manifest__.

Cach chay:
  1. Them field phone vao models/person.py
  2. Tang version trong __manifest__.py: 20.0.1.0.0 -> 20.0.1.1.0
  3. Dat 2 file nay vao migrations/20.0.1.1.0/
  4. docker compose exec odoo odoo -d <DB> -u hrm_employee --stop-after-init
     Odoo tu chay pre-migrate (truoc khi ORM tao cot) roi post-migrate (sau).
"""

def migrate(cr, version):
    # pre: chay TRUOC khi ORM cap nhat cau truc bang.
    # Dung de don dep du lieu xau truoc khi dat NOT NULL / UNIQUE.
    cr.execute("SELECT column_name FROM information_schema.columns "
               "WHERE table_name='hrm_person' AND column_name='phone'")
    # Neu cot chua co thi cu de ORM tu tao o buoc sau, khong can lam gi.
    # Vi du don dep: chuan hoa SDT cu neu cot da ton tai tu ban cu.
    # (try/except de migration chay lai an toan - idempotent)
    try:
        cr.execute("UPDATE hrm_person SET phone=TRIM(phone) "
                   "WHERE phone IS NOT NULL AND phone <> TRIM(phone)")
    except Exception:
        cr.rollback()
