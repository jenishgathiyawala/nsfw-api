# Contributing

Thanks for helping. Bug reports, fixes and improvements are welcome.

## Set up

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/jenishgathiyawala/nsfw-api.git && cd nsfw-api
./run.sh --reload     # http://127.0.0.1:8000/docs
uv run pytest         # all tests must pass
```

## Sending a change

1. Fork the repository and create a branch.
2. Keep the change focused: one fix or feature per pull request.
3. Add or update tests in `tests/` and run `uv run pytest`.
4. Update `README.md` if you change behaviour, endpoints or settings.
5. Open a pull request that says what changed and why.

The maintainer reviews every pull request. Nothing is merged without that review.

## Accuracy changes

If a change claims better accuracy (preprocessing, thresholds, a new model), include the
before and after output of `scripts/evaluate.py` on your own labelled photos.

## Photos: never commit them

- Don't add NSFW or personal photos to the repository, issues or pull requests.
- Keep test photos in `dataset/`, which git ignores.
- Tests generate their own images (see `tests/conftest.py`).

## New models or dependencies

Say what licence they use. They must be compatible with AGPL-3.0, and model files need an
entry in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Licence

By sending a contribution you agree that it is licensed under the project's licence,
[AGPL-3.0](LICENSE).

## Security

Report security problems privately, see [SECURITY.md](SECURITY.md).
