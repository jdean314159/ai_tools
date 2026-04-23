from llm_inspector.core import ContextResult, Section, TokenAccounting


def test_token_accounting_consistency_when_provided():
    sections = [
        Section(title="A", text="x", origin="system", tokens=3),
        Section(title="B", text="y", origin="user", tokens=5),
    ]
    acc = TokenAccounting(total_tokens=8)
    ctx = ContextResult(sections=sections, token_accounting=acc)

    total = sum(s.tokens for s in ctx.sections if s.tokens is not None)
    assert total == ctx.token_accounting.total_tokens
