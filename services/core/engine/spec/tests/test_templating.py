import pytest

from engine.spec.templating import Filter, Ref, TemplateError, format_date, parse, render


def test_plain_text_has_no_refs() -> None:
    assert parse("Northwind Ltd") == []


def test_input_with_filters() -> None:
    assert parse('Due {{ due_date | date:"MM/DD/YYYY" }} for {{amount|number:2}}') == [
        Ref("input", "due_date", None, (Filter("date", "MM/DD/YYYY"),)),
        Ref("input", "amount", None, (Filter("number", 2),)),
    ]


def test_secret_and_output_refs() -> None:
    assert parse("{{secrets.acme_login.username}}/{{outputs.invoice_number}}") == [
        Ref("secret", "acme_login", "username"),
        Ref("output", "invoice_number"),
    ]


@pytest.mark.parametrize(
    "template",
    [
        "{{ amount + 1 }}",
        "{{ __import__('os') }}",
        "{{ secrets.acme_login }}",
        "{{ vendor.name }}",
        '{{ amount | number:"2" }}',
        "{{ due_date | date:MM }}",
        "{{ secrets.acme_login.password | number:2 }}",
        "{{ unclosed",
        "stray }}",
    ],
)
def test_rejects_anything_but_the_grammar(template: str) -> None:
    with pytest.raises(TemplateError):
        parse(template)


# --- render ---


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{{amount | number:2}}", "1250.50"),
        ("{{amount}}", "1250.5"),
        ('{{due | date:"MM/DD/YYYY"}}', "11/05/2026"),
        ('{{due | date:"D.M.YY"}}', "5.11.26"),
        ("Invoice for {{vendor}} ({{outputs.ref}})", "Invoice for Northwind (INV-7)"),
        ("{{secrets.acme_login.password}}", "s3cret"),
        ("no templates", "no templates"),
    ],
)
def test_render(template: str, expected: str) -> None:
    values = {"amount": 1250.5, "due": "2026-11-05", "vendor": "Northwind"}
    assert (
        render(template, values, {"acme_login": {"password": "s3cret"}}, {"ref": "INV-7"})
        == expected
    )


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("{{missing}}", 'input "missing" has no value'),
        ("{{secrets.other.password}}", "secret other.password is not available"),
        ('{{amount | date:"YYYY"}}', "can't format"),
        ("{{outputs.later}}", 'output "later" has no value'),
    ],
)
def test_render_errors(template: str, message: str) -> None:
    with pytest.raises(TemplateError, match=message):
        render(template, {"amount": "abc"}, {})


def test_format_date_tokens() -> None:
    from datetime import date

    assert format_date(date(2026, 1, 9), "YYYY-MM-DD / M/D") == "2026-01-09 / 1/9"
