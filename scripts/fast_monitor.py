"""Long-running fast monitor; do not run beside the legacy cron runner."""
import logging
import os
from pathlib import Path
import signal
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app.config import load_settings
from app.database.repository import ListingRepository
from app.fast_monitor import FastMonitor, Scheduler, BrowserRecoveryNeeded
from app.runtime import monitor_lock
from app.monitor_status import report_status


def positive_env(name, default):
    value = float(os.getenv(name, default))
    if not 0 < value < float('inf'):
        raise ValueError(f'{name} must be positive and finite')
    return value


STOP_REQUESTED = False


def stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main():
    os.chdir(PROJECT)
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    marketplace_interval = positive_env('FAST_MARKETPLACE_INTERVAL_SECONDS', '120')
    group_interval = positive_env('FAST_GROUP_INTERVAL_SECONDS', '300')
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise ValueError('Telegram credentials are required')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    from playwright.sync_api import sync_playwright
    try:
        with monitor_lock(settings.monitor_lock_path) as acquired:
            if not acquired:
                logging.error('fast_monitor_start_blocked lock_busy')
                return 1
            scheduler = Scheduler(settings.facebook_group_urls, marketplace_interval=marketplace_interval, group_interval=group_interval)
            with report_status(settings, scheduler) as reporter, ListingRepository(settings.database_path) as repository, sync_playwright() as p:
                monitor = None
                while not STOP_REQUESTED:
                    context = p.chromium.launch_persistent_context(settings.facebook_profile_dir, headless=settings.facebook_headless, locale='zh-TW')
                    try:
                        logging.info('fast_monitor_started marketplace_interval=%s group_interval=%s', marketplace_interval, group_interval)
                        if monitor is None:
                            monitor = FastMonitor(context, repository, settings)
                        else:
                            monitor.attach_context(context)
                        monitor.status_reporter = reporter
                        monitor.run(scheduler, should_stop=lambda: STOP_REQUESTED)
                    except BrowserRecoveryNeeded:
                        logging.warning('browser_recovery_requested pending_details_preserved=true')
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
                    logging.info('browser_recycle interval_hours=4')
                    if not STOP_REQUESTED:
                        time.sleep(2)
                logging.info('fast_monitor_stopped')
                return 0
    except KeyboardInterrupt:
        logging.info('fast_monitor_stopped')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
