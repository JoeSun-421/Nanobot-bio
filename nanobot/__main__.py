"""
Entry point for running nanobot as a module: python -m nanobot

Product entry is ``nanobot-bio`` / ``app``; the upstream personal-assistant CLI
is not shipped in the slim vendor.
"""


def app() -> None:
    raise SystemExit(
        "nanobot CLI was stripped in the slim vendor; use `nanobot-bio` instead."
    )


if __name__ == "__main__":
    app()
