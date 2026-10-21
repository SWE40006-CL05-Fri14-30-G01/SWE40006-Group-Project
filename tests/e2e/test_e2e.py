""" E2E browser test of the full task lifecycle (Selenium + real app) """
import os
import uuid
import pytest

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.e2e
TIMEOUT = 10

def css(test_e2e_id):
    return f'[data-testid="{test_e2e_id}"]'

def reload_error(exc):
    # Every click reloads the page. Chrome reports "the page changed under me" either as a
    # stale element or as a generic error saying the node does not belong to the document.
    return isinstance(exc, StaleElementReferenceException) or (
        isinstance(exc, WebDriverException)
        and "does not belong to the document" in str(exc)
    )

def retrying(check):
    # Wrap a wait condition so a page reload mid-check means "not yet", not a failure
    def _wrapped(driver):
        try:
            return check(driver)
        except WebDriverException as exc:
            if reload_error(exc):
                return False
            raise
    return _wrapped

def wait_until(driver, check):
    return WebDriverWait(driver, TIMEOUT).until(retrying(check))


def find_card(driver, title):
    # Return the task card with this exact title, otherwise None.
    # If the page reloads while we're reading it, look again (up to 3 tries).
    for attempt in range(3):
        try:
            for card in driver.find_elements(By.CSS_SELECTOR, css("task-card")):
                if card.find_element(By.CSS_SELECTOR, css("task-title")).text == title:
                    return card
            return None
        except WebDriverException as exc:
            if not reload_error(exc) or attempt == 2:
                raise

def wait_for_card(driver, title, status):
    # Wait until the card with this title is in the given column
    def _check(d):
        card = find_card(d, title)
        if card and card.get_attribute("data-status") == status:
            return card
        return False
    return wait_until(driver, _check)

def wait_until_gone(driver, title):
    wait_until(driver, lambda d: find_card(d, title) is None)

def card_text(driver, title, testid):
    # Read a field from the task card, re-finding the card if the page reloads
    def _read(d):
        card = find_card(d, title)
        return card.find_element(By.CSS_SELECTOR, css(testid)).text if card else False
    return wait_until(driver, _read)

def click_in_card(driver, title, selector):
    # Find the card and click a button inside it as one retried step
    def _click(d):
        card = find_card(d, title)
        if card is None:
            return False
        card.find_element(By.CSS_SELECTOR, selector).click()
        return True
    wait_until(driver, _click)

def delete_card(driver, title):
    click_in_card(driver, title, css("delete-task"))
    WebDriverWait(driver, TIMEOUT).until(EC.alert_is_present()).accept()  # confirm pop-up

def clean_up_task(driver, base_url, title):
    # If the task still exists, delete it and confirm it's gone. Raises if it can't
    driver.get(base_url)
    if find_card(driver, title):
        delete_card(driver, title)
    wait_until_gone(driver, title)

def test_task_lifecycle(e2e_driver, e2e_base_url):
    title = f"[e2e] lifecycle {uuid.uuid4().hex[:8]}"
    e2e_driver.get(e2e_base_url)
    try:
        # Page loads + shows the expected build ID
        build_id = wait_until(
            e2e_driver,
            EC.visibility_of_element_located((By.CSS_SELECTOR, css("build-id"))),
        )
        assert build_id.text.strip() != ""
        expected_build_id = os.environ.get("EXPECTED_BUILD_ID")  # Set by pipeline
        if expected_build_id:
            assert build_id.get_attribute("textContent").strip() == expected_build_id

        # Create a task
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-title-input")).send_keys(title)
        e2e_driver.find_element(By.CSS_SELECTOR, css("task-assignee-input")).send_keys("Selenium Bot")
        e2e_driver.find_element(By.CSS_SELECTOR, css("add-task-button")).click()

        wait_for_card(e2e_driver, title, "To Do")
        assert card_text(e2e_driver, title, "task-assignee") == "Selenium Bot"
        wait_until(
            e2e_driver,
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, f'{css("flash-message")}[data-category="success"]')
            ),
        )

        # Move task: To Do -> In Progress -> Done
        click_in_card(e2e_driver, title, f'{css("move-task")}[data-target-status="In Progress"]')
        wait_for_card(e2e_driver, title, "In Progress")

        click_in_card(e2e_driver, title, f'{css("move-task")}[data-target-status="Done"]')
        wait_for_card(e2e_driver, title, "Done")

        # Delete it + check it's gone
        delete_card(e2e_driver, title)
        wait_until_gone(e2e_driver, title)

    finally:
        # Clean up
        clean_up_task(e2e_driver, e2e_base_url, title)