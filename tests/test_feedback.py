"""Feedback tests mock the SDK and use temporary databases only."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError
from streamlit.testing.v1 import AppTest

from database.database import record_attempt
from init_db import initialize_database
from services.feedback import (
    AIFeedbackUnavailable, DEFAULT_OPENAI_MODEL, FEEDBACK_HEADINGS, FEEDBACK_INSTRUCTIONS,
    build_feedback_context, build_rule_based_feedback, generate_learning_feedback,
)


class FeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        initialize_database(self.path)
        environment = patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.root = Path(__file__).resolve().parents[1]

    def context(self) -> dict:
        return build_feedback_context("S001", database_path=self.path)

    def sdk(self, text: str | None = None):
        client = Mock()
        client.responses.create.return_value.output_text = text or build_rule_based_feedback(self.context())
        factory = Mock()
        factory.return_value.__enter__ = Mock(return_value=client)
        factory.return_value.__exit__ = Mock(return_value=False)
        return factory, client

    def test_context_whitelists_only_learning_data(self) -> None:
        context = self.context()
        self.assertEqual(context["student_id"], "S001")
        self.assertEqual(context["topic"], "函数")
        self.assertEqual(len(context["knowledge_points"]), 5)
        self.assertEqual(context["recommendation"]["target_knowledge"]["knowledge_point_id"], "K001")
        serialized = json.dumps(context)
        for forbidden in (str(self.path), "OPENAI_API_KEY", "SELECT", "created_at", "user_answer", "stem"):
            self.assertNotIn(forbidden, serialized)

    def test_prompt_contains_decision_and_evidence_constraints(self) -> None:
        for constraint in ("不重新计算掌握度", "不改变推荐目标", "evidence_level", "数据较少",
                           "未评估", "不得否定确定性推荐", "不得生成最终成绩"):
            self.assertIn(constraint, FEEDBACK_INSTRUCTIONS)
        for heading in FEEDBACK_HEADINGS:
            self.assertIn(heading, FEEDBACK_INSTRUCTIONS)

    def test_mock_response_returns_text_and_preserves_inputs(self) -> None:
        record_attempt("S001", "Q001", "D", 1, 1, database_path=self.path)
        context = self.context()
        before_context = copy.deepcopy(context)
        before_database = self.path.read_bytes()
        expected = build_rule_based_feedback(context)
        factory, client = self.sdk(expected)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.OpenAI", factory):
            text = generate_learning_feedback("S001", context=context)
        self.assertEqual(text, expected)
        self.assertEqual(context, before_context)
        self.assertEqual(self.path.read_bytes(), before_database)
        client.responses.create.assert_called_once()
        arguments = client.responses.create.call_args.kwargs
        self.assertEqual(json.loads(arguments["input"]), context)
        self.assertFalse(arguments["store"])
        self.assertEqual(arguments["model"], DEFAULT_OPENAI_MODEL)
        self.assertEqual(factory.call_args.kwargs, {"timeout": 20.0, "max_retries": 0})

    def test_main_interface_reads_mastery_and_recommendation(self) -> None:
        factory, client = self.sdk()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.OpenAI", factory):
            generate_learning_feedback("S001", database_path=self.path)
        self.assertEqual(json.loads(client.responses.create.call_args.kwargs["input"]), self.context())

    def test_model_environment_override(self) -> None:
        factory, client = self.sdk()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder", "OPENAI_MODEL": "test-model"}), \
                patch("services.feedback.OpenAI", factory):
            generate_learning_feedback("S001", context=self.context())
        self.assertEqual(client.responses.create.call_args.kwargs["model"], "test-model")

    def test_missing_key_never_constructs_client(self) -> None:
        with patch("services.feedback.OpenAI") as factory:
            with self.assertRaisesRegex(AIFeedbackUnavailable, "尚未配置 AI 学习反馈服务"):
                generate_learning_feedback("S001", database_path=self.path)
        factory.assert_not_called()

    def test_api_error_is_redacted(self) -> None:
        factory, client = self.sdk()
        client.responses.create.side_effect = APIConnectionError(
            message="private internal diagnostic", request=httpx.Request("POST", "https://example.invalid"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.OpenAI", factory):
            with self.assertRaises(AIFeedbackUnavailable) as caught:
                generate_learning_feedback("S001", context=self.context())
        self.assertEqual(str(caught.exception), "AI学习反馈暂时不可用，请稍后重试。")
        self.assertNotIn("private", str(caught.exception))

    def test_empty_or_malformed_output_is_unavailable(self) -> None:
        factory, client = self.sdk()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.OpenAI", factory):
            for text in ("", "no required sections"):
                client.responses.create.return_value.output_text = text
                with self.assertRaises(AIFeedbackUnavailable):
                    generate_learning_feedback("S001", context=self.context())

    def test_fallback_unevaluated_and_five_sections(self) -> None:
        text = build_rule_based_feedback(self.context())
        for heading in FEEDBACK_HEADINGS:
            self.assertIn(heading, text)
        self.assertIn("尚未评估", text)
        self.assertNotIn("掌握度为0%", text)
        self.assertNotIn("能力差", text.replace("不代表能力差", ""))

    def test_fallback_high_score_low_evidence(self) -> None:
        record_attempt("S001", "Q001", "D", 1, 1, database_path=self.path)
        context = self.context()
        text = build_rule_based_feedback(context)
        self.assertIn("当前表现较好", text)
        self.assertIn("训练数据较少", text)
        self.assertNotIn("完全掌握", text)
        self.assertIn(context["recommendation"]["target_knowledge"]["knowledge_point_name"], text)

    def test_page_no_key_and_rule_fallback_never_calls_sdk(self) -> None:
        with patch("services.feedback.build_feedback_context", side_effect=lambda _: self.context()), \
                patch("services.feedback.OpenAI") as factory:
            app = AppTest.from_file(str(self.root / "pages" / "feedback.py")).run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("尚未配置", app.info[0].value)
            self.assertTrue(app.button[0].disabled)
            app.button[1].click().run()
            self.assertIn("本次学习表现", app.session_state["learning_feedback"])
            app.run()
        factory.assert_not_called()

    def test_page_only_calls_api_on_explicit_click_and_invalidates_stale_feedback(self) -> None:
        factory, client = self.sdk()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.build_feedback_context", side_effect=lambda _: self.context()), \
                patch("services.feedback.OpenAI", factory):
            app = AppTest.from_file(str(self.root / "pages" / "feedback.py")).run()
            client.responses.create.assert_not_called()
            app.button[0].click().run()
            self.assertEqual(client.responses.create.call_count, 1)
            app.run()
            self.assertEqual(client.responses.create.call_count, 1)
            self.assertEqual(app.button[0].label, "重新生成")
            app.button[0].click().run()
            self.assertEqual(client.responses.create.call_count, 2)
            record_attempt("S001", "Q001", "D", 1, 1, database_path=self.path)
            app.run()
            self.assertIsNone(app.session_state["learning_feedback"])
            self.assertEqual(client.responses.create.call_count, 2)
            self.assertEqual(len(app.exception), 0)

    def test_page_api_failure_shows_safe_error_and_rule_text(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("services.feedback.build_feedback_context", side_effect=lambda _: self.context()), \
                patch("services.feedback.generate_learning_feedback", side_effect=AIFeedbackUnavailable(
                    "AI学习反馈暂时不可用，请稍后重试。")) as generator:
            app = AppTest.from_file(str(self.root / "pages" / "feedback.py")).run()
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("暂时不可用", app.warning[0].value)
            self.assertEqual(app.session_state["learning_feedback_source"], "规则式学习反馈")
            app.run()
            generator.assert_called_once()


if __name__ == "__main__":
    unittest.main()
