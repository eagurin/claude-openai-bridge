#!/usr/bin/env python3
"""
Интеграционные тесты для GitHub интеграции claude-openai-bridge

Покрывает:
- GitHub webhook обработку  
- API endpoints
- Безопасность и валидацию
- GitHub Action совместимость
- OpenAI API совместимость
"""

import pytest
import asyncio
import json
import hmac
import hashlib
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Импорты из основного приложения
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.server import app, CONFIG, github_adapter, verify_github_signature
from src.server import GitHubWebhookPayload, GitHubActionContext

class TestGitHubWebhookSecurity:
    """Тесты безопасности GitHub webhook"""
    
    def test_verify_github_signature_valid(self):
        """Тест корректной проверки подписи"""
        secret = "test_secret"
        payload = b'{"test": "data"}'
        
        # Создаем корректную подпись
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        signature_header = f"sha256={signature}"
        
        assert verify_github_signature(payload, signature_header, secret) == True
    
    def test_verify_github_signature_invalid(self):
        """Тест некорректной подписи"""
        secret = "test_secret"
        payload = b'{"test": "data"}'
        wrong_signature = "sha256=invalid_signature"
        
        assert verify_github_signature(payload, wrong_signature, secret) == False
    
    def test_verify_github_signature_wrong_format(self):
        """Тест неправильного формата подписи"""
        secret = "test_secret"
        payload = b'{"test": "data"}'
        
        # Без префикса sha256=
        assert verify_github_signature(payload, "invalid_format", secret) == False
        
        # Пустая подпись
        assert verify_github_signature(payload, "", secret) == False
        
        # None подпись
        assert verify_github_signature(payload, None, secret) == False

class TestGitHubWebhookProcessing:
    """Тесты обработки GitHub webhook"""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)
    
    @pytest.fixture
    def sample_issue_comment_payload(self):
        """Пример payload для issue comment"""
        return {
            "action": "created",
            "comment": {
                "id": 123,
                "body": "@claude please help with this issue",
                "user": {"login": "test-user", "id": 1},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/repo/issues/1#issuecomment-123"
            },
            "repository": {
                "id": 1,
                "name": "test-repo",
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo",
                "default_branch": "main",
                "private": False
            },
            "sender": {"login": "test-user", "id": 1}
        }
    
    @pytest.fixture
    def sample_pr_comment_payload(self):
        """Пример payload для PR comment"""
        return {
            "action": "created",
            "comment": {
                "id": 456,
                "body": "/review please check this code",
                "user": {"login": "developer", "id": 2},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/repo/pull/1#issuecomment-456"
            },
            "pull_request": {
                "id": 100,
                "number": 1,
                "title": "Add feature",
                "body": "This PR adds a new feature",
                "state": "open",
                "user": {"login": "developer", "id": 2},
                "base": {"ref": "main"},
                "head": {"ref": "feature/new"},
                "html_url": "https://github.com/test/repo/pull/1",
                "diff_url": "https://github.com/test/repo/pull/1.diff",
                "patch_url": "https://github.com/test/repo/pull/1.patch"
            },
            "repository": {
                "id": 1,
                "name": "test-repo",
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo",
                "default_branch": "main",
                "private": False
            },
            "sender": {"login": "developer", "id": 2}
        }
    
    def test_github_status_endpoint(self, client):
        """Тест endpoint статуса GitHub интеграции"""
        response = client.get("/github/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "github_integration_enabled" in data
        assert "webhook_secret_configured" in data
        assert "supported_events" in data
        assert "trigger_phrases" in data
    
    @patch('src.server.CONFIG', {**CONFIG, 'require_webhook_signature': False})
    @patch.object(github_adapter, 'create_response')
    async def test_webhook_issue_comment_without_signature(
        self, 
        mock_create_response,
        client, 
        sample_issue_comment_payload
    ):
        """Тест webhook без проверки подписи"""
        # Мокаем ответ адаптера
        mock_create_response.return_value = {
            "response": "Test response from Claude",
            "context": {},
            "metadata": {}
        }
        
        response = client.post(
            "/github/webhook",
            json=sample_issue_comment_payload,
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "test-123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Webhook processed successfully"
        assert data["event_type"] == "issue_comment"
    
    def test_webhook_unsupported_event(self, client):
        """Тест webhook с неподдерживаемым событием"""
        payload = {"action": "opened", "repository": {}}
        
        response = client.post(
            "/github/webhook",
            json=payload,
            headers={
                "X-GitHub-Event": "push",  # Неподдерживаемое событие
                "X-GitHub-Delivery": "test-456"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "ignored" in data["message"]
    
    def test_webhook_invalid_json(self, client):
        """Тест webhook с невалидным JSON"""
        response = client.post(
            "/github/webhook",
            data="invalid json",
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issue_comment"
            }
        )
        
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["error"]

class TestGitHubActionAdapter:
    """Тесты GitHubActionAdapter"""
    
    @pytest.fixture
    def adapter(self):
        """Экземпляр адаптера для тестирования"""
        return github_adapter
    
    def test_should_respond_with_trigger_phrases(self, adapter):
        """Тест определения необходимости ответа"""
        # Должен отвечать на триггерные фразы
        assert adapter.should_respond("@claude help me") == True
        assert adapter.should_respond("Hey @ai, what do you think?") == True
        assert adapter.should_respond("/review this code please") == True
        assert adapter.should_respond("/analyze for bugs") == True
        assert adapter.should_respond("Can you /help with this?") == True
        assert adapter.should_respond("Please /fix this issue") == True
        
        # Не должен отвечать без триггерных фраз
        assert adapter.should_respond("Just a regular comment") == False
        assert adapter.should_respond("Thanks for the fix!") == False
    
    @pytest.mark.asyncio
    async def test_process_issue_comment_webhook(self, adapter):
        """Тест обработки issue comment webhook"""
        payload_data = {
            "action": "created",
            "comment": {
                "id": 123,
                "body": "@claude analyze this",
                "user": {"login": "user", "id": 1},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/repo/issues/1#issuecomment-123"
            },
            "repository": {
                "id": 1,
                "name": "test-repo",
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo",
                "default_branch": "main",
                "private": False
            },
            "sender": {"login": "user", "id": 1}
        }
        
        payload = GitHubWebhookPayload(**payload_data)
        context = await adapter.process_webhook(payload)
        
        assert context.event_type == "issue_comment"
        assert context.content == "@claude analyze this"
        assert context.comment_id == 123
        assert context.repository.full_name == "test/repo"
    
    @pytest.mark.asyncio
    async def test_process_pr_comment_webhook(self, adapter):
        """Тест обработки PR comment webhook"""
        payload_data = {
            "action": "created",
            "comment": {
                "id": 456,
                "body": "/review this implementation",
                "user": {"login": "dev", "id": 2},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/repo/pull/1#issuecomment-456"
            },
            "pull_request": {
                "id": 100,
                "number": 1,
                "title": "Feature",
                "body": "New feature",
                "state": "open",
                "user": {"login": "dev", "id": 2},
                "base": {"ref": "main"},
                "head": {"ref": "feature"},
                "html_url": "https://github.com/test/repo/pull/1",
                "diff_url": "https://github.com/test/repo/pull/1.diff",
                "patch_url": "https://github.com/test/repo/pull/1.patch"
            },
            "repository": {
                "id": 1,
                "name": "test-repo",
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo",
                "default_branch": "main",
                "private": False
            },
            "sender": {"login": "dev", "id": 2}
        }
        
        payload = GitHubWebhookPayload(**payload_data)
        context = await adapter.process_webhook(payload)
        
        assert context.event_type == "pull_request_comment"
        assert context.content == "/review this implementation"
        assert context.pr_number == 1
        assert context.comment_id == 456
    
    def test_build_system_context_for_pr(self, adapter):
        """Тест построения системного контекста для PR"""
        context = GitHubActionContext(
            event_type="pull_request_comment",
            action="created",
            repository=Mock(full_name="test/repo"),
            sender=Mock(login="user"),
            content="test content",
            pr_number=42
        )
        
        system_context = adapter._build_system_context(context)
        
        assert "Pull Request #42" in system_context
        assert "test/repo" in system_context
        assert "code review" in system_context.lower()
        assert "GitHub Markdown" in system_context

class TestOpenAICompatibility:
    """Тесты совместимости с OpenAI API"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_models_endpoint(self, client):
        """Тест endpoint списка моделей"""
        response = client.get("/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        
        # Проверяем наличие Claude моделей
        model_ids = [model["id"] for model in data["data"]]
        assert "claude-3-5-sonnet-20241022" in model_ids
        assert "claude-3-5-haiku-20241022" in model_ids
    
    @patch('src.server.bridge_adapter.execute_claude_request')
    def test_chat_completions_endpoint(self, mock_execute, client):
        """Тест endpoint chat completions"""
        # Мокаем ответ от Claude
        mock_execute.return_value = {
            "response": "Hello! I'm Claude, ready to help.",
            "metadata": {"cost_usd": 0.001, "duration_ms": 500}
        }
        
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {"role": "user", "content": "Hello Claude!"}
            ],
            "max_tokens": 100
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "usage" in data

class TestGitHubAPIIntegration:
    """Тесты интеграции с GitHub API"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    @patch('httpx.AsyncClient.get')
    def test_repository_info_endpoint(self, mock_get, client):
        """Тест получения информации о репозитории"""
        # Мокаем ответ GitHub API
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "name": "test-repo",
            "full_name": "owner/test-repo",
            "description": "Test repository",
            "language": "Python",
            "default_branch": "main",
            "private": False,
            "topics": ["python", "fastapi"],
            "html_url": "https://github.com/owner/test-repo"
        }
        mock_get.return_value = mock_response
        
        response = client.get("/github/repository/owner/test-repo")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["name"] == "test-repo"
        assert data["repository"]["language"] == "Python"
    
    @patch('httpx.AsyncClient.post')
    def test_comment_posting_endpoint(self, mock_post, client):
        """Тест создания комментария"""
        # Мокаем ответ GitHub API
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 456,
            "html_url": "https://github.com/owner/repo/issues/1#issuecomment-456"
        }
        mock_post.return_value = mock_response
        
        response = client.post(
            "/github/comment",
            params={
                "repo_full_name": "owner/repo",
                "issue_number": 1,
                "comment_body": "Test comment"
            },
            headers={"X-GitHub-Token": "test_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["comment_id"] == 456

class TestIntegrationScenarios:
    """Интеграционные тесты для полных сценариев"""
    
    @pytest.mark.asyncio
    @patch('src.server.bridge_adapter.execute_claude_request')
    async def test_full_pr_review_scenario(self, mock_execute):
        """Тест полного сценария review PR"""
        # Мокаем ответ Claude
        mock_execute.return_value = {
            "response": "## Code Review\n\nThis looks good! ✅",
            "metadata": {"cost_usd": 0.01, "duration_ms": 2000}
        }
        
        # Создаем тестовый контекст PR
        context = GitHubActionContext(
            event_type="pull_request_comment",
            action="created",
            repository=Mock(
                id=123,
                name="test-repo",
                full_name="owner/test-repo",
                html_url="https://github.com/owner/test-repo",
                default_branch="main",
                private=False
            ),
            sender=Mock(login="reviewer", id=456),
            content="/review please check this authentication code",
            pr_number=42,
            comment_id=789,
            diff_content="@@ -1,3 +1,4 @@\n def login():\n+    # Added validation\n     pass"
        )
        
        # Выполняем анализ
        result = await github_adapter.create_response(context)
        
        assert "response" in result
        assert "Code Review" in result["response"]
        assert result["context"]["pr_number"] == 42

# Функции для запуска тестов

def run_unit_tests():
    """Запуск unit тестов"""
    pytest.main([
        __file__ + "::TestGitHubWebhookSecurity",
        __file__ + "::TestGitHubActionAdapter",
        "-v"
    ])

def run_integration_tests():
    """Запуск интеграционных тестов"""
    pytest.main([
        __file__ + "::TestGitHubWebhookProcessing",
        __file__ + "::TestOpenAICompatibility", 
        __file__ + "::TestGitHubAPIIntegration",
        __file__ + "::TestIntegrationScenarios",
        "-v"
    ])

def run_all_tests():
    """Запуск всех тестов"""
    pytest.main([__file__, "-v"])

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run GitHub integration tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only") 
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    if args.unit:
        run_unit_tests()
    elif args.integration:
        run_integration_tests()
    else:
        run_all_tests()