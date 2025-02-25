import sys
import inspect
from datetime import datetime

from peewee import Model

from pysky.database import db
import pysky.models


def get_model_classes():
    class_members = inspect.getmembers(sys.modules["pysky.models"], inspect.isclass)
    return [(n, cls) for n, cls in class_members if cls.__base__ == pysky.models.BaseModel]


def create_non_existing_tables(db):

    all_model_classes = get_model_classes()
    missing_table_model_classes = [
        (n, cls) for n, cls in all_model_classes if not cls.table_exists()
    ]

    if not missing_table_model_classes:
        print("All tables already exist.")
    else:
        print(
            f"Creating missing tables: {', '.join(str(cls._meta.table_name) for n,cls in missing_table_model_classes)}"
        )
        db.create_tables([cls for n, cls in missing_table_model_classes])


if __name__=="__main__":

    # create missing tables:
    create_non_existing_tables(db)
