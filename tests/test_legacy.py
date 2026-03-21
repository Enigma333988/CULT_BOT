import importlib
import os
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def load_legacy_module(base_dir: Path):
    os.environ["TOKEN"] = "test-token"
    os.environ["ADMIN_CHAT_ID"] = "1001"
    os.environ.pop("MAX_TOKEN", None)
    os.environ.pop("MAX_ADMIN_CHAT_ID", None)
    os.environ["TIMEZONE"] = "UTC"
    os.environ["ORDERS_FILE"] = str(base_dir / "orders.json")
    os.environ["STATE_FILE"] = str(base_dir / "bot_state.json")
    os.environ["CATALOG_FILE"] = str(base_dir / "catalog.json")
    os.environ["ARCHIVE_DIR"] = str(base_dir / "archive")

    module = importlib.import_module("app.legacy")
    module = importlib.reload(module)

    for wrapper_name in (
        "app.config",
        "app.domain",
        "app.handlers",
        "app.main",
        "app.platforms",
        "app.polling",
        "app.state",
        "app.ui",
    ):
        if wrapper_name in sys.modules:
            importlib.reload(sys.modules[wrapper_name])

    return module


class LegacyTests(unittest.TestCase):
    def test_create_order_persists_and_archives(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))

            order = legacy.create_order(
                title="Шкаф",
                total_price=120000,
                paid_amount=60000,
                has_delivery=True,
                notes="Позвонить перед доставкой",
                created_via="telegram",
            )

            self.assertEqual(order["id"], 1)
            self.assertEqual(order["paid_amount"], 60000)
            self.assertEqual(legacy.calculate_payment_percent(order), 50)
            self.assertTrue(Path(legacy.ORDERS_FILE).exists())
            self.assertTrue(legacy.archive_file_path(order["id"]).exists())

    def test_add_payment_is_capped_by_total(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))
            order = legacy.create_order(
                title="Стол",
                total_price=50000,
                paid_amount=45000,
                has_delivery=False,
                notes="",
                created_via="telegram",
            )

            legacy.add_payment(order, 10000)

            self.assertEqual(order["paid_amount"], 50000)
            self.assertEqual(legacy.calculate_payment_percent(order), 100)

    def test_build_report_uses_archived_orders(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))
            order = legacy.create_order(
                title="Комод",
                total_price=70000,
                paid_amount=35000,
                has_delivery=False,
                notes="",
                created_via="telegram",
            )
            order["created_at"] = "2026-01-15T12:00:00+00:00"
            order["updated_at"] = "2026-01-15T12:00:00+00:00"
            legacy.persist_order(order)
            legacy.complete_order(order)

            start_dt, end_dt = legacy.parse_russian_period("1 января 2026_31 января 2026")
            report = legacy.build_report_text(start_dt, end_dt)

            self.assertIn("1", report)
            self.assertIn("70.000", report)
            self.assertIn("35.000", report)

    def test_load_json_quarantines_corrupted_file(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))
            broken_file = Path(temp_dir) / "broken.json"
            broken_file.write_text("{", encoding="utf-8")

            payload = legacy.load_json(broken_file, {"fallback": True})

            self.assertEqual(payload, {"fallback": True})
            backups = list(Path(temp_dir).glob("broken.json.corrupted.*"))
            self.assertEqual(len(backups), 1)

    def test_run_telegram_polling_acknowledges_only_processed_updates(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))
            stop_event = threading.Event()
            processed: list[int] = []

            def fake_fetch():
                stop_event.set()
                return [{"update_id": 10}, {"update_id": 11}]

            def fake_handle(update):
                processed.append(update["update_id"])
                if update["update_id"] == 11:
                    raise RuntimeError("boom")

            legacy.fetch_telegram_updates = fake_fetch
            legacy.handle_telegram_update = fake_handle

            legacy.run_telegram_polling(stop_event)

            self.assertEqual(processed, [10, 11])
            self.assertEqual(legacy.state["telegram_last_update_id"], 10)

    def test_run_max_polling_updates_marker_only_after_successful_batch(self):
        with TemporaryDirectory() as temp_dir:
            legacy = load_legacy_module(Path(temp_dir))
            stop_event = threading.Event()
            legacy.state["max_marker"] = "old-marker"

            def fake_fetch_batch():
                stop_event.set()
                return [{"timestamp": 1}, {"timestamp": 2}], "new-marker"

            def fake_handle(update):
                if update["timestamp"] == 2:
                    raise RuntimeError("boom")

            legacy.fetch_max_updates_batch = fake_fetch_batch
            legacy.handle_max_update = fake_handle

            legacy.run_max_polling(stop_event)

            self.assertEqual(legacy.state["max_marker"], "old-marker")


if __name__ == "__main__":
    unittest.main()
