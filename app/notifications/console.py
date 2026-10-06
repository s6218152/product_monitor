from app.monitors.marketplace_monitor import MonitorResult


def notify(result: MonitorResult) -> None:
    print(f"Found {result.found} listings")
    print(f"New: {result.new}")
    print(f"Existing: {result.existing}")
