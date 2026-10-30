"""交付与 Router 墙钟观测；不包含费用、选模或质量判定。"""
import math

VERSION = 'planning-transport-observation-v1'


def _duration(value):
    return type(value) in (int, float) and 0 <= value <= 2**53 - 1 and (type(value) is int or math.isfinite(value))


def attach_router_timing(row, payload):
    for key in ('routerOperationMs', 'routerRoundTripMs'):
        value = payload.get(key)
        if value is None:
            continue
        if _duration(value):
            row[key] = value
        else:
            row[key + 'Status'] = 'invalid-observation'


def attach_delivery(row, value):
    if not isinstance(value, dict) or set(value) - {
        'schemaVersion', 'clockOrigin', 'firstTextMs', 'releasedTextBytes', 'mode',
        'routerOperationMs', 'routerRoundTripMs'
    } or value.get('schemaVersion') != VERSION:
        raise ValueError('交付观测合同无效')
    if (value.get('clockOrigin') != 'dsh-model-request-start' or not _duration(value.get('firstTextMs'))
            or type(value.get('releasedTextBytes')) is not int or not 0 < value['releasedTextBytes'] <= 8 * 1024 * 1024
            or value.get('mode') not in ('live-text', 'buffered-release')):
        raise ValueError('交付观测字段无效')
    if row.get('userFirstTextMs') is not None and (
        row['userFirstTextMs'] != value['firstTextMs'] or row.get('userFirstTextOrigin') != value['clockOrigin']
        or row.get('deliveryMode') != value['mode']
    ):
        raise ValueError('相同调用的首次交付观测冲突')
    if value['releasedTextBytes'] < row.get('releasedTextBytes', 0):
        raise ValueError('相同调用的累计交付量不能回退')
    row.update(userFirstTextMs=value['firstTextMs'], userFirstTextOrigin=value['clockOrigin'],
               deliveryMode=value['mode'], releasedTextBytes=value['releasedTextBytes'], deliveryAttempted=True)
    attach_router_timing(row, value)
