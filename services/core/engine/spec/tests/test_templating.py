import pytest

from engine.spec.templating import Filter, Ref, TemplateError, parse


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
