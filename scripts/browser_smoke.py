"""Exercise the demo through the browser and optionally refresh README screenshots."""

from argparse import ArgumentParser
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import build_opener, ProxyHandler

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def demo_server():
    with TemporaryDirectory(prefix="enterprise-data-hub-") as state:
        env = {**os.environ, "HUB_STATE": state}
        subprocess.run([sys.executable, "-m", "hub", "seed", "--with-incident"],
                       cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "hub.api:app", "--host", "127.0.0.1",
                                    "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        opener = build_opener(ProxyHandler({}))
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("The web process stopped unexpectedly.")
                try:
                    with opener.open(f"{base}/health", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("The app did not become healthy.")
            yield base
        finally:
            process.terminate()
            process.wait(timeout=8)


def check_workspace(page, base, capture):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for path, title, screenshot in [
        ("overview", "Platform overview", "01-overview.png"),
        ("product/shipment-reliability/lineage", "End-to-end lineage", "02-lineage.png"),
        ("run/4", "Run #4", "03-quality-gate.png"),
        ("delivery", "Delivery roadmap", "04-roadmap.png"),
    ]:
        page.goto(f"{base}/#{path}")
        expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
        if capture:
            page.screenshot(path=ROOT / "assets" / screenshot, full_page=True, animations="disabled")

    page.get_by_role("link", name="Data catalogue", exact=True).click()
    page.get_by_role("combobox", name="Owning domain").select_option("Finance")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_role("heading", name="Freight Spend")).to_be_visible()
    expect(page.get_by_role("heading", name="Returns Pulse")).to_have_count(0)
    page.get_by_role("link", name="Open product").click()
    page.get_by_label("Region").select_option("WEST")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.get_by_role("link", name="Download CSV")).to_have_attribute("href", "/api/products/freight-spend/download?dimension=WEST")
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="Download CSV").click()
    assert downloaded.value.suggested_filename == "freight-spend-v1.0.0.csv"

    page.get_by_role("link", name="Operations", exact=True).click()
    page.get_by_role("combobox", name="Data product").select_option("freight-spend")
    page.get_by_role("combobox", name="Source scenario").select_option("negative-money")
    page.get_by_role("button", name="Run pipeline").click()
    expect(page.get_by_text("The run was blocked.", exact=False)).to_be_visible()
    expect(page.get_by_text("Non-negative monetary amount", exact=True)).to_be_visible()
    page.get_by_role("link", name="Back to operations").click()
    page.get_by_role("button", name="Acknowledge").first.click()
    expect(page.get_by_role("table").first.get_by_text("acknowledged", exact=True)).to_be_visible()
    page.get_by_role("combobox", name="Data product").select_option("freight-spend")
    page.get_by_role("button", name="Run pipeline").click()
    expect(page.get_by_text("The snapshot became current", exact=False)).to_be_visible()

    page.get_by_role("combobox", name="Simulated role").select_option("operations-owner")
    page.get_by_role("link", name="Governance", exact=True).click()
    page.get_by_role("textbox", name="Business rationale").fill("Add room for an optional consumer annotation.")
    page.get_by_role("button", name="Submit proposal").click()
    expect(page.get_by_text("pending", exact=True)).to_be_visible()
    page.get_by_role("combobox", name="Simulated role").select_option("governance-steward")
    page.get_by_role("textbox", name="Review note").fill("All existing consumer columns and grain are preserved.")
    page.get_by_role("button", name="Approve").click()
    expect(page.get_by_text("approved", exact=True)).to_be_visible()
    if capture:
        page.screenshot(path=ROOT / "assets/05-governance.png", full_page=True, animations="disabled")
    page.get_by_role("link", name="Open contract").click()
    expect(page.get_by_text("The approved version will be served", exact=False)).to_be_visible()
    page.get_by_role("combobox", name="Simulated role").select_option("platform-operator")
    page.get_by_role("link", name="Operations", exact=True).click()
    page.get_by_role("button", name="Run pipeline").click()
    expect(page.get_by_text("The snapshot became current", exact=False)).to_be_visible()
    page.goto(f"{base}/#product/shipment-reliability")
    expect(page.get_by_role("columnheader", name="reporting note")).to_be_visible()
    assert not errors, errors


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    with demo_server() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.getenv("HUB_CHROMIUM_EXECUTABLE"),
                                           args=os.getenv("HUB_CHROMIUM_ARGS", "").split())
        page = browser.new_page(viewport={"width": 1440, "height": 970})
        check_workspace(page, base, args.capture)
        page.set_viewport_size({"width": 412, "height": 915})
        page.goto(f"{base}/#overview")
        expect(page.get_by_role("heading", name="Platform overview")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
        browser.close()
    print("Browser smoke passed.")


if __name__ == "__main__":
    main()
