"""Structural checks for the proxy-chain Docker images.

These run without Docker. The semantic `xray run -test` gate runs on a build
host via scripts/build-images.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROLES = ("client-legacy", "client", "server-legacy", "server-exit", "server-gate")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class DockerImageTests(unittest.TestCase):
    def test_dockerfile_pins_base_by_digest_and_avoids_latest(self) -> None:
        text = (ROOT / "docker" / "Dockerfile").read_text()
        self.assertIn("@sha256:", text)
        self.assertNotIn(":latest", text)

    def test_entrypoint_selftests_before_exec(self) -> None:
        text = (ROOT / "docker" / "entrypoint.sh").read_text()
        self.assertIn("run -test", text)
        self.assertLess(text.index("run -test"), text.index("exec xray run"))

    def test_every_role_has_template_vars_and_env_example(self) -> None:
        for role in ROLES:
            self.assertTrue((ROOT / "docker" / "templates" / f"{role}.json").is_file(), role)
            self.assertTrue((ROOT / "docker" / "vars" / f"{role}.vars").is_file(), role)
            self.assertTrue((ROOT / "docker" / "env" / f"{role}.env.example").is_file(), role)

    def test_templates_carry_no_literal_secrets(self) -> None:
        for role in ROLES:
            text = (ROOT / "docker" / "templates" / f"{role}.json").read_text()
            self.assertNotRegex(text, UUID_RE, f"{role} template embeds a UUID")

    def test_env_examples_are_placeholders_only(self) -> None:
        for path in (ROOT / "docker" / "env").glob("*.env.example"):
            self.assertNotRegex(path.read_text(), UUID_RE, f"{path.name} embeds a UUID")

    def test_every_template_var_is_declared_and_renders(self) -> None:
        for role in ROLES:
            tpl = (ROOT / "docker" / "templates" / f"{role}.json").read_text()
            declared = {
                ln.strip()
                for ln in (ROOT / "docker" / "vars" / f"{role}.vars").read_text().splitlines()
                if ln.strip() and not ln.startswith("#")
            }
            used = set(re.findall(r"\$\{(\w+)\}", tpl))
            self.assertEqual(used - declared, set(), f"{role}: template uses undeclared vars")


if __name__ == "__main__":
    unittest.main()
