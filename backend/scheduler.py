"""
Scheduler: spouští refresh cen v pravidelných intervalech, pak exportuje JSON a pushuje na GitHub.
Spuštění: python scheduler.py  (z backend/ adresáře)
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime

from app.database import init_db
from app.scrapers.dispatcher import refresh_all_items

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

INTERVAL_HOURS = 6
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def export_and_push():
    from export_json import export
    try:
        export()
    except Exception as e:
        logger.error(f"Export JSON selhal: {e}")
        return

    try:
        subprocess.run(["git", "add", "data/"], cwd=REPO_ROOT, check=True, capture_output=True)
        # Push pouze pokud jsou skutečné změny
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
        if diff.returncode != 0:
            msg = f"data: ceny {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT, check=True, capture_output=True)
            subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True, capture_output=True)
            logger.info("✅ Data pushnutá na GitHub")
        else:
            logger.info("ℹ️ Žádné změny k pushování")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"❌ Git selhal: {stderr}")


async def run():
    init_db()
    logger.info(f"Scheduler spuštěn, interval: {INTERVAL_HOURS}h")

    while True:
        logger.info("▶ Spouštím refresh všech cen...")
        results = await refresh_all_items()
        total_ok = sum(r["scraped"] for r in results)
        total_err = sum(len(r["errors"]) for r in results)
        logger.info(f"✅ Scraping hotovo: {total_ok} cen, {total_err} chyb")

        export_and_push()

        await asyncio.sleep(INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    asyncio.run(run())
