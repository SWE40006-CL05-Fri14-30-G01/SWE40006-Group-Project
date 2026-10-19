""" E2E browser test of the full task lifecycle (Selenium + real app) """
import os
import uuid
import pytest

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.e2e
TIMEOUT = 10

def css(test_e2e_id):
    return f'[data-testid="{test_e2e_id}"]'


def find_card(driver, title):
    # Return the task card with the exact following title otherwise returns none
    for card in driver.find_elements(By.CSS_SELECTOR, css("task-card")):
        if card.find_element(By.CSS_SELECTOR, css("task-title")).text == title:
            return card
    return None

def wait_for_card(driver, title, status):
    # Wait until the card with the specified title is in the given column
    def _check(d):
        card = find_card(d, title)
        if card and card.get_attribute("data-status") == status:
            return card
        return False
    return WebDriverWait(driver, TIMEOUT).until(_check)


def delete_card(driver, title):
    card = find_card(driver, title)
    card.find_element(By.CSS_SELECTOR, css("delete-task")).click()
    WebDriverWait(driver, TIMEOUT).until(EC.alert_is_present()).accept()  


def test_task_lifecycle(e2e_driver, e2e_base_url):
    title = f"[e2e] lifecycle {uuid.uuid4().hex[:8]}"
    e2e_driver.get(e2e_base_url)
    try:
        # Page loads + shows a build ID
        build_id = WebDriverWait(e2e_driver, TIMEOUT).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, css("build-id")))
        )
        assert build_id.text.strip() != ""
        expected_build_id = os.environ.get("EXPECTED_BUILD_ID")  # Set by pipeline
        if expected_build_id:
            assert build_id.get_attribute("textContent").strip() == expected_build_id # Proves that tests ran against freshly deployed vers

        # Create a task
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-title-input")).send_keys(title)
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-assignee-input")).send_keys("Selenium Bot")
        e2e_driver.find_element(By.CSS_SELECTOR, css("add-task-button")).click()

        card = wait_for_card(e2e_driver, title, "To Do")
        assert card.find_element(By.CSS_SELECTOR, css("task-assignee")).text == "Selenium Bot"
        e2e_driver.find_element(
            By.CSS_SELECTOR, f'{css("flash-message")}[data-category="success"]'
        )

        # Move task to To Do -> In Progress -> Done
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
        WebDriverWait(e2e_driver, TIMEOUT).until(lambda d: find_card(d, title) is None)

    finally:
        # Clean-up
        # If the test failed halfway, the task is still removed
        try:
            e2e_driver.get(e2e_base_url)
            if find_card(e2e_driver, title):
                delete_card(e2e_driver, title)
        except Exception:
            pass