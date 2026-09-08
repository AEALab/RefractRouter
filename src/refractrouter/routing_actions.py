"""Execution identity of a route: provider, model and its effective request settings."""
from dataclasses import asdict
import hashlib
import json


def reasoning_effort(model):
    options = model.request_options
    return (options.get('reasoning', {}).get('effort') if model.wire_api == 'responses'
            else options.get('reasoning_effort'))


def action_identity(model):
    return {'id': model.model_id, 'provider': model.provider, 'model': model.api_model,
            'reasoning_effort': reasoning_effort(model)}


def action_binding(model):
    # Bind predictions to the actual request envelope and prices, not just an API name.
    data = asdict(model)
    data.pop('snapshot_date', None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
