"""为旧版插件纯日志事件补可忽略标记；备份原文件，不删除或改写消息内容。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def migrate(path, apply=False):
    original = path.read_bytes()
    plain = subprocess.run(['zstd', '-dc'], input=original, capture_output=True, check=True).stdout
    rows, count = [], 0
    for line in plain.splitlines(keepends=True):
        row = json.loads(line)
        if row.get('type') in {'refractagent/tool-call', 'refractagent/tool-result'} and row.get('ignorable') is not True:
            row['ignorable'] = True
            line = (json.dumps(row, ensure_ascii=False, separators=(',', ':'))+'\n').encode()
            count += 1
        rows.append(line)
    if apply and count:
        digest = hashlib.sha256(original).hexdigest()
        backup = path.with_name(path.name + '.before-ignorable-' + digest[:12])
        if backup.exists():
            assert backup.read_bytes() == original
        else:
            with backup.open('xb') as stream:
                stream.write(original)
        # DSH 要求首个压缩帧独立且仅包含 header 行。
        encoded = b''.join(subprocess.run(['zstd', '-q', '-c'], input=part, capture_output=True, check=True).stdout
                           for part in (rows[0], b''.join(rows[1:])) if part)
        temp = path.with_name(path.name+'.migration-tmp')
        with temp.open('xb') as stream:
            stream.write(encoded)
        if path.read_bytes() != original:
            temp.unlink()
            raise RuntimeError('会话文件已变化，取消替换')
        temp.replace(path)
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print('marked' if args.apply else 'eligible', migrate(args.path, args.apply))
