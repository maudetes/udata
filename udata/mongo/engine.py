import mongoengine
from bson import DBRef, ObjectId
from flask import Flask
from flask_mongoengine import MongoEngineSessionInterface
from flask_storage.mongo import FileField, ImageField
from mongoengine.base import TopLevelDocumentMetaclass, get_document
from mongoengine.errors import ValidationError
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    DictField,
    EmbeddedDocument,
    EmbeddedDocumentField,
    EmbeddedDocumentListField,
    FloatField,
    GenericEmbeddedDocumentField,
    GenericLazyReferenceField,
    GenericReferenceField,
    IntField,
    LazyReferenceField,
    ListField,
    MapField,
    MultiPolygonField,
    ReferenceField,
    StringField,
    UUIDField,
)
from mongoengine.queryset import CASCADE, NULLIFY, PULL
from mongoengine.signals import post_save, pre_save
from pymongo import ReadPreference, uri_parser

from .badges_field import BadgesField
from .datetime_fields import DateField, DateRange, Datetimed
from .document import DomainModel, UDataDocument
from .extras_fields import ExtrasField, OrganizationExtrasField
from .queryset import UDataQuerySet
from .slug_fields import SlugField
from .taglist_field import TagListField
from .url_field import URLField
from .uuid_fields import AutoUUIDField

MONGODB_CONF_VARS = (
    "MONGODB_ALIAS",
    "MONGODB_DB",
    "MONGODB_HOST",
    "MONGODB_IS_MOCK",
    "MONGODB_PASSWORD",
    "MONGODB_PORT",
    "MONGODB_USERNAME",
    "MONGODB_CONNECT",
    "MONGODB_TZ_AWARE",
)


class InvalidSettingsError(Exception):
    pass


def _sanitize_settings(settings):
    """Given a dict of connection settings, sanitize the keys and fall
    back to some sane defaults.
    """
    # Remove the "MONGODB_" prefix and make all settings keys lower case.
    resolved_settings = {}
    for k, v in settings.items():
        if k.startswith("MONGODB_"):
            k = k[len("MONGODB_") :]
        k = k.lower()
        resolved_settings[k] = v

    # Handle uri style connections
    if "://" in resolved_settings.get("host", ""):
        # this section pulls the database name from the URI
        # PyMongo requires URI to start with mongodb:// to parse
        # this workaround allows mongomock to work
        uri_to_check = resolved_settings["host"]

        if uri_to_check.startswith("mongomock://"):
            uri_to_check = uri_to_check.replace("mongomock://", "mongodb://")

        uri_dict = uri_parser.parse_uri(uri_to_check)
        resolved_settings["db"] = uri_dict["database"]

    # Add a default name param or use the "db" key if exists
    if resolved_settings.get("db"):
        resolved_settings["name"] = resolved_settings.pop("db")
    else:
        resolved_settings["name"] = "test"

    # Add various default values.
    resolved_settings["alias"] = resolved_settings.get(
        "alias", mongoengine.DEFAULT_CONNECTION_NAME
    )  # TODO do we have to specify it here? MongoEngine should take care of that
    resolved_settings["host"] = resolved_settings.get(
        "host", "localhost"
    )  # TODO this is the default host in pymongo.mongo_client.MongoClient, we may not need to explicitly set a default here
    resolved_settings["port"] = resolved_settings.get(
        "port", 27017
    )  # TODO this is the default port in pymongo.mongo_client.MongoClient, we may not need to explicitly set a default here

    # Default to ReadPreference.PRIMARY if no read_preference is supplied
    resolved_settings["read_preference"] = resolved_settings.get(
        "read_preference", ReadPreference.PRIMARY
    )

    # Clean up empty values
    for k, v in list(resolved_settings.items()):
        if v is None:
            del resolved_settings[k]

    return resolved_settings


def get_connection_settings(config):
    """
    Given a config dict, return a sanitized dict of MongoDB connection
    settings that we can then use to establish connections. For new
    applications, settings should exist in a "MONGODB_SETTINGS" key, but
    for backward compactibility we also support several config keys
    prefixed by "MONGODB_", e.g. "MONGODB_HOST", "MONGODB_PORT", etc.
    """
    # Sanitize all the settings living under a "MONGODB_SETTINGS" config var
    if "MONGODB_SETTINGS" in config:
        settings = config["MONGODB_SETTINGS"]

        # If MONGODB_SETTINGS is a list of settings dicts, sanitize each
        # dict separately.
        if isinstance(settings, list):
            # List of connection settings.
            settings_list = []
            for setting in settings:
                settings_list.append(_sanitize_settings(setting))
            return settings_list

        # Otherwise, it should be a single dict describing a single connection.
        else:
            return _sanitize_settings(settings)

    # If "MONGODB_SETTINGS" doesn't exist, sanitize the "MONGODB_" keys
    # as if they all describe a single connection.
    else:
        config = dict(
            (k, v) for k, v in config.items() if k in MONGODB_CONF_VARS
        )  # ugly dict comprehention in order to support python 2.6
        return _sanitize_settings(config)


def create_connections(config):
    """
    Given Flask application's config dict, extract relevant config vars
    out of it and establish MongoEngine connection(s) based on them.
    """
    # Validate that the config is a dict
    if config is None or not isinstance(config, dict):
        raise InvalidSettingsError("Invalid application configuration")

    # Get sanitized connection settings based on the config
    conn_settings = get_connection_settings(config)

    # If conn_settings is a list, set up each item as a separate connection
    # and return a dict of connection aliases and their connections.
    if isinstance(conn_settings, list):
        connections = {}
        for each in conn_settings:
            alias = each["alias"]
            connections[alias] = _connect(each)
        return connections

    # Otherwise, return a single connection
    return _connect(conn_settings)


def _connect(conn_settings):
    """Given a dict of connection settings, create a connection to
    MongoDB by calling mongoengine.connect and return its result.
    """
    db_name = conn_settings.pop("name")
    return mongoengine.connect(db_name, **conn_settings)


class UDataMongoEngine:
    """Customized mongoengine with extra fields types and helpers"""

    def __init__(self, config=None, app=None):
        self.app = None
        self.config = config

        if app is not None:
            self.init_app(app, config)

        self.BadgesField = BadgesField
        self.TagListField = TagListField
        self.DateField = DateField
        self.Datetimed = Datetimed
        self.ExtrasField = ExtrasField
        self.OrganizationExtrasField = OrganizationExtrasField
        self.SlugField = SlugField
        self.AutoUUIDField = AutoUUIDField
        self.Document = UDataDocument
        self.EmbeddedDocument = EmbeddedDocument
        self.DomainModel = DomainModel
        self.DateRange = DateRange
        self.BaseQuerySet = UDataQuerySet
        self.BaseDocumentMetaclass = TopLevelDocumentMetaclass
        self.FileField = FileField
        self.ImageField = ImageField
        self.URLField = URLField
        self.BooleanField = BooleanField
        self.DateTimeField = DateTimeField
        self.DictField = DictField
        self.IntField = IntField
        self.EmbeddedDocumentField = EmbeddedDocumentField
        self.EmbeddedDocumentListField = EmbeddedDocumentListField
        self.FloatField = FloatField
        self.GenericEmbeddedDocumentField = GenericEmbeddedDocumentField
        self.GenericLazyReferenceField = GenericLazyReferenceField
        self.GenericReferenceField = GenericReferenceField
        self.LazyReferenceField = LazyReferenceField
        self.ListField = ListField
        self.MapField = MapField
        self.MultiPolygonField = MultiPolygonField
        self.ReferenceField = ReferenceField
        self.StringField = StringField
        self.UUIDField = UUIDField
        self.ValidationError = ValidationError
        self.ObjectId = ObjectId
        self.DBRef = DBRef
        self.CASCADE = CASCADE
        self.PULL = PULL
        self.NULLIFY = NULLIFY
        self.post_save = post_save
        self.pre_save = pre_save

    def init_app(self, app, config=None):
        if not app or not isinstance(app, Flask):
            raise TypeError("Invalid Flask application instance")

        self.app = app

        app.extensions = getattr(app, "extensions", {})

        # Make documents JSON serializable
        # override_json_encoder(app)
        # TODO: do we need this?

        if "mongoengine" not in app.extensions:
            app.extensions["mongoengine"] = {}

        if self in app.extensions["mongoengine"]:
            # Raise an exception if extension already initialized as
            # potentially new configuration would not be loaded.
            raise ValueError("Extension already initialized")

        if config:
            # Passed config have max priority, over init config.
            self.config = config

        if not self.config:
            # If no configs passed, use app.config.
            config = app.config

        # Obtain db connection(s)
        connections = create_connections(config)

        # Store objects in application instance so that multiple apps do not
        # end up accessing the same objects.
        s = {"app": app, "conn": connections}
        app.extensions["mongoengine"][self] = s

    def resolve_model(self, model):
        """
        Resolve a model given a name or dict with `class` entry.

        :raises ValueError: model specification is wrong or does not exists
        """
        if not model:
            raise ValueError("Unsupported model specifications")
        if isinstance(model, str):
            classname = model
        elif isinstance(model, dict) and "class" in model:
            classname = model["class"]
        else:
            raise ValueError("Unsupported model specifications")

        try:
            return get_document(classname)
        except self.NotRegistered:
            message = 'Model "{0}" does not exist'.format(classname)
            raise ValueError(message)


db = UDataMongoEngine()
session_interface = MongoEngineSessionInterface(db)
