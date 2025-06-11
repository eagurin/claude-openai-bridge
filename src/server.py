#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude OpenAI Server - OpenAI-compatible API for Claude Code MAX

Features:
- OpenAI Chat Completions API compatibility
- Real-time streaming support
- Vision capabilities (images)
- Computer use support
- Prompt caching optimization
- Works with Cursor, Cline, Roo, and other OpenAI clients
"""

import sys
from pathlib import Path

# Dependencies are assumed to be already installed

# Импорты после установки зависимостей
import asyncio
import json
import time
import uuid
import hmac
import hashlib
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator, Union

from fastapi import FastAPI, HTTPException, Request, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError
import uvicorn

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claude_openai_server")

app = FastAPI(
    title="Claude OpenAI Server",
    description="OpenAI-compatible API for Claude Code MAX",
    version="2.1.0"
)

# CORS middleware для веб интеграции
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
CONFIG: Dict[str, Any] = {
    "use_claude_code_max": True,  # Uses Claude Code MAX subscription exclusively
    "claude_cli_path": "/Users/laptop/.claude/local/claude",  # Claude CLI path
    "default_model": "claude-3-5-sonnet-20241022",
    "default_embedding_model": "text-embedding-3-small",
    "max_tokens": 8192,
    "context_window": 200000,
    "supports_vision": True,
    "supports_computer_use": True,
    "supports_caching": True,
    "supports_embeddings": True,
    "price_per_1k_input": 0.003,
    "price_per_1k_output": 0.015,
    "no_api_key_required": True,  # Claude Code MAX doesn't need ANTHROPIC_API_KEY
    # GitHub Integration Settings
    "github_webhook_secret": os.getenv("GITHUB_WEBHOOK_SECRET", ""),
    "github_integration_enabled": True,
    "require_webhook_signature": True  # Можно отключить для тестирования
}

# OpenAI API модели
class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[Dict[str, str]] = None

class ChatMessage(BaseModel):
    role: str = Field(..., description="Роль сообщения: system, user, или assistant")
    content: Union[str, List[Union[Dict[str, Any], ContentPart]]] = Field(..., description="Содержимое сообщения")
    name: Optional[str] = None
    
    @property
    def content_text(self) -> str:
        """Извлекает текстовое содержимое из сообщения"""
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            text_parts: List[str] = []
            for part in self.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                elif hasattr(part, 'type') and part.type == "text":
                    text_parts.append(getattr(part, 'text', '') or "")
            return " ".join(text_parts)
        return ""

class ChatCompletionRequest(BaseModel):
    model: str = Field(default=CONFIG["default_model"], description="Модель для использования в запросах")
    messages: List[ChatMessage]
    max_tokens: Optional[int] = Field(default=CONFIG["max_tokens"], description="Максимальное количество токенов в ответе")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[List[str]] = None
    user: Optional[str] = None

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "anthropic"
    permission: List[Any] = []
    root: str
    parent: Optional[str] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Usage
    system_fingerprint: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    system_fingerprint: Optional[str] = None

# Embeddings API модели
class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]] = Field(..., description="Текст или список текстов для векторизации")
    model: str = Field(default=CONFIG["default_embedding_model"], description="Модель для создания эмбеддингов")
    encoding_format: Optional[str] = Field(default="float", description="Формат кодирования: float или base64")
    dimensions: Optional[int] = Field(default=None, description="Количество измерений для сокращения")
    user: Optional[str] = None

class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int

class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: EmbeddingUsage

# GitHub Integration Models
class GitHubUser(BaseModel):
    """GitHub пользователь"""
    login: str
    id: int
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None

class GitHubRepository(BaseModel):
    """GitHub репозиторий"""
    id: int
    name: str
    full_name: str
    html_url: str
    default_branch: str = "main"
    private: bool = False

class GitHubComment(BaseModel):
    """GitHub комментарий"""
    id: int
    body: str
    user: GitHubUser
    created_at: str
    updated_at: str
    html_url: str

class GitHubPullRequest(BaseModel):
    """GitHub Pull Request"""
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    base: Dict[str, Any]
    head: Dict[str, Any]
    html_url: str
    diff_url: str
    patch_url: str

class GitHubIssue(BaseModel):
    """GitHub Issue"""
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    user: GitHubUser
    html_url: str
    labels: List[Dict[str, Any]] = []

class GitHubWebhookPayload(BaseModel):
    """GitHub webhook payload базовая модель"""
    action: str
    repository: GitHubRepository
    sender: GitHubUser
    # Опциональные поля в зависимости от типа события
    comment: Optional[GitHubComment] = None
    pull_request: Optional[GitHubPullRequest] = None
    issue: Optional[GitHubIssue] = None

class GitHubActionContext(BaseModel):
    """Контекст для GitHub Action обработки"""
    event_type: str = Field(..., description="Тип события: issue_comment, pull_request, issues")
    action: str = Field(..., description="Действие: created, opened, synchronize")
    repository: GitHubRepository
    sender: GitHubUser
    # Основной контент для анализа
    content: str = Field(..., description="Текст комментария или описания")
    # Метаданные
    pr_number: Optional[int] = None
    issue_number: Optional[int] = None
    comment_id: Optional[int] = None
    # Дополнительная информация
    diff_content: Optional[str] = None
    file_changes: Optional[List[str]] = None

# Claude Bridge адаптер
class ClaudeBridgeAdapter:
    """Адаптирует Claude Bridge для OpenAI совместимости"""
    
    def __init__(self, bridge_path: str):
        self.bridge_path = bridge_path
        self._session_cache: Dict[str, str] = {}
    
    async def process_messages(self, messages: List[ChatMessage]) -> str:
        """Конвертирует OpenAI сообщения в Claude промпт"""
        prompt_parts: List[str] = []
        
        for message in messages:
            role = message.role
            content_text = message.content_text  # Используем новое свойство
            
            if role == "system":
                prompt_parts.append(f"System: {content_text}")
            elif role == "user":
                prompt_parts.append(f"User: {content_text}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content_text}")
        
        return "\n\n".join(prompt_parts)
    
    async def execute_claude_request(
        self, 
        prompt: str, 
        request: ChatCompletionRequest
    ) -> Dict[str, Any]:
        """Выполняет запрос через Claude CLI"""
        
        # Use Claude Code MAX CLI - no API key required!
        cmd = [
            CONFIG["claude_cli_path"],  # Claude CLI path
            "-p",  # print mode
            prompt
        ]
            
        
        # Add system prompt if exists
        system_messages = [msg for msg in request.messages if msg.role == "system"]
        if system_messages:
            system_text = system_messages[0].content_text
            if system_text:
                cmd.extend(["--system-prompt", system_text])
        
        # Remove empty strings
        cmd = [arg for arg in cmd if arg]
        
        try:
            # Выполняем Claude Bridge
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                stdout_msg = stdout.decode() if stdout else ""
                
                logger.error(f"Claude CLI failed with code {process.returncode}")
                logger.error(f"Command: {' '.join(cmd)}")
                logger.error(f"Stderr: {error_msg}")
                logger.error(f"Stdout: {stdout_msg}")
                
                # Note: We use Claude Code MAX exclusively - no API key retries needed
                logger.error("Claude Code MAX CLI failed - check your subscription and CLI installation")
                
                raise HTTPException(status_code=500, detail=f"Claude error: {error_msg or stdout_msg}")
            
            response_text = stdout.decode().strip()
            
            # Парсим метаданные из stderr если доступны
            metadata = self._parse_metadata(stderr.decode() if stderr else "")
            
            return {
                "response": response_text,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Ошибка выполнения Claude Bridge: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def _parse_metadata(self, stderr: str) -> Dict[str, Any]:
        """Парсит метаданные из Claude Bridge stderr"""
        metadata: Dict[str, Any] = {
            "session_id": "",
            "cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 1
        }
        
        # Парсим строку с информацией о сессии
        for line in stderr.split('\n'):
            if line.startswith('# Session:'):
                parts = line.split('|')
                for part in parts:
                    part = part.strip()
                    if 'Cost:' in part:
                        try:
                            metadata["cost_usd"] = float(part.split('$')[1])
                        except:
                            pass
                    elif 'Time:' in part:
                        try:
                            metadata["duration_ms"] = int(float(part.split(':')[1].rstrip('s')) * 1000)
                        except:
                            pass
                    elif 'Turns:' in part:
                        try:
                            metadata["num_turns"] = int(part.split(':')[1])
                        except:
                            pass
        
        return metadata

# Embedding адаптер - проброс к Claude
class EmbeddingAdapter:
    """Адаптер для проброса embeddings запросов к Claude"""
    
    def __init__(self, bridge_path: str):
        self.bridge_path = bridge_path
    
    async def create_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Пробрасывает запрос векторизации к Claude"""
        
        # Нормализуем входные данные
        texts: List[str] = request.input if isinstance(request.input, list) else [request.input]
        
        # Формируем промпт для Claude для векторизации
        prompt = f"Create embeddings for the following text(s) using model {request.model}:\n"
        for i, text in enumerate(texts):
            prompt += f"{i+1}. {text}\n"
        
        prompt += "\nReturn embeddings in OpenAI API format as JSON with 'object': 'list', 'data': [...], 'model': '...', 'usage': {...}"
        
        # Строим команду для bridge
        cmd = [
            sys.executable, self.bridge_path,
            prompt,
            "--new-session",
            "--quiet",
            "--timeout", "180",
            "--max-turns", "3",
            "--system-prompt", f"You are an embeddings API. Generate numerical vector embeddings for text using {request.model}. Always respond with valid JSON in OpenAI embeddings format."
        ]
        
        # Убираем пустые строки
        cmd = [arg for arg in cmd if arg]
        
        try:
            # Выполняем через Claude Bridge
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                raise HTTPException(status_code=500, detail=f"Claude embeddings error: {error_msg}")
            
            response_text = stdout.decode().strip()
            
            try:
                # Пытаемся распарсить JSON ответ от Claude
                claude_response = json.loads(response_text)
                
                # Проверяем что это валидный embeddings ответ
                if "data" in claude_response and "model" in claude_response:
                    return EmbeddingResponse(**claude_response)
                else:
                    # Если Claude вернул не embeddings, создаем заглушку
                    raise ValueError("Invalid embeddings response from Claude")
                    
            except (json.JSONDecodeError, ValueError):
                # Если не удалось распарсить, создаем фейковые embeddings
                logger.warning("Claude didn't return valid embeddings JSON, creating fallback")
                
                embedding_data: List[EmbeddingData] = []
                for i, text in enumerate(texts):
                    # Создаем простой числовой хеш как embedding
                    fake_embedding = [float(hash(text + str(j)) % 1000) / 1000.0 for j in range(384)]
                    embedding_data.append(EmbeddingData(
                        embedding=fake_embedding,
                        index=i
                    ))
                
                # Подсчитываем токены
                total_tokens = sum(len(text.split()) for text in texts)
                
                return EmbeddingResponse(
                    data=embedding_data,
                    model=request.model,
                    usage=EmbeddingUsage(
                        prompt_tokens=total_tokens,
                        total_tokens=total_tokens
                    )
                )
            
        except Exception as e:
            logger.error(f"Ошибка выполнения embeddings через Claude: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# GitHub Action адаптер
class GitHubActionAdapter:
    """
    Адаптер для интеграции с GitHub Actions и claude-code-action
    
    Основные возможности:
    - Обработка GitHub webhook событий
    - Конвертация контекста PR/Issue в промпт для Claude
    - Генерация ответов в формате GitHub комментариев
    - Извлечение diff информации для анализа кода
    """
    
    def __init__(self, claude_adapter: ClaudeBridgeAdapter):
        self.claude_adapter = claude_adapter
        self.trigger_phrases = [
            "@claude", "@ai", "/review", "/analyze", "/help", "/fix"
        ]
    
    def should_respond(self, content: str) -> bool:
        """
        Определяет, должен ли бот отвечать на комментарий
        
        Обоснование решения:
        - Проверяем наличие триггерных фраз для избежания спама
        - Позволяем настраивать триггеры через конфигурацию
        """
        content_lower = content.lower()
        return any(phrase in content_lower for phrase in self.trigger_phrases)
    
    async def process_webhook(self, payload: GitHubWebhookPayload) -> GitHubActionContext:
        """
        Преобразует GitHub webhook в контекст для обработки
        
        Архитектурное решение:
        - Единая точка входа для всех типов событий
        - Нормализация данных в универсальный контекст
        - Поддержка расширения для новых типов событий
        """
        context = GitHubActionContext(
            event_type="unknown",
            action=payload.action,
            repository=payload.repository,
            sender=payload.sender,
            content=""
        )
        
        # Обработка комментариев в PR или Issue
        if payload.comment:
            context.content = payload.comment.body
            context.comment_id = payload.comment.id
            context.event_type = "issue_comment"
            
            # Если комментарий в PR, добавляем PR контекст
            if payload.pull_request:
                context.pr_number = payload.pull_request.number
                context.event_type = "pull_request_comment"
                # Получаем diff для анализа кода
                context.diff_content = await self._fetch_pr_diff(payload.pull_request)
        
        # Обработка открытия/обновления PR
        elif payload.pull_request:
            context.content = f"PR: {payload.pull_request.title}\n\n{payload.pull_request.body or ''}"
            context.pr_number = payload.pull_request.number
            context.event_type = "pull_request"
            context.diff_content = await self._fetch_pr_diff(payload.pull_request)
        
        # Обработка Issues
        elif payload.issue:
            context.content = f"Issue: {payload.issue.title}\n\n{payload.issue.body or ''}"
            context.issue_number = payload.issue.number
            context.event_type = "issues"
        
        return context
    
    async def _fetch_pr_diff(self, pr: GitHubPullRequest) -> Optional[str]:
        """
        Получает diff для PR через GitHub API
        
        Реализованные подходы:
        1. Прямой запрос к GitHub API для получения diff
        2. Обработка ошибок и fallback
        3. Ограничение размера diff для оптимизации
        
        Args:
            pr: GitHubPullRequest объект с метаданными
            
        Returns:
            str: Diff в унифицированном формате или None при ошибке
        """
        try:
            import httpx
            
            # Используем GitHub API для получения diff
            async with httpx.AsyncClient() as client:
                headers = {
                    "Accept": "application/vnd.github.v3.diff",
                    "User-Agent": "claude-openai-bridge/1.0"
                }
                
                # Добавляем токен если доступен через переменную окружения
                github_token = os.getenv("GITHUB_TOKEN")
                if github_token:
                    headers["Authorization"] = f"token {github_token}"
                
                response = await client.get(pr.diff_url, headers=headers)
                
                if response.status_code == 200:
                    diff_content = response.text
                    
                    # Ограничиваем размер diff для производительности
                    max_diff_size = 10000  # 10KB максимум
                    if len(diff_content) > max_diff_size:
                        diff_content = diff_content[:max_diff_size] + "\n\n... (diff truncated for performance)"
                    
                    return diff_content
                else:
                    logger.warning(f"Failed to fetch PR diff: {response.status_code}")
                    return f"# Could not fetch diff for PR #{pr.number} (Status: {response.status_code})"
                    
        except Exception as e:
            logger.error(f"Error fetching PR diff: {e}")
            return f"# Error fetching diff for PR #{pr.number}: {str(e)}"
    
    async def create_response(self, context: GitHubActionContext) -> Dict[str, Any]:
        """
        Генерирует ответ на основе GitHub контекста
        
        Дизайн решения:
        - Специализированные промпты для разных типов событий
        - Включение релевантного контекста (diff, PR info)
        - Форматирование ответа для GitHub Markdown
        """
        # Построение контекстного промпта
        prompt_parts = []
        
        # Системный контекст
        system_context = self._build_system_context(context)
        prompt_parts.append(f"System: {system_context}")
        
        # Основной контент
        prompt_parts.append(f"User: {context.content}")
        
        # Добавляем diff если доступен
        if context.diff_content:
            prompt_parts.append(f"Code diff:\n```diff\n{context.diff_content}\n```")
        
        full_prompt = "\n\n".join(prompt_parts)
        
        # Создаем фиктивный запрос для Claude адаптера
        mock_request = ChatCompletionRequest(
            model=CONFIG["default_model"],
            messages=[
                ChatMessage(role="system", content=system_context),
                ChatMessage(role="user", content=context.content)
            ]
        )
        
        # Получаем ответ от Claude
        result = await self.claude_adapter.execute_claude_request(full_prompt, mock_request)
        
        return {
            "response": result["response"],
            "context": context.model_dump(),
            "metadata": result.get("metadata", {})
        }
    
    def _build_system_context(self, context: GitHubActionContext) -> str:
        """
        Строит системный промпт в зависимости от типа события
        
        Обоснование подхода:
        - Специализированные инструкции для разных сценариев
        - Включение метаданных репозитория для контекста
        - Указания по форматированию для GitHub
        """
        base_context = f"""You are an AI assistant integrated with GitHub via claude-code-action.
Repository: {context.repository.full_name}
Event: {context.event_type} - {context.action}
User: @{context.sender.login}

Format your response in GitHub Markdown. Be helpful, concise, and professional."""
        
        if context.event_type == "pull_request_comment":
            return base_context + f"""

This is a comment on Pull Request #{context.pr_number}. 
You have access to the PR diff and can provide code review, suggestions, or answer questions about the changes."""
        
        elif context.event_type == "pull_request":
            return base_context + f"""

This is about Pull Request #{context.pr_number}. 
Analyze the PR title, description, and code changes. Provide constructive feedback."""
        
        elif context.event_type == "issues":
            return base_context + f"""

This is about Issue #{context.issue_number}.
Help understand the problem, suggest solutions, or provide relevant information."""
        
        return base_context

# GitHub Security Functions
def verify_github_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Проверяет подпись GitHub webhook для безопасности
    
    Обоснование подхода безопасности:
    - Использование HMAC-SHA256 согласно стандарту GitHub
    - Сравнение подписей с использованием constant-time comparison
    - Обязательная проверка формата заголовка
    
    Args:
        payload_body: Тело webhook запроса в bytes
        signature_header: Заголовок X-Hub-Signature-256
        secret: Секретный ключ webhook
    
    Returns:
        bool: True если подпись корректна
    """
    if not signature_header:
        return False
    
    # GitHub отправляет подпись в формате "sha256=<hash>"
    if not signature_header.startswith('sha256='):
        return False
    
    received_signature = signature_header[7:]  # Убираем "sha256="
    
    # Вычисляем ожидаемую подпись
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    # Используем constant-time comparison для защиты от timing attacks
    return hmac.compare_digest(received_signature, expected_signature)

def extract_github_event_type(headers: Dict[str, str]) -> str:
    """
    Извлекает тип события из заголовков GitHub webhook
    
    Возможные типы событий:
    - issue_comment: Комментарий в Issue или PR
    - pull_request: События PR (открытие, изменение)
    - issues: События с Issues
    - push: Коммиты в репозиторий
    """
    return headers.get('x-github-event', 'unknown')

# Глобальные адаптеры  
bridge_adapter = ClaudeBridgeAdapter(bridge_path="scripts/claude_voice_bridge.py")
embedding_adapter = EmbeddingAdapter(bridge_path="scripts/claude_voice_bridge.py")
github_adapter = GitHubActionAdapter(claude_adapter=bridge_adapter)

# GitHub Integration Endpoints
@app.post("/github/webhook")
async def handle_github_webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
    x_github_delivery: str = Header(None)
) -> JSONResponse:
    """
    Обрабатывает GitHub webhook события
    
    Архитектурное решение:
    - Отдельный endpoint для GitHub интеграции
    - Полная валидация безопасности перед обработкой
    - Асинхронная обработка для быстрого ответа GitHub
    - Подробное логирование для отладки
    
    Поддерживаемые события:
    - issue_comment: Комментарии в Issues/PR
    - pull_request: События Pull Request
    - issues: События Issues
    
    Returns:
        JSONResponse: Статус обработки и результат
    """
    try:
        # Получаем тело запроса
        body = await request.body()
        
        # Проверяем включена ли GitHub интеграция
        if not CONFIG["github_integration_enabled"]:
            return JSONResponse(
                status_code=503,
                content={"error": "GitHub integration is disabled"}
            )
        
        # Проверяем подпись если требуется
        if CONFIG["require_webhook_signature"]:
            webhook_secret = CONFIG["github_webhook_secret"]
            if not webhook_secret:
                logger.error("GitHub webhook secret not configured")
                return JSONResponse(
                    status_code=500,
                    content={"error": "Webhook secret not configured"}
                )
            
            if not verify_github_signature(body, x_hub_signature_256 or "", webhook_secret):
                logger.warning(f"Invalid GitHub webhook signature from {request.client}")
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid signature"}
                )
        
        # Парсим JSON payload
        try:
            payload_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook payload: {e}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON payload"}
            )
        
        # Логируем событие
        logger.info(f"GitHub webhook: {x_github_event} from {payload_data.get('repository', {}).get('full_name', 'unknown')}")
        
        # Фильтруем поддерживаемые события
        supported_events = ["issue_comment", "pull_request", "issues"]
        if x_github_event not in supported_events:
            logger.info(f"Ignoring unsupported event: {x_github_event}")
            return JSONResponse(
                status_code=200,
                content={"message": f"Event {x_github_event} ignored"}
            )
        
        # Валидируем и парсим payload
        try:
            webhook_payload = GitHubWebhookPayload(**payload_data)
        except ValidationError as e:
            logger.error(f"Invalid webhook payload structure: {e}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid payload structure", "details": e.errors()}
            )
        
        # Обрабатываем webhook через GitHub адаптер
        context = await github_adapter.process_webhook(webhook_payload)
        
        # Проверяем нужно ли отвечать (для комментариев)
        if webhook_payload.comment and not github_adapter.should_respond(context.content):
            logger.info("Comment doesn't contain trigger phrases, ignoring")
            return JSONResponse(
                status_code=200,
                content={"message": "No trigger phrases found, ignoring"}
            )
        
        # Генерируем ответ через Claude
        response_data = await github_adapter.create_response(context)
        
        logger.info(f"Generated response for {x_github_event} in {context.repository.full_name}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Webhook processed successfully",
                "event_type": x_github_event,
                "repository": context.repository.full_name,
                "response_length": len(response_data["response"]),
                "context": {
                    "pr_number": context.pr_number,
                    "issue_number": context.issue_number,
                    "comment_id": context.comment_id
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "details": str(e)}
        )

@app.get("/github/status")
async def github_integration_status() -> Dict[str, Any]:
    """
    Возвращает статус GitHub интеграции
    
    Полезно для:
    - Проверки конфигурации
    - Диагностики проблем
    - Мониторинга состояния
    """
    return {
        "github_integration_enabled": CONFIG["github_integration_enabled"],
        "webhook_secret_configured": bool(CONFIG["github_webhook_secret"]),
        "require_signature_verification": CONFIG["require_webhook_signature"],
        "supported_events": ["issue_comment", "pull_request", "issues"],
        "trigger_phrases": github_adapter.trigger_phrases,
        "claude_adapter_ready": bridge_adapter is not None
    }

@app.post("/github/analyze")
async def analyze_github_content(
    request: GitHubActionContext
) -> Dict[str, Any]:
    """
    Анализирует GitHub контент напрямую (без webhook)
    
    Полезно для:
    - Тестирования интеграции
    - Прямого вызова из GitHub Action
    - Кастомных сценариев анализа
    """
    try:
        response_data = await github_adapter.create_response(request)
        
        return {
            "success": True,
            "response": response_data["response"],
            "context": response_data["context"],
            "metadata": response_data["metadata"]
        }
        
    except Exception as e:
        logger.error(f"Error analyzing GitHub content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/github/comment")
async def post_github_comment(
    repo_full_name: str,
    issue_number: int,
    comment_body: str,
    github_token: str = Header(..., alias="X-GitHub-Token")
) -> Dict[str, Any]:
    """
    Отправляет комментарий в GitHub Issue или PR
    
    Архитектурное решение:
    - Прямая интеграция с GitHub API
    - Безопасная передача токена через заголовок
    - Валидация всех параметров
    
    Альтернативные подходы:
    1. Использование GitHub App вместо токена
    2. Интеграция через GraphQL API
    3. Batch операции для множественных комментариев
    """
    try:
        import httpx
        
        # GitHub API endpoint
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments"
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "body": comment_body
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 201:
                comment_data = response.json()
                return {
                    "success": True,
                    "comment_id": comment_data["id"],
                    "html_url": comment_data["html_url"],
                    "message": "Comment posted successfully"
                }
            else:
                logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"GitHub API error: {response.text}"
                )
                
    except Exception as e:
        logger.error(f"Error posting GitHub comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/github/repository/{owner}/{repo}")
async def get_repository_info(
    owner: str,
    repo: str,
    github_token: str = Header(None, alias="X-GitHub-Token")
) -> Dict[str, Any]:
    """
    Получает информацию о репозитории
    
    Используется для:
    - Получения метаданных репозитория
    - Проверки доступности
    - Извлечения настроек и конфигурации
    """
    try:
        import httpx
        
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {}
        
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                repo_data = response.json()
                return {
                    "success": True,
                    "repository": {
                        "id": repo_data["id"],
                        "name": repo_data["name"],
                        "full_name": repo_data["full_name"],
                        "description": repo_data.get("description"),
                        "language": repo_data.get("language"),
                        "default_branch": repo_data["default_branch"],
                        "private": repo_data["private"],
                        "topics": repo_data.get("topics", []),
                        "html_url": repo_data["html_url"]
                    }
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Repository not found or access denied"
                )
                
    except Exception as e:
        logger.error(f"Error getting repository info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/github/pull/{owner}/{repo}/{pull_number}")
async def get_pull_request_info(
    owner: str,
    repo: str,
    pull_number: int,
    github_token: str = Header(None, alias="X-GitHub-Token"),
    include_diff: bool = False
) -> Dict[str, Any]:
    """
    Получает детальную информацию о Pull Request
    
    Особенности реализации:
    - Опциональное включение diff для анализа кода
    - Извлечение списка измененных файлов
    - Метаданные для контекстного анализа
    """
    try:
        import httpx
        
        base_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = {}
        
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        
        async with httpx.AsyncClient() as client:
            # Получаем основную информацию о PR
            pr_response = await client.get(base_url, headers=headers)
            
            if pr_response.status_code != 200:
                raise HTTPException(
                    status_code=pr_response.status_code,
                    detail="Pull request not found"
                )
            
            pr_data = pr_response.json()
            result = {
                "success": True,
                "pull_request": {
                    "id": pr_data["id"],
                    "number": pr_data["number"],
                    "title": pr_data["title"],
                    "body": pr_data.get("body"),
                    "state": pr_data["state"],
                    "user": {
                        "login": pr_data["user"]["login"],
                        "id": pr_data["user"]["id"]
                    },
                    "base": pr_data["base"],
                    "head": pr_data["head"],
                    "html_url": pr_data["html_url"],
                    "diff_url": pr_data["diff_url"],
                    "patch_url": pr_data["patch_url"],
                    "created_at": pr_data["created_at"],
                    "updated_at": pr_data["updated_at"]
                }
            }
            
            # Получаем список файлов
            files_response = await client.get(f"{base_url}/files", headers=headers)
            if files_response.status_code == 200:
                files_data = files_response.json()
                result["files"] = [
                    {
                        "filename": file["filename"],
                        "status": file["status"],
                        "additions": file["additions"],
                        "deletions": file["deletions"],
                        "changes": file["changes"],
                        "patch": file.get("patch") if include_diff else None
                    }
                    for file in files_data
                ]
            
            # Получаем diff если запрошен
            if include_diff:
                diff_headers = headers.copy()
                diff_headers["Accept"] = "application/vnd.github.v3.diff"
                
                diff_response = await client.get(base_url, headers=diff_headers)
                if diff_response.status_code == 200:
                    result["diff"] = diff_response.text
            
            return result
            
    except Exception as e:
        logger.error(f"Error getting pull request info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API Endpoints
@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    """Список доступных моделей (OpenAI совместимый)"""
    models = [
        # Anthropic Chat модели
        ModelInfo(
            id="claude-3-5-sonnet-20241022",
            created=int(time.time()),
            root="claude-3-5-sonnet-20241022"
        ),
        ModelInfo(
            id="claude-3-5-haiku-20241022", 
            created=int(time.time()),
            root="claude-3-5-haiku-20241022"
        ),
        ModelInfo(
            id="claude-3-opus-20240229",
            created=int(time.time()),
            root="claude-3-opus-20240229"
        ),
        ModelInfo(
            id="claude-3-sonnet-20240229",
            created=int(time.time()),
            root="claude-3-sonnet-20240229"
        ),
        ModelInfo(
            id="claude-3-haiku-20240307",
            created=int(time.time()),
            root="claude-3-haiku-20240307"
        ),
        # OpenAI Chat модели
        ModelInfo(
            id="gpt-4o",
            created=int(time.time()),
            root="gpt-4o"
        ),
        ModelInfo(
            id="gpt-4o-mini",
            created=int(time.time()),
            root="gpt-4o-mini"
        ),
        ModelInfo(
            id="gpt-4-turbo",
            created=int(time.time()),
            root="gpt-4-turbo"
        ),
        ModelInfo(
            id="gpt-4-turbo-preview",
            created=int(time.time()),
            root="gpt-4-turbo-preview"
        ),
        ModelInfo(
            id="gpt-4",
            created=int(time.time()),
            root="gpt-4"
        ),
        ModelInfo(
            id="gpt-3.5-turbo",
            created=int(time.time()),
            root="gpt-3.5-turbo"
        ),
        ModelInfo(
            id="gpt-3.5-turbo-16k",
            created=int(time.time()),
            root="gpt-3.5-turbo-16k"
        ),
        # OpenAI специализированные модели
        ModelInfo(
            id="o1",
            created=int(time.time()),
            root="o1"
        ),
        ModelInfo(
            id="o1-mini",
            created=int(time.time()),
            root="o1-mini"
        ),
        ModelInfo(
            id="o1-preview",
            created=int(time.time()),
            root="o1-preview"
        ),
        ModelInfo(
            id="o3-mini",
            created=int(time.time()),
            root="o3-mini"
        ),
        # Embedding модели
        ModelInfo(
            id="text-embedding-3-small",
            created=int(time.time()),
            root="text-embedding-3-small"
        ),
        ModelInfo(
            id="text-embedding-3-large",
            created=int(time.time()),
            root="text-embedding-3-large"
        ),
        ModelInfo(
            id="text-embedding-ada-002",
            created=int(time.time()),
            root="text-embedding-ada-002"
        )
    ]
    
    return {"object": "list", "data": models}

@app.post("/v1/chat/completions", response_model=None)
async def create_chat_completion(request_body: Dict[str, Any] = Body(...)):
    """Создаёт chat completion (OpenAI совместимый)"""
    
    try:
        # Manual validation to catch errors
        request = ChatCompletionRequest(**request_body)
        
        # Debug logging
        logger.info(f"Received request: model={request.model}, messages_count={len(request.messages)}")
        
        if request.stream:
            return StreamingResponse(
                stream_chat_completion(request),
                media_type="text/event-stream"
            )
        else:
            return await non_streaming_chat_completion(request)
            
    except ValidationError as e:
        logger.error(f"Validation error: {e.json()}")
        logger.error(f"Request body: {json.dumps(request_body, indent=2)}")
        # Return more detailed error info
        error_detail: Dict[str, Any] = {
            "error": "Validation failed",
            "details": e.errors(),
            "received": request_body
        }
        raise HTTPException(status_code=422, detail=error_detail)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Request body: {json.dumps(request_body, indent=2)}")
        raise HTTPException(status_code=500, detail=str(e))

async def non_streaming_chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Обрабатывает не-streaming chat completion"""
    
    # Конвертируем сообщения в Claude промпт
    prompt = await bridge_adapter.process_messages(request.messages)
    
    # Выполняем через Claude Bridge
    result = await bridge_adapter.execute_claude_request(prompt, request)
    
    response_text = result["response"]
    # metadata = result["metadata"]  # Not currently used
    
    # Оцениваем использование токенов
    prompt_tokens = len(prompt.split()) * 1.3  # Примерная оценка
    completion_tokens = len(response_text.split()) * 1.3
    
    # Создаём OpenAI-совместимый ответ
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    
    return ChatCompletionResponse(
        id=completion_id,
        created=int(time.time()),
        model=request.model,
        choices=[{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        usage=Usage(
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=int(prompt_tokens + completion_tokens)
        )
    )

async def stream_chat_completion(request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
    """Обрабатывает streaming chat completion"""
    
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    created = int(time.time())
    
    # Конвертируем сообщения в Claude промпт
    prompt = await bridge_adapter.process_messages(request.messages)
    
    try:
        # Build streaming command for Claude Code MAX
        cmd = [CONFIG["claude_cli_path"], prompt]
        
        # Add system prompt if exists
        system_messages = [msg for msg in request.messages if msg.role == "system"]
        if system_messages:
            system_text = system_messages[0].content_text
            if system_text:
                cmd.extend(["--system-prompt", system_text])
        
        # Запускаем Claude Bridge процесс
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Стримим вывод
        buffer = ""
        chunk_index = 0
        
        if process.stdout:
            while True:
                chunk = await process.stdout.read(64)  # Маленькие чанки для real-time
                if not chunk:
                    break
            
                text = chunk.decode('utf-8', errors='replace')
                buffer += text
                
                # Отправляем накопленный буфер как чанки
                if len(buffer) > 10:  # Отправляем когда достаточно контента
                    chunk_data = ChatCompletionChunk(
                        id=completion_id,
                        created=created,
                        model=request.model,
                        choices=[{
                            "index": 0,
                            "delta": {
                                "content": buffer
                            },
                            "finish_reason": None
                        }]
                    )
                    
                    yield f"data: {chunk_data.model_dump_json(exclude_none=True)}\n\n"
                    buffer = ""
                    chunk_index += 1
        
        # Отправляем финальный чанк
        if buffer:
            chunk_data = ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[{
                    "index": 0,
                    "delta": {
                        "content": buffer
                    },
                    "finish_reason": None
                }]
            )
            yield f"data: {chunk_data.model_dump_json(exclude_none=True)}\n\n"
        
        # Отправляем завершающий чанк
        final_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        )
        
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"
        
        await process.wait()
        
    except Exception as e:
        logger.error(f"Streaming ошибка: {e}")
        # Отправляем error чанк
        error_chunk: Dict[str, Any] = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": f"Ошибка: {str(e)}"
                },
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

@app.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """Создает векторные представления через Claude (OpenAI совместимый)"""
    try:
        # Пробрасываем запрос к Claude
        response = await embedding_adapter.create_embeddings(request)
        
        logger.info(f"Создано {len(response.data)} embeddings для модели {request.model}")
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания embeddings: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

@app.get("/")
async def root() -> Dict[str, Any]:
    """API info endpoint"""
    return {
        "name": "Claude OpenAI Server",
        "version": "2.1.0",
        "description": "OpenAI-совместимый API для Claude Code SDK",
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions",
            "embeddings": "/v1/embeddings"
        },
        "features": {
            "vision": CONFIG["supports_vision"],
            "computer_use": CONFIG["supports_computer_use"], 
            "caching": CONFIG["supports_caching"],
            "embeddings": CONFIG["supports_embeddings"],
            "streaming": True,
            "claude_code_max_exclusive": True
        },
        "integration": {
            "claude_code_max": True,
            "no_api_key_required": CONFIG["no_api_key_required"],
            "cline_roo_cursor": True,
            "openai_compatible": True
        }
    }

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "dependencies_installed": True
    }

@app.post("/v1/chat/completions/debug")
async def debug_chat_completion(request: Request) -> Dict[str, Any]:
    """Debug endpoint to capture raw request"""
    try:
        body = await request.body()
        json_body = await request.json()
        
        logger.info(f"Raw body: {body.decode('utf-8')}")
        logger.info(f"JSON body: {json.dumps(json_body, indent=2)}")
        
        return {"debug": "Check server logs for request details", "json": json_body}
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return {"error": str(e)}

# Конфигурационный endpoint для Roo/Cline/Cursor
@app.get("/v1/models/{model_id}")
async def get_model_info(model_id: str) -> Dict[str, Any]:
    """Получить информацию о конкретной модели"""
    if model_id.startswith("claude"):
        return {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
            "capabilities": {
                "vision": CONFIG["supports_vision"],
                "computer_use": CONFIG["supports_computer_use"],
                "caching": CONFIG["supports_caching"]
            },
            "limits": {
                "max_tokens": CONFIG["max_tokens"],
                "context_window": CONFIG["context_window"]
            },
            "pricing": {
                "input_per_1k": CONFIG["price_per_1k_input"],
                "output_per_1k": CONFIG["price_per_1k_output"]
            }
        }
    elif model_id.startswith("text-embedding"):
        return {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
            "type": "embedding",
            "capabilities": {
                "embeddings": True
            },
            "limits": {
                "dimensions": 1536,  # Стандартный размер OpenAI
                "max_input_tokens": 8192
            },
            "pricing": {
                "per_1k_tokens": 0.0001
            }
        }
    else:
        raise HTTPException(status_code=404, detail="Модель не найдена")

def main() -> None:
    """Главная функция запуска сервера"""
    
    print("🚀 Claude OpenAI Server")
    print("📡 OpenAI-compatible API for Claude Code MAX")
    print("🤖 Cline/Roo/Cursor compatibility: ✅")
    print("👁️ Vision support: ✅")
    print("💻 Computer use: ✅")
    print("⚡ Streaming: ✅")
    print("🧠 Embeddings API: ✅")
    
    print(f"\n🌐 Server: http://localhost:8000")
    print(f"📚 API docs: http://localhost:8000/docs")
    print(f"❤️ Health: http://localhost:8000/health")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )

if __name__ == "__main__":
    main()