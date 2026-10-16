# Offline NUT regression tests

Use Python 3.14 and a virtualenv outside the repository. The review environment
already has the pinned dependencies; to recreate it with uv if needed:

```sh
uv venv --python 3.14 /tmp/ha-nut-whole-review-venv
uv pip install --python /tmp/ha-nut-whole-review-venv/bin/python -r tests/requirements.txt
```

From the repository root:

```sh
PYTHONPATH="$PWD" /tmp/ha-nut-whole-review-venv/bin/pytest tests -q
/tmp/ha-nut-whole-review-venv/bin/ruff check custom_components tests
/tmp/ha-nut-whole-review-venv/bin/ruff format --check custom_components tests
```

All NUT clients are mocked. pytest.ini disables network sockets (Unix sockets are
allowed for Home Assistant's event loop). No Home Assistant installation or real
NUT server is used.

The separate review harness at `/tmp/ha-nut-whole-review-run` contains the 87
adapted core tests. Its malformed-count test expected status-key fallback; M6
explicitly requires rejecting invalid counts. Apply the included patch once to
that harness to update this expectation:

```sh
patch -d /tmp/ha-nut-whole-review-run -p1 < tests/baseline-count-validation.patch
PYTHONPATH="$PWD" /tmp/ha-nut-whole-review-venv/bin/pytest --import-mode=importlib /tmp/ha-nut-whole-review-run/tests -q --disable-socket --allow-unix-socket
```

Importlib mode and PYTHONPATH ensure the harness tests the repository integration,
not its stale copy. The repo tests run independently of the review harness.
