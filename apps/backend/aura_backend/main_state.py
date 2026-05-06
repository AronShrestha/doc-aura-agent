from __future__ import annotations


def get_queue():
    from .main import app_state

    return app_state.queue
