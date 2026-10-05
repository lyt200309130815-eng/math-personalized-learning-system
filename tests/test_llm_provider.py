"""Provider routing and fallback checks; all SDK calls are mocked."""

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from init_db import initialize_database
from services.feedback import build_feedback_context, build_rule_based_feedback, generate_learning_feedback
from services.llm_provider import (
    DEFAULT_GEMINI_MODEL, DEFAULT_DEEPSEEK_MODEL, LLMUnavailable, generate_text, get_provider_config,
)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "LLM_PROVIDER": "", "GEMINI_API_KEY": "", "GEMINI_MODEL": "",
            "OPENAI_API_KEY": "", "OPENAI_MODEL": "", "DEEPSEEK_API_KEY": "", "DEEPSEEK_MODEL": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)

    def sdk(self, text):
        client = Mock()
        client.models.generate_content.return_value.text = text
        client.responses.create.return_value.output_text = text
        client.chat.completions.create.return_value.choices = [Mock(message=Mock(content=text))]
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=client)
        factory.return_value.__exit__ = Mock(return_value=False)
        return factory, client

    def test_default_is_deepseek(self):
        config = get_provider_config()
        self.assertEqual(config["provider"], "deepseek")
        self.assertEqual(config["model"], DEFAULT_DEEPSEEK_MODEL)
        self.assertFalse(config["configured"])

    def test_gemini_returns_text_and_routes_only_to_gemini(self):
        factory, client = self.sdk("模拟反馈")
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.genai.Client", factory), \
                patch("services.llm_provider.OpenAI") as other:
            self.assertEqual(generate_text("测试"), "模拟反馈")
            client.models.generate_content.assert_called_once_with(model=DEFAULT_GEMINI_MODEL, contents="测试")
            other.assert_not_called()

    def test_deepseek_routes_chat_and_supports_system_prompt(self):
        factory, client = self.sdk("模拟反馈")
        with patch.dict(os.environ, {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.OpenAI", factory), \
                patch("services.llm_provider.genai.Client") as other:
            self.assertEqual(generate_text("测试", system_prompt="约束"), "模拟反馈")
            client.chat.completions.create.assert_called_once_with(
                model=DEFAULT_DEEPSEEK_MODEL,
                messages=[{"role": "system", "content": "约束"}, {"role": "user", "content": "测试"}],
                stream=False,
            )
            self.assertEqual(factory.call_args.kwargs["base_url"], "https://api.deepseek.com")
            client.responses.create.assert_not_called()
            other.assert_not_called()

    def test_deepseek_failures_are_safe(self):
        import httpx
        from openai import APIConnectionError, APIStatusError
        factory, client = self.sdk("unused")
        request = httpx.Request("POST", "https://example.invalid")
        errors = [APIConnectionError(request=request)] + [
            APIStatusError("private diagnostic", response=httpx.Response(status, request=request),
                           body={"error": {"code": "model_not_found" if status == 404 else "private"}})
            for status in (401, 402, 429, 404)
        ]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.OpenAI", factory):
            for error in errors:
                with self.subTest(error=type(error).__name__):
                    client.chat.completions.create.side_effect = error
                    with self.assertRaisesRegex(LLMUnavailable, "暂时不可用") as caught:
                        generate_text("测试")
                    self.assertNotIn("private", str(caught.exception))

    def test_deepseek_model_override(self):
        factory, client = self.sdk("模拟反馈")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-placeholder", "DEEPSEEK_MODEL": "test-model"}), \
                patch("services.llm_provider.OpenAI", factory):
            generate_text("测试")
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "test-model")

    def test_deepseek_page_reruns_do_not_repeat_requests(self):
        context = build_feedback_context("S001", database_path=self.path)
        factory, client = self.sdk(build_rule_based_feedback(context))
        page = Path(__file__).resolve().parents[1] / "pages" / "feedback.py"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-placeholder"}), \
                patch("services.feedback.build_feedback_context", return_value=context), \
                patch("services.llm_provider.OpenAI", factory):
            app = AppTest.from_file(str(page)).run()
            client.chat.completions.create.assert_not_called()
            self.assertTrue(any("当前 AI 服务：DeepSeek" in item.value for item in app.markdown))
            app.button[0].click().run()
            app.run()
            client.chat.completions.create.assert_called_once()
            self.assertEqual(len(app.exception), 0)

    def test_openai_returns_text_and_routes_only_to_openai(self):
        factory, client = self.sdk("模拟反馈")
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.OpenAI", factory), \
                patch("services.llm_provider.genai.Client") as other:
            self.assertEqual(generate_text("测试"), "模拟反馈")
            client.responses.create.assert_called_once()
            self.assertFalse(client.responses.create.call_args.kwargs["store"])
            other.assert_not_called()

    def test_missing_keys_allow_rule_fallback_for_both_providers(self):
        context = build_feedback_context("TEST", database_path=self.path)
        for provider, name in (("gemini", "Gemini"), ("openai", "OpenAI"), ("deepseek", "DeepSeek")):
            with self.subTest(provider=provider), patch.dict(os.environ, {"LLM_PROVIDER": provider}), \
                    patch("services.llm_provider.genai.Client") as gemini, \
                    patch("services.llm_provider.OpenAI") as openai:
                with self.assertRaisesRegex(LLMUnavailable, f"尚未配置 {name} AI 服务"):
                    generate_learning_feedback("TEST", context=context)
                self.assertIn("尚未评估", build_rule_based_feedback(context))
                gemini.assert_not_called()
                openai.assert_not_called()

    def test_switching_preserves_mastery_recommendation_and_database(self):
        context = build_feedback_context("TEST", database_path=self.path)
        before = copy.deepcopy(context)
        database_bytes = self.path.read_bytes()
        text = build_rule_based_feedback(context)
        for provider, target in (("gemini", "genai.Client"), ("openai", "OpenAI"), ("deepseek", "OpenAI")):
            factory, _ = self.sdk(text)
            with patch.dict(os.environ, {"LLM_PROVIDER": provider,
                                        "GEMINI_API_KEY": "test-placeholder", "OPENAI_API_KEY": "test-placeholder", "DEEPSEEK_API_KEY": "test-placeholder"}), \
                    patch("services.llm_provider." + target, factory):
                self.assertEqual(generate_learning_feedback("TEST", context=context), text)
                self.assertEqual(context, before)
                self.assertEqual(build_feedback_context("TEST", database_path=self.path), before)
                self.assertEqual(self.path.read_bytes(), database_bytes)

    def test_gemini_error_is_sanitized_and_fallback_works(self):
        factory, client = self.sdk("unused")
        client.models.generate_content.side_effect = RuntimeError("private credential diagnostic")
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.genai.Client", factory):
            with self.assertRaisesRegex(LLMUnavailable, "暂时不可用") as caught:
                generate_text("测试")
            self.assertNotIn("private", str(caught.exception))
        self.assertIn("本次学习表现", build_rule_based_feedback(build_feedback_context("TEST", database_path=self.path)))

    def test_invalid_provider_is_safe(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "unknown"}):
            with self.assertRaisesRegex(LLMUnavailable, "配置无效"):
                generate_text("测试")

    def test_gemini_model_override(self):
        factory, client = self.sdk("模拟反馈")
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_MODEL": "test-model", "GEMINI_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.genai.Client", factory):
            generate_text("测试")
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "test-model")

    def test_gemini_empty_text_is_unavailable(self):
        factory, _ = self.sdk(None)
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-placeholder"}), \
                patch("services.llm_provider.genai.Client", factory):
            with self.assertRaises(LLMUnavailable):
                generate_text("测试")

    def test_page_gemini_missing_key_and_provider_switch_clear_cached_text(self):
        context = build_feedback_context("TEST", database_path=self.path)
        page = Path(__file__).resolve().parents[1] / "pages" / "feedback.py"
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}), \
                patch("services.feedback.build_feedback_context", return_value=context), \
                patch("services.llm_provider.genai.Client") as gemini, \
                patch("services.llm_provider.OpenAI") as openai:
            app = AppTest.from_file(str(page)).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("Gemini", app.info[0].value)
            self.assertTrue(app.button[0].disabled)
            app.button[1].click().run()
            self.assertIsNotNone(app.session_state["learning_feedback"])
            with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}):
                app.run()
                self.assertIsNone(app.session_state["learning_feedback"])
                self.assertIn("OpenAI", app.info[0].value)
            gemini.assert_not_called()
            openai.assert_not_called()
