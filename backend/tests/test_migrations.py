from sqlalchemy import text


def test_schema_and_extensions(db):
    with db.connect() as c:
        ext = {r[0] for r in c.execute(text("SELECT extname FROM pg_extension"))}
        assert {"postgis", "pg_trgm", "unaccent"} <= ext
        assert c.execute(text("SELECT f_unaccent('Žižkov Řeporyje')")).scalar() == "Zizkov Reporyje"
