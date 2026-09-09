"""检查 #39/#40 协议并归档零调用包络；本入口不支持付费执行。"""
import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.manifest import load_model_manifest
from refractrouter.research_protocol import historical_materials, preflight

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    raw = json.loads(args.protocol.read_text())
    manifest = load_model_manifest((args.protocol.parent / raw['manifest_path']).resolve())
    result = preflight(raw, manifest, excluded_materials=historical_materials(ROOT))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / 'protocol.json', raw)
    write_json(args.output_dir / 'preflight.json', result)
    write_json(args.output_dir / 'artifact-index.json', {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(args.output_dir.iterdir()) if p.is_file()})
    print(json.dumps({k: result[k] for k in ('real_model_calls', 'live_execution_ready',
        'protocol_sha256', 'maximum_calls', 'budget')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
