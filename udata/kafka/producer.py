import json

from flask import current_app
from kafka import KafkaProducer

from udata.models import Dataset


producer = KafkaProducer(bootstrap_servers='localhost:29092',
                         value_serializer=lambda v: json.dumps(v).encode('utf-8'))


def format_dataset_message(dataset):
    # TODO: better marshalling. Maybe share DatasetCsvAdaptater logic
    return {
        'id': str(dataset.id),
        'title': dataset.title,
        'description': dataset.description,
        'url': dataset.display_url,
        'orga_sp': 1 if dataset.organization and dataset.organization.public_service else 0,
        'orga_followers': dataset.organization.metrics.get("followers", 0) if dataset.organization else 0,
        'dataset_views': dataset.metrics.get("views", 0),
        'dataset_followers': dataset.metrics.get("followers", 0),
        'dataset_reuses': dataset.metrics.get("reuses", 0),
        'dataset_featured': 1 if dataset.featured else 0,
        'organization_id': str(dataset.organization.id) if dataset.organization else str(dataset.owner.id),
        'temporal_coverage_start': 0,
        'temporal_coverage_end': 0,
        'spatial_granularity': 0,
        'spatial_zones': 0
    }


def produce(sender, document, **kwargs):
    '''Produce message with marshalled document'''
    if isinstance(document, Dataset):
        # TODO: Support reuse and orga
        producer.send('dataset', format_dataset_message(document))
        producer.flush()
