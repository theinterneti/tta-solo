## Summary
<!-- Brief description of what this PR does -->

## Related Issues
<!-- Link to related issues: Fixes #123, Relates to #456 -->

## Type of Change
- [ ] 📋 Spec (new or updated specification)
- [ ] ✨ Feature (new functionality)
- [ ] 🐛 Bug fix
- [ ] 🔧 Refactor (no functional changes)
- [ ] 📚 Documentation
- [ ] 🏗️ Infrastructure (CI, dependencies, etc.)

## Checklist

### Spec-Driven Development
- [ ] Spec exists in `/specs/` for this change (or this IS a spec)
- [ ] Implementation follows the spec

### Code Quality
- [ ] Type hints added (using `str | None` syntax)
- [ ] Pydantic models used for data validation
- [ ] Code is stateless (no global variables in skills)
- [ ] Google-style docstrings included

### Testing
- [ ] Tests added/updated
- [ ] All tests pass locally (`uv run pytest -v`)
- [ ] Type checking passes (`uv run pyright src/`)

### Style
- [ ] Formatted with Ruff (`uv run ruff format .`)
- [ ] Linting passes (`uv run ruff check .`)

## Architecture Layer
<!-- Which layer(s) does this affect? -->
- [ ] Neural (LLM/narrative)
- [ ] Symbolic (Python/rules)  
- [ ] Bridge (skills)
- [ ] Infrastructure

## Testing Instructions
<!-- How can reviewers test this change? -->

## Screenshots/Logs
<!-- If applicable, add screenshots or relevant output -->
