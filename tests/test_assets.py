"""Run assets (the ad image) live in the database, per run."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.cycle import store_ad_image
from storage import get_asset, save_asset, start_run, using_run
from storage.db import normalise_url


def test_an_asset_round_trips_and_is_replaced_not_piled_up():
    run = start_run(mode="new_idea")
    save_asset("ad_image", b"first", "image/jpeg", run_id=run)
    save_asset("ad_image", b"second", "image/png", run_id=run)
    assert get_asset(run, "ad_image") == (b"second", "image/png")
    assert get_asset(run, "other") is None


def test_each_run_keeps_its_own_image():
    a, b = start_run(mode="new_idea"), start_run(mode="new_idea")
    save_asset("ad_image", b"A", run_id=a)
    save_asset("ad_image", b"B", run_id=b)
    assert get_asset(a, "ad_image")[0] == b"A" and get_asset(b, "ad_image")[0] == b"B"


def test_store_ad_image_reads_the_file_into_the_current_run(tmp_path):
    image = tmp_path / "cycle_1.png"
    image.write_bytes(b"PNGDATA")
    run = start_run(mode="new_idea")
    with using_run(run):
        store_ad_image(SimpleNamespace(ad_image_path=str(image)))
    assert get_asset(run, "ad_image") == (b"PNGDATA", "image/png")


def test_store_ad_image_ignores_a_missing_file_or_no_image(tmp_path):
    run = start_run(mode="new_idea")
    with using_run(run):
        store_ad_image(SimpleNamespace(ad_image_path=None))
        store_ad_image(SimpleNamespace(ad_image_path=str(tmp_path / "gone.jpg")))
    assert get_asset(run, "ad_image") is None


def test_hosted_postgres_urls_name_the_installed_driver():
    assert normalise_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalise_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_url("sqlite:///x.db") == "sqlite:///x.db"
