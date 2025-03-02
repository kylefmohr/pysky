def pytest_collection_modifyitems(config, items):

    initial = [i for i in items if "db_state" in i.name]
    other   = [i for i in items if "db_state" not in i.name]

    initial.sort(key=lambda item: item.name)

    items[:] = initial + other
    return items
