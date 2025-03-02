import os

from contextlib import contextmanager


@contextmanager
def unset_env_vars(var_names):
    cached_env_vars = {v: os.environ.pop(v, None) for v in var_names}
    cached_env_vars = {k: v for k, v in cached_env_vars.items() if v is not None}
    try:
        yield
    finally:
        os.environ.update(cached_env_vars)


def run_without_env_vars(var_names):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with unset_env_vars(var_names):
                return func(*args, **kwargs)

        return wrapper

    return decorator
