import os
from datetime import datetime
from pathlib import Path

import pytest
from selenium import webdriver 

E2E_BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
E2E_ARTIFACT_DIR = Path(os.environ.get("E2E_ARTIFACT_DIR", "reports/e2e-screenshots")) # Screenshots are saved in reports folder

@pytest.fixture(scope="session")
def e2e_base_url():
    """ This fixture ensures the test knows where the app is - allows the same test to work in different environments """
    return E2E_BASE_URL

@pytest.fixture(scope="function")
def e2e_driver():
    """ For each test, this fixture launches + quits Chrome """
    e2e_options = webdriver.ChromeOptions() 
    if os.environ.get("HEADLESS", "1") == "1": 
        e2e_options.add_argument("--headless=new") # Runs Chrome without visible window (useful for Test EC2)
    e2e_options.add_argument("--no-sandbox") # Allows Chrome to start as root / inside containers
    e2e_options.add_argument("--disable-dev-shm-usage") # Prevents Chrom from crashing when a Linux server has a small amount of shared memory 
    e2e_options.add_argument("--window-size=1920,1080") # Headless browser + outlining its size

    e2e_browser = webdriver.Chrome(options=e2e_options)
    yield e2e_browser

    try:
        e2e_browser.quit()
    except Exception:
        pass

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    """ This fixture saves a screenshot when a browser test fails """
    browser_test_outcome = yield
    browser_test_report = browser_test_outcome.get_result()
    if browser_test_report.when == "call" and browser_test_report.failed:
        e2e_browser = item.funcargs.get("e2e_driver") # Takes the browser the test was using - must match the name of the fixture exactly 
        if e2e_browser:
            E2E_ARTIFACT_DIR.mkdri(parents=True, exist_ok=True)
            name = f"{item.name}-{datetime.now():%Y%m%d-%H%M%S}.png"
            e2e_browser.save_screenshot(str(E2E_ARTIFACT_DIR/name)) 
