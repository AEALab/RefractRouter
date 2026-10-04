"""按请求规模匹配真实时延样本；稀疏观测不当成已校准的硬保证。"""
import math

MIN_SAMPLES = 5
BOOTSTRAP_MS = 60_000.0
INPUT_BOUNDS = (1024, 4096, 16384, 65536, 262144, 1048576)
OUTPUT_BOUNDS = (256, 1024, 4096, 16384, 65536, 262144)


def bucket(value, bounds):
    return next((bound for bound in bounds if value <= bound), None)


def validate_latency_evidence(raw):
    if not isinstance(raw, dict) or set(raw) - {'observations', 'snapshot_id'}:
        raise ValueError('invalid latency evidence')
    observations = raw.get('observations')
    if not isinstance(observations, list) or len(observations) > 50:
        raise ValueError('latency evidence requires at most 50 observations')
    result = []
    for row in observations:
        if not isinstance(row, dict) or set(row) != {'input_tokens', 'output_tokens', 'latency_ms'}:
            raise ValueError('invalid latency observation')
        if any(type(row[k]) is not int or row[k] < 0 for k in row):
            raise ValueError('latency observation requires nonnegative integers')
        result.append(dict(row))
    snapshot = raw.get('snapshot_id')
    if snapshot is not None and (not isinstance(snapshot, str) or len(snapshot) != 64):
        raise ValueError('invalid latency snapshot')
    return {'observations': result, 'snapshot_id': snapshot}


def forecast_latency(evidence, input_tokens, output_tokens, fallback_ms):
    """同模型／推理档位的同规模分组 P90；无匹配或小样本使用保守先验。"""
    ib, ob = bucket(input_tokens, INPUT_BOUNDS), bucket(output_tokens, OUTPUT_BOUNDS)
    rows = evidence['observations']
    matches = [r['latency_ms'] for r in rows if ib is not None and ob is not None
               and bucket(r['input_tokens'], INPUT_BOUNDS) == ib
               and bucket(r['output_tokens'], OUTPUT_BOUNDS) == ob]
    ordered = sorted(matches)
    p90 = ordered[max(0, math.ceil(.9 * len(ordered)) - 1)] if ordered else None
    ready = len(matches) >= MIN_SAMPLES
    prediction = max(1, p90) if ready else max(BOOTSTRAP_MS, fallback_ms, p90 or 0)
    return {'rule_version': 'request-size-p90-v1', 'prediction_ms': prediction,
            'source': 'matched-observation-p90' if ready else 'sparse-or-unmatched-bootstrap',
            'samples': len(matches), 'available_samples': len(rows), 'minimum_samples': MIN_SAMPLES,
            'input_bucket_max': ib, 'output_bucket_max': ob, 'observed_p90_ms': p90,
            'snapshot_id': evidence.get('snapshot_id'), 'calibrated_sla': False}
