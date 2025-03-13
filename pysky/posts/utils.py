from types import SimpleNamespace


def uploadable(obj):
    return hasattr(obj, "upload") and callable(obj.upload)


def uploaded(obj):
    return hasattr(obj, "upload_response") and isinstance(obj.upload_response, SimpleNamespace)
