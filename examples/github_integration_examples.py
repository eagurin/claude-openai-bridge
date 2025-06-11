#!/usr/bin/env python3
"""
Примеры использования GitHub интеграции для claude-openai-bridge

Этот файл содержит практические примеры для:
- Тестирования webhook обработки
- Интеграции с GitHub API  
- Создания кастомных сценариев
- Отладки и мониторинга
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional
import httpx
from datetime import datetime

# Базовая конфигурация
BRIDGE_BASE_URL = "http://localhost:8000"
GITHUB_API_BASE = "https://api.github.com"

class GitHubIntegrationExamples:
    """
    Класс с примерами интеграции GitHub и claude-openai-bridge
    """
    
    def __init__(self, bridge_url: str = BRIDGE_BASE_URL, github_token: Optional[str] = None):
        self.bridge_url = bridge_url
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        
    async def test_bridge_health(self) -> Dict[str, Any]:
        """
        Проверяет доступность claude-openai-bridge
        
        Пример использования:
        ```python
        examples = GitHubIntegrationExamples()
        health = await examples.test_bridge_health()
        print(f"Bridge status: {health['status']}")
        ```
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.bridge_url}/health")
                return {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "status_code": response.status_code,
                    "data": response.json() if response.status_code == 200 else None
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e)
                }
    
    async def test_github_integration_status(self) -> Dict[str, Any]:
        """
        Проверяет статус GitHub интеграции
        
        Возвращает конфигурацию интеграции и готовность компонентов
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.bridge_url}/github/status")
                return response.json()
            except Exception as e:
                return {"error": str(e)}
    
    async def simulate_issue_comment_webhook(
        self, 
        comment_body: str = "@claude please help with this code",
        repo_name: str = "test/repo",
        issue_number: int = 1
    ) -> Dict[str, Any]:
        """
        Симулирует GitHub webhook для комментария в Issue
        
        Args:
            comment_body: Текст комментария
            repo_name: Имя репозитория (owner/repo)  
            issue_number: Номер Issue
            
        Returns:
            Ответ от webhook обработчика
            
        Пример:
        ```python
        result = await examples.simulate_issue_comment_webhook(
            comment_body="@claude analyze this error",
            repo_name="myorg/myrepo", 
            issue_number=42
        )
        ```
        """
        webhook_payload = {
            "action": "created",
            "comment": {
                "id": 123456,
                "body": comment_body,
                "user": {
                    "login": "test-developer",
                    "id": 12345
                },
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "html_url": f"https://github.com/{repo_name}/issues/{issue_number}#issuecomment-123456"
            },
            "issue": {
                "id": 987654,
                "number": issue_number,
                "title": "Test Issue",
                "body": "This is a test issue for debugging",
                "state": "open",
                "user": {
                    "login": "issue-creator",
                    "id": 54321
                },
                "html_url": f"https://github.com/{repo_name}/issues/{issue_number}",
                "labels": []
            },
            "repository": {
                "id": 111222333,
                "name": repo_name.split("/")[1],
                "full_name": repo_name,
                "html_url": f"https://github.com/{repo_name}",
                "default_branch": "main",
                "private": False
            },
            "sender": {
                "login": "test-developer",
                "id": 12345
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "issue_comment",
            "X-GitHub-Delivery": "test-delivery-123"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.bridge_url}/github/webhook",
                    json=webhook_payload,
                    headers=headers
                )
                return {
                    "status_code": response.status_code,
                    "response": response.json()
                }
            except Exception as e:
                return {"error": str(e)}
    
    async def simulate_pr_comment_webhook(
        self,
        comment_body: str = "/review please check this implementation",
        repo_name: str = "test/repo",
        pr_number: int = 42
    ) -> Dict[str, Any]:
        """
        Симулирует GitHub webhook для комментария в Pull Request
        
        Включает дополнительные данные PR для контекстного анализа
        """
        webhook_payload = {
            "action": "created",
            "comment": {
                "id": 789012,
                "body": comment_body,
                "user": {
                    "login": "reviewer",
                    "id": 67890
                },
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "html_url": f"https://github.com/{repo_name}/pull/{pr_number}#issuecomment-789012"
            },
            "pull_request": {
                "id": 345678,
                "number": pr_number,
                "title": "Add user authentication feature",
                "body": "This PR implements JWT-based authentication with role-based access control.",
                "state": "open",
                "user": {
                    "login": "feature-developer",
                    "id": 13579
                },
                "base": {
                    "ref": "main",
                    "sha": "abc123def456"
                },
                "head": {
                    "ref": "feature/auth",
                    "sha": "def456ghi789"
                },
                "html_url": f"https://github.com/{repo_name}/pull/{pr_number}",
                "diff_url": f"https://github.com/{repo_name}/pull/{pr_number}.diff",
                "patch_url": f"https://github.com/{repo_name}/pull/{pr_number}.patch"
            },
            "repository": {
                "id": 111222333,
                "name": repo_name.split("/")[1],
                "full_name": repo_name,
                "html_url": f"https://github.com/{repo_name}",
                "default_branch": "main",
                "private": False
            },
            "sender": {
                "login": "reviewer",
                "id": 67890
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": "issue_comment",  # PR comments тоже issue_comment
            "X-GitHub-Delivery": "test-pr-delivery-456"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.bridge_url}/github/webhook",
                    json=webhook_payload,
                    headers=headers
                )
                return {
                    "status_code": response.status_code,
                    "response": response.json()
                }
            except Exception as e:
                return {"error": str(e)}
    
    async def direct_content_analysis(
        self,
        content: str,
        event_type: str = "issue_comment",
        repo_name: str = "test/repo"
    ) -> Dict[str, Any]:
        """
        Прямой анализ контента через /github/analyze endpoint
        
        Полезно для:
        - Тестирования без webhook
        - Кастомных сценариев  
        - Интеграции с другими системами
        """
        analysis_request = {
            "event_type": event_type,
            "action": "created",
            "repository": {
                "id": 111222333,
                "name": repo_name.split("/")[1],
                "full_name": repo_name,
                "html_url": f"https://github.com/{repo_name}",
                "default_branch": "main",
                "private": False
            },
            "sender": {
                "login": "test-user",
                "id": 12345
            },
            "content": content
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.bridge_url}/github/analyze",
                    json=analysis_request
                )
                return {
                    "status_code": response.status_code,
                    "analysis": response.json()
                }
            except Exception as e:
                return {"error": str(e)}
    
    async def test_openai_compatibility(
        self,
        message: str = "Hello from GitHub integration test!",
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Dict[str, Any]:
        """
        Тестирует OpenAI совместимость claude-openai-bridge
        
        Проверяет работу базового API для взаимодействия с claude-code-action
        """
        openai_request = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an AI assistant integrated with GitHub. Respond helpfully and professionally."
                },
                {
                    "role": "user", 
                    "content": message
                }
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.bridge_url}/v1/chat/completions",
                    json=openai_request
                )
                return {
                    "status_code": response.status_code,
                    "openai_response": response.json()
                }
            except Exception as e:
                return {"error": str(e)}
    
    async def get_repository_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Получает информацию о репозитории через bridge
        
        Демонстрирует интеграцию с GitHub API
        """
        headers = {}
        if self.github_token:
            headers["X-GitHub-Token"] = self.github_token
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.bridge_url}/github/repository/{owner}/{repo}",
                    headers=headers
                )
                return {
                    "status_code": response.status_code,
                    "repository_info": response.json()
                }
            except Exception as e:
                return {"error": str(e)}
    
    async def get_pull_request_with_diff(
        self, 
        owner: str, 
        repo: str, 
        pr_number: int,
        include_diff: bool = True
    ) -> Dict[str, Any]:
        """
        Получает детальную информацию о PR включая diff
        
        Полезно для анализа изменений кода
        """
        headers = {}
        if self.github_token:
            headers["X-GitHub-Token"] = self.github_token
            
        params = {"include_diff": "true"} if include_diff else {}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.bridge_url}/github/pull/{owner}/{repo}/{pr_number}",
                    headers=headers,
                    params=params
                )
                return {
                    "status_code": response.status_code,
                    "pr_info": response.json()
                }
            except Exception as e:
                return {"error": str(e)}

# Utility функции для тестирования

async def run_comprehensive_test() -> None:
    """
    Запускает полный набор тестов для проверки интеграции
    """
    examples = GitHubIntegrationExamples()
    
    print("🧪 Comprehensive GitHub Integration Test")
    print("=" * 50)
    
    # 1. Проверка доступности bridge
    print("\n1. Testing bridge health...")
    health = await examples.test_bridge_health()
    print(f"   Status: {health.get('status', 'unknown')}")
    
    # 2. Проверка GitHub интеграции
    print("\n2. Testing GitHub integration status...")
    github_status = await examples.test_github_integration_status()
    if 'error' not in github_status:
        print(f"   Integration enabled: {github_status.get('github_integration_enabled')}")
        print(f"   Webhook configured: {github_status.get('webhook_secret_configured')}")
    
    # 3. Тест OpenAI совместимости
    print("\n3. Testing OpenAI compatibility...")
    openai_test = await examples.test_openai_compatibility(
        "Test message for GitHub integration"
    )
    if openai_test.get('status_code') == 200:
        response = openai_test.get('openai_response', {})
        choices = response.get('choices', [])
        if choices:
            content = choices[0].get('message', {}).get('content', '')
            print(f"   Response preview: {content[:100]}...")
    
    # 4. Тест Issue comment webhook
    print("\n4. Testing Issue comment webhook...")
    issue_test = await examples.simulate_issue_comment_webhook(
        "@claude please help debug this authentication issue"
    )
    print(f"   Webhook status: {issue_test.get('status_code')}")
    
    # 5. Тест PR comment webhook  
    print("\n5. Testing PR comment webhook...")
    pr_test = await examples.simulate_pr_comment_webhook(
        "/review check for security vulnerabilities in this auth code"
    )
    print(f"   PR webhook status: {pr_test.get('status_code')}")
    
    # 6. Тест прямого анализа
    print("\n6. Testing direct content analysis...")
    analysis_test = await examples.direct_content_analysis(
        "@claude analyze this Python function for performance improvements:\n\ndef slow_function(data):\n    result = []\n    for item in data:\n        if item > 0:\n            result.append(item * 2)\n    return result"
    )
    print(f"   Analysis status: {analysis_test.get('status_code')}")
    
    print("\n✅ Comprehensive test completed!")

async def run_performance_test(iterations: int = 10) -> None:
    """
    Тестирует производительность интеграции
    """
    examples = GitHubIntegrationExamples()
    
    print(f"⚡ Performance Test ({iterations} iterations)")
    print("=" * 40)
    
    import time
    
    total_time = 0
    successful_requests = 0
    
    for i in range(iterations):
        start_time = time.time()
        
        result = await examples.test_openai_compatibility(
            f"Performance test iteration {i+1}"
        )
        
        end_time = time.time()
        iteration_time = end_time - start_time
        total_time += iteration_time
        
        if result.get('status_code') == 200:
            successful_requests += 1
            
        print(f"   Iteration {i+1}: {iteration_time:.2f}s")
    
    avg_time = total_time / iterations
    success_rate = (successful_requests / iterations) * 100
    
    print(f"\n📊 Results:")
    print(f"   Average response time: {avg_time:.2f}s")
    print(f"   Success rate: {success_rate:.1f}%")
    print(f"   Total time: {total_time:.2f}s")

async def demo_custom_scenario() -> None:
    """
    Демонстрирует кастомный сценарий использования
    """
    examples = GitHubIntegrationExamples()
    
    print("🎯 Custom Scenario Demo: Code Security Review")
    print("=" * 50)
    
    # Симулируем PR с потенциально небезопасным кодом
    security_code = """
@claude please review this login function for security issues:

```python
def login_user(username, password):
    # TODO: This needs security review
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    result = db.execute(query)
    return result.fetchone()
```

I'm concerned about potential vulnerabilities.
"""
    
    print("\n📝 Analyzing security code...")
    
    # Отправляем на анализ
    result = await examples.direct_content_analysis(
        content=security_code,
        event_type="pull_request_comment"
    )
    
    if result.get('status_code') == 200:
        analysis = result.get('analysis', {})
        response_text = analysis.get('response', '')
        
        print("\n🤖 Claude's Security Analysis:")
        print("-" * 30)
        print(response_text[:500] + "..." if len(response_text) > 500 else response_text)
    else:
        print(f"❌ Analysis failed: {result.get('error', 'Unknown error')}")

# Главная функция для запуска примеров
async def main():
    """
    Главная функция для демонстрации возможностей
    """
    print("🚀 Claude OpenAI Bridge - GitHub Integration Examples")
    print("=" * 60)
    
    # Проверяем доступность сервера
    examples = GitHubIntegrationExamples()
    health = await examples.test_bridge_health()
    
    if health.get('status') != 'healthy':
        print("❌ Bridge server is not available!")
        print("   Please start the server with: python src/server.py")
        return
    
    print("✅ Bridge server is healthy!")
    
    # Запускаем демонстрации
    print("\n" + "="*60)
    await run_comprehensive_test()
    
    print("\n" + "="*60)
    await demo_custom_scenario()
    
    print("\n" + "="*60)
    await run_performance_test(5)  # 5 итераций для демо
    
    print("\n🎉 All demos completed successfully!")

if __name__ == "__main__":
    # Запуск примеров
    asyncio.run(main())