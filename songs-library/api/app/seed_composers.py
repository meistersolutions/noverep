"""Optional seed script — run later when ready to pull Wikidata."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, init_db
from app.services.discover import discover_many

SEEDS = ["Ilaiyaraaja", "A. R. Rahman", "Yuvan Shankar Raja"]


async def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        print("Discovering:", ", ".join(SEEDS))
        results = await discover_many(db, SEEDS, limit_per_seed=300)
        for r in results:
            print(
                f"  {r.seed}: entity={r.entity_label}({r.entity_id}) "
                f"found={r.found} inserted={r.inserted} skipped={r.skipped}"
                + (f" ERROR={r.error}" if r.error else "")
            )
        print(
            "Done. total_inserted=",
            sum(r.inserted for r in results),
            "total_skipped=",
            sum(r.skipped for r in results),
        )
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
