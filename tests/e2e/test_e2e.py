""" E2E browser test of the full task lifecycle (Selenium + real app) """
import os
import uuid
import pytest

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.e2e
TIMEOUT = 10
# Every click reloads the page, which can invalidate ("stale") elements we were holding
STALE = (StaleElementReferenceException,)

def css(test_e2e_id):
    return f'[data-testid="{test_e2e_id}"]'

def wait(driver):
    # WebDriverWait that retries, instead of failing, when the page reloads mid-check
    return WebDriverWait(driver, TIMEOUT, ignored_exceptions=STALE)

def find_card(driver, title):
    # Return the task card with this exact title, otherwise None.
    # If the page reloads while we're reading it, look again (up to 3 tries).
    for attempt in range(3):
        try:
            for card in driver.find_elements(By.CSS_SELECTOR, css("task-card")):
                if card.find_element(By.CSS_SELECTOR, css("task-title")).text == title:
                    return card
            return None
        except StaleElementReferenceException:
            if attempt == 2:
                raise

def wait_for_card(driver, title, status):
    # Wait until the card with this title is in the given column
    def _check(d):
        card = find_card(d, title)
        if card and card.get_attribute("data-status") == status:
            return card
        return False
    return wait(driver).until(_check)

def delete_card(driver, title):
    # Find the card and click its delete button in one retried step
    def _click_delete(d):
        card = find_card(d, title)
        if card is None:
            return False
        card.find_element(By.CSS_SELECTOR, css("delete-task")).click()
        return True
    wait(driver).until(_click_delete)
    wait(driver).until(EC.alert_is_present()).accept()  # confirm pop-up

def clean_up_task(driver, base_url, title):
    # If the task still exists, delete it and confirm it's gone. Raises if it can't
    driver.get(base_url)
    if find_card(driver, title):
        delete_card(driver, title)
    wait(driver).until(lambda d: find_card(d, title) is None)

def test_task_lifecycle(e2e_driver, e2e_base_url):
    title = f"[e2e] lifecycle {uuid.uuid4().hex[:8]}"
    e2e_driver.get(e2e_base_url)
    try:
        # Page loads + shows a build ID
        build_id = wait(e2e_driver).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css("build-id")))
        )
        assert build_id.text.strip() != ""
        expected_build_id = os.environ.get("EXPECTED_BUILD_ID")  # Set by pipeline
        if expected_build_id:
            assert build_id.get_attribute("textContent").strip() == expected_build_id

        # Create a task
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-title-input")).send_keys(title)
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-assignee-input")).send_keys("Selenium Bot")
        e2e_driver.find_element(By.CSS_SELECTOR, css("add-task-button")).click()

        card = wait_for_card(e2e_driver, title, "To Do")
        assert card.find_element(By.CSS_SELECTOR, css("task-assignee")).text == "Selenium Bot"
        wait(e2e_driver).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, f'{css("flash-message")}[data-category="success"]')
            )
        )

        # Move task: To Do -> In Progress -> Done
        card.find_element(
            By.CSS_SELECTOR, f'{css("move-task")}[data-target-status="In Progress"]'
        ).click()
        card = wait_for_card(e2e_driver, title, "In Progress")

        card.find_element(
            By.CSS_SELECTOR, f'{css("move-task")}[data-target-status="Done"]'
        ).click()
        wait_for_card(e2e_driver, title, "Done")

        # Delete it + check it's gone
        delete_card(e2e_driver, title)
        wait(e2e_driver).until(lambda d: find_card(d, title) is None)

    finally:
        # Clean up
        clean_up_task(e2e_driver, e2e_base_url, title)