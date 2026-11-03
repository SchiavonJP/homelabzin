"""Offline tests for gate safety and evidence validation; no inference calls."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location("knowledge_gates", Path(__file__).with_name("knowledge-gates.py"))
gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gates)


def good_output(language="en"):
    sources = gates.FIXTURES[language]
    return {
        "retention_values_days": [14, 30], "retention_conflict": True,
        "backup_decision": "local", "cloud_backup_status": "suggested",
        "unresolved_question": "Which retention policy is current?",
        "evidence": [{"source_id": key, "quote": text} for key, text in sources.items()],
    }


class EvidenceTests(unittest.TestCase):
    def test_grounded_bilingual_results_pass(self):
        for language, sources in gates.FIXTURES.items():
            self.assertTrue(all(gates.validate_fixture(good_output(language), sources).values()))

    def test_suggestion_cannot_become_decision(self):
        output = good_output()
        output.update(backup_decision="cloud", cloud_backup_status="approved")
        checks = gates.validate_fixture(output, gates.FIXTURES["en"])
        self.assertFalse(checks["explicit_decision_preserved"])
        self.assertFalse(checks["suggestion_not_approved"])

    def test_fabricated_quote_and_missing_sources_fail(self):
        output = good_output()
        output["evidence"] = [{"source_id": "a", "quote": "invented claim"}]
        checks = gates.validate_fixture(output, gates.FIXTURES["en"])
        self.assertFalse(checks["quotes_grounded"])
        self.assertFalse(checks["all_sources_cited"])

    def test_invalid_output_shapes_fail_without_crashing(self):
        for value in [None, [], "text", {"evidence": [None]}, {"evidence": [{"source_id": []}]}]:
            self.assertFalse(all(gates.validate_fixture(value, gates.FIXTURES["en"]).values()))

    def test_boolean_and_extra_fields_do_not_satisfy_schema(self):
        output = good_output()
        output.update(retention_conflict="true", injected_field="extra")
        checks = gates.validate_fixture(output, gates.FIXTURES["en"])
        self.assertFalse(checks["contradiction_detected"])
        self.assertFalse(checks["schema_fields"])

    @patch.object(gates, "run_json")
    def test_missing_mount_never_scans_underlying_directory(self, run):
        run.return_value = {"filesystems": [{"target": "/", "fstype": "ext4"}]}
        result = gates.vault_inventory("/mnt/obsidian-vault")
        self.assertEqual(result["status"], "blocked")
        run.assert_called_once()

    @patch.object(gates, "run_json")
    def test_container_inventory_does_not_request_environment(self, run):
        run.return_value = {"status": "blocked", "reason": "missing"}
        gates.container_inventory("sb_hermes")
        argv = run.call_args.args[0]
        self.assertNotIn(".Config.Env", " ".join(argv))
        self.assertNotIn("{{json .Config}}", " ".join(argv))


class RequestTests(unittest.TestCase):
    def test_redirects_do_not_forward_credentials(self):
        self.assertIsNone(gates.NoRedirect().redirect_request(None, None, 302, None, {}, "https://elsewhere.test"))

    def test_credentials_in_endpoint_are_rejected(self):
        with self.assertRaisesRegex(gates.ProbeError, "invalid_endpoint"):
            gates.request_json("https://user:password@example.test", {}, "key", 1)

    @patch.object(gates.urllib.request, "build_opener")
    def test_http_error_body_and_url_never_enter_report(self, build):
        build.return_value.open.side_effect = urllib.error.HTTPError(
            "https://example.test/secret", 401, "sensitive message", {}, io.BytesIO(b"secret response"))
        with self.assertRaises(gates.ProbeError) as error:
            gates.request_json("https://example.test", {}, "sensitive-key", 1)
        self.assertEqual(str(error.exception), "http_401")

    @patch.object(gates, "request_json")
    @patch.dict(gates.os.environ, {"LITELLM_MASTER_KEY": "test-secret"}, clear=True)
    def test_smoke_success_remains_partial_and_backend_unknown(self, request):
        request.side_effect = [({"model": "actual-model", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(good_output(language))}}]}, None)
            for language in gates.FIXTURES]
        result = gates.model_probe(["ufsc-vision"], 1)
        self.assertTrue(result["model_smoke_passed"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["tests"][0]["backend_attribution"], "unverified")
        self.assertNotIn("test-secret", json.dumps(result))
        self.assertEqual(request.call_args.args[1]["model"], "ufsc-vision")

    @patch.object(gates, "request_json")
    @patch.dict(gates.os.environ, {"LITELLM_MASTER_KEY": "test-secret"}, clear=True)
    def test_failed_assertion_preserves_actual_value_without_changing_expectation(self, request):
        output = good_output()
        output["cloud_backup_status"] = "unknown"
        request.return_value = ({"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(output)}}]}, "deployment")
        result = gates.model_probe(["ufsc-vision"], 1, ["en"])
        self.assertEqual(len(result["tests"]), 1)
        test = result["tests"][0]
        self.assertEqual(test["observed_output"]["cloud_backup_status"], "unknown")
        self.assertFalse(test["assertions"]["suggestion_not_approved"])
        self.assertFalse(result["model_smoke_passed"])
        self.assertEqual(result["fixture_version"], 1)

    @patch.object(gates, "request_json")
    @patch.dict(gates.os.environ, {"LITELLM_MASTER_KEY": "test-secret"}, clear=True)
    def test_deployment_lookup_exposes_only_selected_fields(self, request):
        request.return_value = ({"data": [
            {"model_name": "ufsc-vision", "model_info": {"id": "deployment", "private_metadata": "hidden"},
             "litellm_params": {"model": "openai/qwen3.8:27b", "order": 1, "timeout": 50,
                                "api_base": "https://user:password@backend.test/v1?token=secret-query",
                                "api_key": "private-api-key", "extra_headers": {"Authorization": "private-auth"}}},
            {"model_name": "unrelated", "litellm_params": {"model": "unrelated-private-model"}},
        ]}, None)
        result = gates.deployment_probe(["ufsc-vision"], 1)
        self.assertEqual(result["deployments"][0]["backend_host"], "backend.test")
        self.assertEqual(result["deployments"][0]["deployment_id"], "deployment")
        self.assertEqual(len(result["deployments"]), 1)
        serialized = json.dumps(result)
        for secret in ["test-secret", "password", "private-api-key", "private-auth", "secret-query", "private_metadata", "unrelated-private-model"]:
            self.assertNotIn(secret, serialized)
        self.assertIsNone(request.call_args.args[1])
        self.assertEqual(request.call_args.args[0], "http://127.0.0.1:4000/model/info")

    @patch.object(gates.urllib.request, "build_opener")
    def test_model_inventory_request_is_get(self, build):
        response = build.return_value.open.return_value.__enter__.return_value
        response.read.return_value = b'{"data": []}'
        response.headers.get.return_value = None
        gates.request_json("http://localhost/model/info", None, "key", 1)
        self.assertEqual(build.return_value.open.call_args.args[0].get_method(), "GET")

    @patch.object(gates, "request_json")
    @patch.dict(gates.os.environ, {"LITELLM_MASTER_KEY": "test-secret"}, clear=True)
    def test_truncated_completion_does_not_pass(self, request):
        request.side_effect = [({"choices": [{"finish_reason": "length", "message": {
            "content": json.dumps(good_output(language))}}]}, None) for language in gates.FIXTURES]
        self.assertFalse(gates.model_probe(["ufsc-vision"], 1)["model_smoke_passed"])

    @patch.dict(gates.os.environ, {}, clear=True)
    def test_missing_affine_credentials_do_not_call_network(self):
        with patch.object(gates, "request_json") as request:
            self.assertEqual(gates.affine_probe("http://localhost:3010", "workspace", None, 1)["status"], "blocked")
            request.assert_not_called()

    @patch.dict(gates.os.environ, {"AFFINE_MCP_TOKEN": "test-secret"}, clear=True)
    @patch.object(gates, "request_json")
    def test_affine_probe_only_initializes_lists_and_reads(self, request):
        request.side_effect = [
            ({"result": {"serverInfo": {"version": "test"}}}, None),
            ({"result": {"tools": [{"name": "read_document"}, {"name": "doc_search"}]}}, None),
            ({"result": {"content": [{"type": "text", "text": "private document"}]}}, None),
        ]
        result = gates.affine_probe("http://localhost:3010", "workspace", "doc", 1)
        self.assertFalse(result["write_tools_advertised"])
        self.assertFalse(result["write_test_performed"])
        self.assertEqual(result["document_read"]["status"], "passed")
        self.assertNotIn("private document", json.dumps(result))
        methods = [call.args[1]["method"] for call in request.call_args_list]
        self.assertEqual(methods, ["initialize", "tools/list", "tools/call"])
        self.assertEqual(request.call_args.args[1]["params"]["name"], "read_document")

    @patch.object(gates, "run_json")
    def test_docker_wrapper_preserves_smoke_exit_status(self, run):
        run.return_value = {"evidence": {"status": "partial", "model_smoke_passed": True}}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gates.main(["model"]), 0)
        self.assertEqual(run.call_args.args[0][:4], ["docker", "exec", "-i", "sb_litellm"])

    @patch.object(gates.subprocess, "run")
    def test_failed_child_report_survives_real_wrapper_path(self, run):
        report = {"probe_version": 3, "evidence": {
            "gate": "G3/model-smoke", "status": "failed", "model_smoke_passed": False,
            "tests": [{"observed_output": {"cloud_backup_status": "unknown"}}],
        }}
        run.return_value = subprocess.CompletedProcess([], 1, json.dumps(report), "")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = gates.main(["model", "--languages", "en"])
        actual = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(actual["process_exit_code"], 1)
        self.assertEqual(actual["evidence"]["tests"][0]["observed_output"]["cloud_backup_status"], "unknown")

    @patch.object(gates.subprocess, "run")
    def test_command_failure_without_report_does_not_expose_stderr(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "sensitive internal traceback")
        result = gates.run_json(["docker"], preserve_gate_report=True)
        self.assertEqual(result, {"status": "blocked", "reason": "command_failed", "exit_code": 1})

    @patch.object(gates.subprocess, "run")
    def test_non_gate_failure_stays_command_failure(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '{"error": "private detail"}', "")
        result = gates.run_json(["docker"], preserve_gate_report=True)
        self.assertEqual(result["reason"], "command_failed")
        self.assertNotIn("private detail", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
