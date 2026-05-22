from __future__ import annotations

import uvicorn
from ironrag_connector import Orchestrator, build_app

from .adapter import ConfluenceAdapter
from .config import ConfluenceSettings
from .webhook import make_confluence_handler


def main() -> None:
    settings = ConfluenceSettings()
    adapter = ConfluenceAdapter(settings)

    def make_handlers(orchestrator: Orchestrator) -> list[object]:
        return [make_confluence_handler(settings, adapter, orchestrator)]

    app = build_app(settings, adapter, webhook_factory=make_handlers)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
