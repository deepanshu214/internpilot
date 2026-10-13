"""Autofill runs against local copies of ATS-style forms. Each form sets window.SUBMITTED if it is ever submitted."""
from pathlib import Path

import pytest

from worker import llm
from worker.apply.autofill import answer_for, application_url, fill_page, load_answers

FIX = Path(__file__).parent / "fixtures"
JOB = {"title": "Software Engineering Intern", "company": "Acme", "jd_text": "Python backend"}
RULES = load_answers()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()


@pytest.fixture
def resume(tmp_path):
    f = tmp_path / "Deepanshu_Agarwal_Resume.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    return str(f)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: None)


def test_answer_rules():
    assert answer_for("First Name *", RULES) == "Deepanshu"
    assert answer_for("Name *", RULES) == "Deepanshu Agarwal"
    assert answer_for("School name", RULES) == "Vellore Institute of Technology"
    assert answer_for("Will you require visa sponsorship?", RULES) == ""  # left for you
    assert answer_for("Gender", RULES) == ""
    assert answer_for("Favourite colour", RULES) is None


def test_application_url():
    assert application_url("https://jobs.lever.co/acme/123") == "https://jobs.lever.co/acme/123/apply"
    assert application_url("https://jobs.ashbyhq.com/acme/abc") == "https://jobs.ashbyhq.com/acme/abc/application"
    assert application_url("https://boards.greenhouse.io/acme/jobs/1") == "https://boards.greenhouse.io/acme/jobs/1"


def test_greenhouse_style_form(page, resume):
    page.goto((FIX / "greenhouse_form.html").as_uri())
    report = fill_page(page, JOB, resume, RULES)
    assert page.input_value("#first_name") == "Deepanshu"
    assert page.input_value("#last_name") == "Agarwal"
    assert page.input_value("#email") == "deepanshuagarwal10b@gmail.com"
    assert page.input_value("#q_school") == "Vellore Institute of Technology"
    assert page.input_value("#q_grad") == "2028"
    assert page.input_value("#q_sponsor") == ""          # sponsorship is yours to answer
    assert page.input_value("#q_gender") == ""           # EEO never auto-answered
    assert page.eval_on_selector("#resume", "e => e.files[0].name") == "Deepanshu_Agarwal_Resume.pdf"
    assert page.eval_on_selector("#cover_letter", "e => e.files.length") == 0
    assert any("sponsorship" in r for r in report["review"])
    assert any("Why do you want" in r for r in report["review"])  # no LLM → flagged for you
    assert page.evaluate("window.SUBMITTED") is None


def test_lever_style_form(page, resume):
    page.goto((FIX / "lever_form.html").as_uri())
    fill_page(page, JOB, resume, RULES)
    assert page.input_value("input[name=name]") == "Deepanshu Agarwal"
    assert page.input_value("input[name='urls[GitHub]']") == "https://github.com/deepanshu214"
    assert page.input_value("input[name='cards[stipend]']") == ""
    assert page.eval_on_selector("input[name=resume]", "e => e.files.length") == 1
    assert page.evaluate("window.SUBMITTED") is None  # its submit button says "Apply": must not be clicked


def test_reveal_link_then_fill(page, resume):
    page.goto((FIX / "ashby_reveal.html").as_uri())
    fill_page(page, JOB, resume, RULES)
    assert page.input_value("input[name=_systemfield_name]") == "Deepanshu Agarwal"
    assert page.input_value("input[name=loc]") == "Vellore, Tamil Nadu, India"
    assert page.evaluate("window.SUBMITTED") is None


def test_never_clicks_submit_labelled_apply(page, resume):
    page.goto((FIX / "tiny_form_apply_submit.html").as_uri())
    fill_page(page, JOB, resume, RULES)
    assert page.input_value("#em") == "deepanshuagarwal10b@gmail.com"
    assert page.evaluate("window.SUBMITTED") is None
