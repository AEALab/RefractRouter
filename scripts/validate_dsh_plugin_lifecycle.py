from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "validation" / "dsh" / "plugin"
PACKAGE_NAME = "dsh-refractrouter-validation"


def run(command: list[str], *, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({completed.returncode}): {rendered}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def assert_compatible_tools(env: dict[str, str], package: dict[str, object]) -> dict[str, str]:
    dsh_version = run(["dsh", "--version"], env=env).strip()
    expected_dsh = package["dsh"]["compatibility"]["cli"]  # type: ignore[index]
    if dsh_version != expected_dsh:
        raise RuntimeError(f"expected DSH {expected_dsh}, found {dsh_version}")

    node_version = run(["node", "--version"], env=env).strip().removeprefix("v")
    node_parts = tuple(int(part) for part in node_version.split(".")[:2])
    if node_parts < (22, 19) or node_parts >= (23, 0):
        raise RuntimeError(f"unsupported Node version: {node_version}")

    pnpm_version = run(["pnpm", "--version"], env=env).strip()
    expected_pnpm = str(package["packageManager"]).removeprefix("pnpm@")
    if pnpm_version != expected_pnpm:
        raise RuntimeError(f"expected pnpm {expected_pnpm}, found {pnpm_version}")
    return {"dsh": dsh_version, "node": node_version, "pnpm": pnpm_version}


def profile_manifest(dsh_home: Path) -> dict[str, object]:
    path = dsh_home / "profiles" / "headless" / "package.json"
    return json.loads(path.read_text(encoding="utf-8"))


def assert_install_state(dsh_home: Path, *, installed: bool) -> None:
    manifest = profile_manifest(dsh_home)
    dependencies = manifest.get("dependencies", {})
    bundles = manifest["dsh"]["profile"]["bundles"]  # type: ignore[index]
    if (PACKAGE_NAME in dependencies) is not installed:
        raise RuntimeError(f"dependency install state does not match installed={installed}")
    if (PACKAGE_NAME in bundles) is not installed:
        raise RuntimeError(f"bundle install state does not match installed={installed}")


def assert_default_config(dump: str) -> None:
    expected = (
        "# == dsh-refractrouter-validation\n"
        "- id: refractrouter-validation\n"
        "  name: dsh-refractrouter-validation\n"
        "  config:\n"
        "    allowPaidRuns: false\n"
        "    billingUnit: USD\n"
        "    maxProductionCost: 2\n"
        "    maxEvaluationCost: 1\n"
        "    maxRetries: 0"
    )
    if expected not in dump:
        raise RuntimeError("composed profile does not contain the plugin's safe defaults")


def main() -> int:
    for executable in ("dsh", "node", "pnpm"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable is not on PATH: {executable}")

    package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="refractrouter-dsh-lifecycle-") as directory:
        dsh_home = Path(directory)
        env = os.environ.copy()
        env["DSH_HOME"] = str(dsh_home)
        env.pop("OPENAI_API_KEY", None)
        env.pop("DEEPSEEK_API_KEY", None)
        versions = assert_compatible_tools(env, package)

        add = ["dsh", "plugin", "--profile", "headless", "add", str(PLUGIN)]
        remove = ["dsh", "plugin", "--profile", "headless", "remove", PACKAGE_NAME]
        dump = ["dsh", "--profile", "headless", "--dump-config"]
        boot_help = ["dsh", "--profile", "headless", "--help"]

        run(add, env=env)
        assert_install_state(dsh_home, installed=True)
        assert_default_config(run(dump, env=env))
        if "Answer one task" not in run(boot_help, env=env):
            raise RuntimeError("headless profile did not boot with the installed plugin")

        user_patch = dsh_home / "profiles" / "headless" / "cordis.patch.yml"
        user_patch.write_text(
            "- id: refractrouter-validation\n"
            "  config:\n"
            "    allowPaidRuns: true\n"
            "    billingUnit: USD\n"
            "    maxProductionCost: 1.25\n"
            "    maxEvaluationCost: 0.5\n"
            "    maxRetries: 0\n",
            encoding="utf-8",
        )
        overridden = run(dump, env=env)
        for expected in (
            "allowPaidRuns: true",
            "billingUnit: USD",
            "maxProductionCost: 1.25",
            "maxEvaluationCost: 0.5",
            "maxRetries: 0",
        ):
            if expected not in overridden:
                raise RuntimeError(f"profile override was not composed: {expected}")

        user_patch.write_text("[]\n", encoding="utf-8")
        run(remove, env=env)
        assert_install_state(dsh_home, installed=False)
        if PACKAGE_NAME in run(dump, env=env):
            raise RuntimeError("removed plugin remains in the composed profile")

        run(add, env=env)
        assert_install_state(dsh_home, installed=True)
        assert_default_config(run(dump, env=env))
        run(boot_help, env=env)

        print(
            json.dumps(
                {
                    "status": "pass",
                    "profile": "headless",
                    "install": "local-path",
                    "lifecycle": ["install", "override", "remove", "reinstall", "boot"],
                    "versions": versions,
                    "paid_calls": 0,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
