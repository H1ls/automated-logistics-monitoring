from __future__ import annotations

from Navigation_Bot.core.infrastructure.api.main import app


def main() -> int:
    routes = sorted(route.path for route in app.routes if getattr(route, "path", None))
    print("Navigation Bot API routes:")
    for route in routes:
        print(route)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
