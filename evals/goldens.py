"""Golden tasks for E1 (docs/12-testing-and-evals.md): how each is performed, and what a
correct compile of it must contain.

`expected` is the answer key, written by hand:
- steps:        [action, element name] in order (navigate has no name)
- input_steps:  element names whose value must become an input (not a constant)
- checkpoints:  element names that must ask for approval
- replay:       new values per element name, used to replay the compiled workflow
- login:        values for the saved login's fields (any secret name the compiler picks)

Rebuild the recordings with `python evals/make_goldens.py` (Acme portal on :3001).
"""

from typing import Any

PORTAL = "http://localhost:3001"
ACME_LOGIN = {"username": "sara", "password": "acme-demo"}


def _acme_login(page, act, enter: bool = False) -> None:
    act(page.get_by_label("Username"), "sara")
    if enter:
        act(page.get_by_label("Password"), "acme-demo", press="Enter")
    else:
        act(page.get_by_label("Password"), "acme-demo")
        act(page.get_by_role("button", name="Sign in"))
    page.wait_for_url("**/dashboard")


def _new_invoice(page, act, vendor: str, amount: str, due: str, description: str | None) -> None:
    act(page.get_by_role("link", name="Invoices", exact=True))
    page.wait_for_url("**/invoices")
    act(page.get_by_test_id("new-invoice-btn"))
    page.wait_for_url("**/invoices/new")
    act(page.get_by_label("Vendor"))
    act(page.get_by_role("option", name=vendor))
    act(page.get_by_label("Amount"), amount)
    act(page.get_by_label("Due date"), due)
    if description:
        act(page.get_by_label("Description"), description)
    act(page.get_by_role("button", name="Submit"))
    page.wait_for_url("**/invoices/INV-*")


INVOICE_STEPS = [
    ["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
    ["click", "Invoices"], ["click", "New invoice"], ["select", "Vendor"], ["fill", "Amount"],
    ["fill", "Due date"],
]  # fmt: skip

TASKS: list[dict[str, Any]] = [
    {
        "id": "acme_invoice_northwind",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Create a vendor invoice and submit it for approval",
        "task": lambda page, act: (
            _acme_login(page, act),
            _new_invoice(page, act, "Northwind Ltd", "1250.50", "11/15/2026", "Office chairs, order 4471"),
        ),
        "expected": {
            "steps": [*INVOICE_STEPS, ["fill", "Description"], ["click", "Submit"]],
            "input_steps": ["Vendor", "Amount", "Due date", "Description"],
            "checkpoints": ["Submit"],
            "replay": {"Vendor": "City Power & Light", "Amount": "77.25", "Due date": "2026-12-24", "Description": "Replay"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_invoice_no_description",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Enter a utility bill as an invoice",
        "task": lambda page, act: (
            _acme_login(page, act),
            _new_invoice(page, act, "City Power & Light", "89.99", "12/01/2026", None),
        ),
        "expected": {
            "steps": [*INVOICE_STEPS, ["click", "Submit"]],
            "input_steps": ["Vendor", "Amount", "Due date"],
            "checkpoints": ["Submit"],
            "replay": {"Vendor": "Northwind Ltd", "Amount": "12", "Due date": "2027-01-31"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_login_with_enter",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Log in with the keyboard and create an invoice",
        "task": lambda page, act: (
            _acme_login(page, act, enter=True),
            _new_invoice(page, act, "Northwind Ltd", "500", "10/30/2026", None),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["press", "Password"],
                      *INVOICE_STEPS[4:], ["click", "Submit"]],  # fmt: skip
            "input_steps": ["Vendor", "Amount", "Due date"],
            "checkpoints": ["Submit"],
            "replay": {"Vendor": "City Power & Light", "Amount": "640.10", "Due date": "2026-11-02"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_add_vendor",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Add a new vendor with its contact email",
        "task": lambda page, act: (
            _acme_login(page, act),
            act(page.get_by_role("link", name="Vendors", exact=True)),
            page.wait_for_url("**/vendors"),
            act(page.get_by_role("button", name="Add vendor")),
            act(page.get_by_label("Name"), "Globex Corporation"),
            act(page.get_by_label("Email"), "ap@globex.example"),
            act(page.get_by_role("button", name="Save vendor")),
            page.wait_for_load_state("load"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
                      ["click", "Vendors"], ["click", "Add vendor"], ["fill", "Name"], ["fill", "Email"],
                      ["click", "Save vendor"]],  # fmt: skip
            "input_steps": ["Name", "Email"],
            "checkpoints": [],
            "replay": {"Name": "Initech LLC", "Email": "billing@initech.example"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_approve_invoice",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Approve the first invoice waiting for approval",
        "task": lambda page, act: (
            _acme_login(page, act),
            act(page.get_by_role("link", name="Approvals", exact=True)),
            page.wait_for_url("**/approvals"),
            act(page.get_by_role("button", name="Approve").first),
            page.wait_for_load_state("load"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
                      ["click", "Approvals"], ["click", "Approve"]],  # fmt: skip
            "input_steps": [],
            "checkpoints": ["Approve"],
            "replay": {},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_search_invoices",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Find the invoices of a vendor",
        "task": lambda page, act: (
            _acme_login(page, act),
            act(page.get_by_role("link", name="Invoices", exact=True)),
            page.wait_for_url("**/invoices"),
            act(page.get_by_label("Search"), "Northwind"),
            act(page.get_by_role("button", name="Go")),
            page.wait_for_url("**/invoices?q=*"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
                      ["click", "Invoices"], ["fill", "Search"], ["click", "Go"]],  # fmt: skip
            "input_steps": ["Search"],
            "checkpoints": [],
            "replay": {"Search": "City Power"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_search_vendors",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Look up a vendor",
        "task": lambda page, act: (
            _acme_login(page, act),
            act(page.get_by_role("link", name="Vendors", exact=True)),
            page.wait_for_url("**/vendors"),
            act(page.get_by_label("Search vendors"), "City"),
            act(page.get_by_role("button", name="Search")),
            page.wait_for_url("**/vendors?q=*"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
                      ["click", "Vendors"], ["fill", "Search vendors"], ["click", "Search"]],  # fmt: skip
            "input_steps": ["Search vendors"],
            "checkpoints": [],
            "replay": {"Search vendors": "North"},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "acme_reject_invoice",
        "start_url": f"{PORTAL}/login?variant=original",
        "description": "Reject the first invoice waiting for approval",
        "task": lambda page, act: (
            _acme_login(page, act),
            act(page.get_by_role("link", name="Approvals", exact=True)),
            page.wait_for_url("**/approvals"),
            act(page.get_by_role("button", name="Reject").first),
            page.wait_for_load_state("load"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Sign in"],
                      ["click", "Approvals"], ["click", "Reject"]],  # fmt: skip
            "input_steps": [],
            "checkpoints": ["Reject"],
            "replay": {},
            "login": ACME_LOGIN,
        },
    },
    {
        "id": "saucedemo_checkout",
        "start_url": "https://www.saucedemo.com/",
        "description": "Buy a backpack in the demo shop",
        "task": lambda page, act: (
            act(page.get_by_placeholder("Username"), "standard_user"),
            act(page.get_by_placeholder("Password"), "secret_sauce"),
            act(page.get_by_role("button", name="Login")),
            page.wait_for_url("**/inventory.html"),
            act(page.locator("#add-to-cart-sauce-labs-backpack")),
            act(page.locator(".shopping_cart_link")),
            act(page.get_by_role("button", name="Checkout")),
            act(page.get_by_placeholder("First Name"), "Ayesha"),
            act(page.get_by_placeholder("Last Name"), "Khan"),
            act(page.get_by_placeholder("Zip/Postal Code"), "54000"),
            act(page.get_by_role("button", name="Continue")),
            act(page.get_by_role("button", name="Finish")),
            page.wait_for_url("**/checkout-complete.html"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Login"],
                      ["click", "Add to cart"], ["click", None], ["click", "Checkout"], ["fill", "First Name"],
                      ["fill", "Last Name"], ["fill", "Zip/Postal Code"], ["click", "Continue"],
                      ["click", "Finish"]],  # fmt: skip
            "input_steps": ["First Name", "Last Name", "Zip/Postal Code"],
            "checkpoints": ["Finish"],
            "replay": {"First Name": "Imran", "Last Name": "Ali", "Zip/Postal Code": "75500"},
            "login": {"username": "standard_user", "password": "secret_sauce"},
        },
    },
    {
        "id": "the_internet_login",
        "start_url": "https://the-internet.herokuapp.com/login",
        "description": "Log in to the secure area",
        "task": lambda page, act: (
            act(page.get_by_label("Username"), "tomsmith"),
            act(page.get_by_label("Password"), "SuperSecretPassword!"),
            act(page.get_by_role("button", name="Login")),
            page.wait_for_url("**/secure"),
        ),
        "expected": {
            "steps": [["navigate", None], ["fill", "Username"], ["fill", "Password"], ["click", "Login"]],
            "input_steps": [],
            "checkpoints": [],
            "replay": {},
            "login": {"username": "tomsmith", "password": "SuperSecretPassword!"},
        },
    },
]
