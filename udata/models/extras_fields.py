import logging

from datetime import date, datetime
from dateutil.parser import parse as parse_dt

from mongoengine import EmbeddedDocument
from mongoengine.fields import DictField, BaseField, DateField, DateTimeField

log = logging.getLogger(__name__)


ALLOWED_TYPES = (str, int, float, bool, datetime, date, list)


class ExtrasField(DictField):
    def __init__(self, **kwargs):
        self.registered = {}
        super(ExtrasField, self).__init__()

    def register(self, key, dbtype):
        '''Register a DB type to add constraint on a given extra key'''
        if not issubclass(dbtype, (BaseField, EmbeddedDocument)):
            msg = 'ExtrasField can only register MongoEngine fields'
            raise TypeError(msg)
        self.registered[key] = dbtype

    def validate(self, values):
        super(ExtrasField, self).validate(values)

        errors = {}
        for key, value in values.items():
            extra_cls = self.registered.get(key)

            if not extra_cls:
                if not isinstance(value, ALLOWED_TYPES):
                    types = ', '.join(t.__name__ for t in ALLOWED_TYPES)
                    msg = 'Value should be an instance of: {types}'
                    errors[key] = msg.format(types=types)
                continue

            try:
                if issubclass(extra_cls, EmbeddedDocument):
                    (value.validate()
                     if isinstance(value, extra_cls)
                     else extra_cls(**value).validate())
                else:
                    extra_cls().validate(value)

                # Serialize str to date or datetime for temporary fields
                if issubclass(extra_cls, (DateField, DateTimeField)) and isinstance(value, str):
                    values[key] = parse_dt(value)
                    if issubclass(extra_cls, DateField):
                        values[key] = value.date()

            except Exception as e:
                errors[key] = getattr(e, 'message', str(e))

        if errors:
            self.error('Unsupported types', errors=errors)

    def __call__(self, key):
        def inner(cls):
            self.register(key, cls)
            return cls
        return inner

    def to_python(self, value):
        if isinstance(value, EmbeddedDocument):
            return value
        return super(ExtrasField, self).to_python(value)
